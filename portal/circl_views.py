"""Operator-only overview and transient private inventory research."""

from time import perf_counter
from django.contrib.auth.decorators import login_required
from django.db import OperationalError
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods
from .access import audit, is_analyst, require, organizations_for
from .circl import dashboard, findings_for, outstanding, research
from .circl_forms import ResearchForm
from .overview_queries import overview_queries, bounded_list, read_snapshot
from .national_snapshots import PendingSnapshot
from .presentation import severity_first
from .pagination import object_page
from django.urls import reverse


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
    from .map_configuration import map_options

    response = render(request, "portal/circl_overview.html", map_options())
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
        if section in {"summary", "versions", "problems", "activity", "history"}
        else "operator.national_invalid",
    )
    if section not in {"summary", "versions", "problems", "activity", "history"}:
        return private_response(render(request, "portal/circl_panel_error.html", status=404))
    started = perf_counter()
    timings = {}
    database = None
    try:
        with overview_queries(query_timeout_ms=3000, budget_ms=8000, planning_limit=4) as database:
            if section == "history":
                from .national_history import stock_history

                context = stock_history(request.user)
            else:
                context = dashboard(request.user, timings=timings, section=section)
            response = render(request, "portal/circl_panel_" + section + ".html", context)
    except (OperationalError, PendingSnapshot):
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
@bounded_list
def findings(request):
    authorize(request, "operator.national_findings")
    return _finding_response(request)


@login_required
@never_cache
@require_GET
@bounded_list
def organization_cases(request, slug):
    org = get_object_or_404(organizations_for(request.user), slug=slug)
    audit(request.user, org, "review.cases")
    return _finding_response(request, org=org)


def _finding_response(request, org=None):
    qs = outstanding(findings_for(request.user))
    organization_filter = org.slug if org else request.GET.get("organization", "")[:100]
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
    from . import review_focus
    from django.core import signing

    view = request.GET.get("view", "cases")
    token = request.GET.get("case", "")
    if len(token) > 3000 or view not in {"cases", "records"}:
        return private_response(
            render(request, "portal/circl_findings.html", {"invalid_filter": True}, status=400)
        )
    if token:
        try:
            qs = review_focus.select_case(qs, token)
        except (signing.BadSignature, ValueError, TypeError):
            return private_response(
                render(request, "portal/circl_findings.html", {"invalid_filter": True}, status=400)
            )
    if view == "cases":
        category = request.GET.get("category", "version")
        if category not in {*review_focus.CASE_LABELS, "all"}:
            return private_response(
                render(request, "portal/circl_findings.html", {"invalid_filter": True}, status=400)
            )
        scoped = review_focus.case_scope(qs)
        if category != "all":
            scoped = scoped.filter(case_kind=category)
        filters = {
            "bucket": bucket,
            "record": record,
            "organization": organization_filter,
            "assessment": "all",
        }
        page = review_focus.cases(scoped, request.GET.get("page"), filters=filters, base_url=request.path)
        return private_response(
            render(
                request,
                "portal/review_cases.html",
                {
                    "page": page,
                    "category": category,
                    "bucket": bucket,
                    "record": record,
                    "organization_filter": organization_filter,
                    "categories": [(key, label[0]) for key, label in review_focus.CASE_LABELS.items()],
                    "back_url": reverse("organization", args=[org.slug])
                    if org
                    else reverse("circl-overview"),
                },
            )
        )
    from .review_queue import classified, BUCKETS

    assessment = request.GET.get("assessment", "action")
    if assessment not in dict(BUCKETS):
        return private_response(
            render(request, "portal/circl_findings.html", {"invalid_filter": True}, status=400)
        )
    qs = classified(qs)
    bins = {
        row["queue_bucket"]: row
        for row in qs.order_by()
        .values("queue_bucket")
        .annotate(total=Count("pk"), vulnerabilities=Count("record__external_id", distinct=True))
    }
    counts = {key: bins.get(key, {}).get("total", 0) for key, _ in BUCKETS}
    counts["all"] = sum(counts.values())
    if assessment != "all":
        qs = qs.filter(queue_bucket=assessment)
    page = object_page(
        severity_first(
            qs.select_related(
                "organization",
                "record",
                "installation__product",
                "installation__asset__responsible_contact",
                "distro_match__component__device",
                "distro_match__advisory__feed",
                "distro_match__ubuntu_status",
            )
        ),
        25,
        request.GET.get("page"),
        count=counts[assessment],
    )
    from .distro_verdicts import decorate_package_verdict

    for finding in page:
        decorate_package_verdict(finding)
    return private_response(
        render(
            request,
            "portal/circl_findings.html",
            {
                "page": page,
                "record": record,
                "bucket": bucket,
                "organization_filter": organization_filter,
                "assessment": assessment,
                "case_token": token,
                "back_url": reverse("organization", args=[org.slug]) if org else reverse("circl-overview"),
                "assessment_options": [(key, label, counts[key]) for key, label in BUCKETS],
                "retained_total": counts["all"],
                "distinct_vulnerabilities": bins.get(assessment, {}).get("vulnerabilities")
                if assessment != "all"
                else None,
            },
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
    status = 200
    try:
        if request.method == "POST" and form.is_valid():
            with read_snapshot(), overview_queries(planning_limit=4, query_timeout_ms=5000, budget_ms=12000):
                try:
                    selected, context["match_counts"] = research(request.user, form.cleaned_data)
                except ValueError as error:
                    form.add_error(None, str(error))
                else:
                    context["page"] = object_page(
                        selected.select_related(
                            "product", "asset__organization", "asset__responsible_contact"
                        ).order_by("asset__organization__name", "asset__name", "pk"),
                        25,
                        form.cleaned_data.get("page"),
                        count=context["match_counts"][form.cleaned_data["bucket"]],
                    )
                    context["bucket"] = form.cleaned_data["bucket"]
    except OperationalError:
        context = {"form": form, "updated_at": timezone.now()}
        form.add_error(
            None,
            "Research is temporarily busy. Refine your query or retry shortly; no partial results are shown.",
        )
        status = 503
    return private_response(render(request, "portal/circl_research.html", context, status=status))


@login_required
@never_cache
@require_GET
@bounded_list
def coverage_records(request):
    from django.db.models import Exists, OuterRef, F
    from django.http import Http404
    from .access import organizations_for
    from .circl import installations_for
    from .models import Asset, Contact
    from .notifications import contact_policy
    from .query_integrity import consistent

    authorize(request, "operator.national_coverage_records")
    bucket = request.GET.get("bucket", "assets")
    titles = {
        "assets": "Active inventory assets",
        "installations": "Recorded installations",
        "unknown": "Unknown installed versions",
        "no_contact": "Companies without a current verified response contact",
        "companies": "Companies with outstanding reviews",
    }
    if bucket not in titles:
        raise Http404
    orgs = organizations_for(request.user)
    if bucket == "assets":
        qs = (
            Asset.objects.filter(organization__in=orgs, lifecycle="active")
            .filter(consistent(source__organization_id=F("organization_id")))
            .select_related("organization")
            .order_by("organization__name", "name", "pk")
        )
    elif bucket in {"installations", "unknown"}:
        qs = (
            installations_for(request.user)
            .select_related("asset__organization", "product")
            .order_by("asset__organization__name", "asset__name", "product__name", "pk")
        )
        if bucket == "unknown":
            qs = qs.filter(version="")
    else:
        if bucket == "no_contact":
            contacts = Contact.objects.filter(organization_id=OuterRef("pk"), **contact_policy()).exclude(
                function="dpo"
            )
            qs = orgs.filter(~Exists(contacts))
        else:
            reviews = outstanding(findings_for(request.user)).filter(organization_id=OuterRef("pk"))
            qs = orgs.filter(Exists(reviews))
        qs = qs.order_by("name", "pk")
    page = object_page(qs, 50, request.GET.get("page"))
    return private_response(
        render(
            request,
            "portal/circl_coverage_records.html",
            {
                "bucket": bucket,
                "title": titles[bucket],
                "page": page,
                "installations": bucket in {"installations", "unknown"},
                "companies": bucket in {"no_contact", "companies"},
            },
        )
    )


@login_required
@never_cache
@require_GET
@bounded_list
def machine_records(request, slug=None):
    from .review_focus import posture
    from django.core.paginator import Paginator

    org = get_object_or_404(organizations_for(request.user), slug=slug) if slug else None
    if org is None:
        authorize(request, "operator.machine_indicators")
    else:
        audit(request.user, org, "inventory.machine_indicators")
    scope = posture(request.user, [org.pk] if org else None)["machines"]
    focus = request.GET.get("focus", "all")
    filters = {
        "all": {},
        "evaluated": {"evaluated": True},
        "matched": {"evaluated": True, "version_match": True},
        "missing": {"evaluated": False},
        "manual": {"manual": True},
        "partial": {"evaluated": True, "partial": True},
    }
    if focus not in filters:
        return private_response(
            render(request, "portal/circl_findings.html", {"invalid_filter": True}, status=400)
        )
    page = Paginator(
        scope.filter(**filters[focus])
        .select_related("organization")
        .defer("upstream_data")
        .order_by("organization__name", "name", "pk"),
        25,
    ).get_page(request.GET.get("page"))
    return private_response(
        render(request, "portal/machine_indicators.html", {"page": page, "focus": focus, "org": org})
    )
