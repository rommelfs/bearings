"""Operator-only overview and transient private inventory research."""

from time import perf_counter
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import OperationalError
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods
from .access import audit, is_analyst, require
from .circl import dashboard, findings_for, outstanding, research
from .circl_forms import ResearchForm
from .overview_queries import overview_queries
from .presentation import severity_first


def authorize(request, action):
    require(request.user.is_superuser or is_analyst(request.user))
    # Audit the operator read, without retaining private research criteria or results.
    audit(request.user, None, action, target="circl-overview")


def private_response(response):
    response["Referrer-Policy"] = "same-origin"
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


@login_required
@never_cache
@require_GET
def overview(request):
    authorize(request, "operator.national_overview")
    started = perf_counter()
    response = render(request, "portal/circl_overview.html")
    response["Server-Timing"] = (
        f"national;dur={(perf_counter() - started) * 1000:.1f}, nationalshell;dur={(perf_counter() - started) * 1000:.1f}"
    )
    return private_response(response)


@login_required
@never_cache
@require_GET
def panel(request, section):
    authorize(
        request,
        "operator.national_" + section
        if section in {"summary", "versions", "problems", "activity"}
        else "operator.national_invalid",
    )
    if section not in {"summary", "versions", "problems", "activity"}:
        return private_response(render(request, "portal/circl_panel_error.html", status=404))
    started = perf_counter()
    timings = {}
    database = None
    try:
        with overview_queries(query_timeout_ms=3000, budget_ms=8000, planning_limit=4) as database:
            context = dashboard(request.user, timings=timings, section=section)
            response = render(request, "portal/circl_panel_" + section + ".html", context)
    except OperationalError:
        response = render(request, "portal/circl_panel_error.html", status=503)
    response["Server-Timing"] = f"national;dur={(perf_counter() - started) * 1000:.1f}"
    if database:
        response["Server-Timing"] += (
            f", database;dur={database.seconds * 1000:.1f}, dbmax;dur={database.slowest * 1000:.1f}"
        )
    response["Server-Timing"] += "".join(f", {name};dur={duration:.1f}" for name, duration in timings.items())
    return private_response(response)


@login_required
@never_cache
@require_GET
def findings(request):
    authorize(request, "operator.national_findings")
    qs = outstanding(findings_for(request.user))
    organization_filter = request.GET.get("organization", "")[:100]
    if organization_filter:
        qs = qs.filter(organization__slug=organization_filter)
    record = request.GET.get("record", "")[:120]
    bucket = request.GET.get("bucket", "all")
    if record:
        qs = qs.filter(record__external_id=record)
    if bucket == "affected":
        qs = qs.filter(analyst_applicability="affected")
    elif bucket == "accepted":
        qs = qs.filter(status="accepted_risk")
    elif bucket == "critical":
        qs = qs.filter(record__source_severity="critical")
    elif bucket != "all":
        return private_response(
            render(request, "portal/circl_findings.html", {"invalid_filter": True}, status=400)
        )
    page = Paginator(
        severity_first(
            qs.select_related(
                "organization", "record", "installation__product", "installation__asset__responsible_contact"
            )
        ),
        25,
    ).get_page(request.GET.get("page"))
    return private_response(
        render(
            request,
            "portal/circl_findings.html",
            {"page": page, "record": record, "bucket": bucket, "organization_filter": organization_filter},
        )
    )


@login_required
@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def inventory_research(request):
    authorize(request, "operator.inventory_research")
    # Confidential criteria stay out of URLs, sessions, audits and upstream requests.
    form = ResearchForm(request.POST if request.method == "POST" else None)
    context = {"form": form, "updated_at": timezone.now()}
    if request.method == "POST" and form.is_valid():
        with overview_queries():
            try:
                selected, context["match_counts"] = research(request.user, form.cleaned_data)
            except ValueError as error:
                form.add_error(None, str(error))
            else:
                context["page"] = Paginator(
                    selected.select_related(
                        "product", "asset__organization", "asset__responsible_contact"
                    ).order_by("asset__organization__name", "asset__name", "pk"),
                    25,
                ).get_page(form.cleaned_data.get("page"))
                context["bucket"] = form.cleaned_data["bucket"]
    return private_response(render(request, "portal/circl_research.html", context))
