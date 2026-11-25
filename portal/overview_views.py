from time import perf_counter
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .access import analyst_read_snapshot, audit, is_analyst, organizations_for
from .models import Asset, Membership
from .overview import OverviewEvidence, company_states, priority_assets
from .overview_queries import overview_queries


@login_required
@never_cache
@analyst_read_snapshot
def overview(request):
    started = perf_counter()
    with overview_queries(planning_limit=4) as database:
        response = _overview_response(request)
    response["Referrer-Policy"] = "same-origin"
    response["Server-Timing"] = (
        f"overview;dur={(perf_counter() - started) * 1000:.1f}, "
        f"database;dur={database.seconds * 1000:.1f}, "
        f"dbmax;dur={database.slowest * 1000:.1f}, " + response["Server-Timing"]
    )
    return response


def _overview_response(request):
    started = perf_counter()
    orgs = (
        organizations_for(request.user)
        .annotate(overview_has_inventory=Exists(Asset.objects.filter(organization_id=OuterRef("pk"))))
        .order_by("-overview_has_inventory", "name", "pk")
    )
    selected = request.GET.get("organization", "")
    if selected:
        org = get_object_or_404(orgs, slug=selected)
        orgs = orgs.filter(pk=org.pk)
    query = request.GET.get("q", "")[:160].strip()
    if query:
        orgs = orgs.filter(name__icontains=query)
    page = Paginator(orgs, 12).get_page(request.GET.get("page"))
    page.object_list = list(
        page.object_list.select_related("inventory_source__instance", "inventory_review_policy")
    )
    if request.user.is_superuser:
        audited_orgs = page.object_list
    elif is_analyst(request.user):
        member_ids = set(
            Membership.objects.filter(user=request.user, organization__in=page.object_list).values_list(
                "organization_id", flat=True
            )
        )
        audited_orgs = [org for org in page if org.pk not in member_ids]
    else:
        audited_orgs = []
    for org in audited_orgs:
        audit(request.user, org, "operator.access")
    scoped = perf_counter()
    evidence = OverviewEvidence.for_page(request.user, page.object_list)
    companies = company_states(request.user, page.object_list, evidence=evidence)
    roles = dict(
        Membership.objects.filter(user=request.user, organization__in=page.object_list).values_list(
            "organization_id", "role"
        )
    )
    from .review_focus import posture

    machine_postures = posture(request.user, [state["org"].pk for state in companies])["organizations"]
    from .software_coverage import inventory, accounting, observation_counts

    software_accounting = accounting(inventory(request.user, [s["org"].pk for s in companies]))
    unlinked_counts = observation_counts(request.user, [s["org"].pk for s in companies])
    for state in companies:
        state["software_accounting"] = software_accounting.get(
            state["org"].pk, {"total": 0, "categories": []}
        )
        state["software_accounting"]["unlinked"] = unlinked_counts.get(state["org"].pk, 0)
        state["posture"] = machine_postures.get(state["org"].pk)
        state["setup_pending"] = not state["org"].overview_has_inventory and not any(
            state[key] for key in ("products", "reviews", "issues", "risk_assessments", "overdue")
        )
        role = roles.get(state["org"].pk)
        source = getattr(state["org"], "inventory_source", None)
        state["setup_editable"] = request.user.is_superuser or role == "admin"
        state["csv_editable"] = (
            (request.user.is_superuser or role in {"admin", "editor"})
            and source is not None
            and source.mode == "manual"
        )
    from .overview_next_steps import decorate

    decorate(companies)
    aggregated = perf_counter()
    priority_timings = {}
    assets = priority_assets(
        request.user,
        orgs.filter(pk__in=[s["org"].pk for s in companies]),
        timings=priority_timings,
        evidence=evidence,
    )
    prioritized = perf_counter()
    response = render(
        request,
        "portal/overview.html",
        {
            "companies": companies,
            "main_companies": [s for s in companies if not s["setup_pending"] or selected or query],
            "pending_companies": [s for s in companies if s["setup_pending"] and not selected and not query],
            "page": page,
            "priority_assets": assets,
            "updated_at": timezone.now(),
            "query": query,
            "selected": selected,
        },
    )
    response["Server-Timing"] = (
        f"scope;dur={(scoped - started) * 1000:.1f}, "
        f"companies;dur={(aggregated - scoped) * 1000:.1f}, "
        f"priority;dur={(prioritized - aggregated) * 1000:.1f}, "
        f"render;dur={(perf_counter() - prioritized) * 1000:.1f}"
    )
    response["Server-Timing"] += "".join(
        f", {name};dur={duration:.1f}" for name, duration in priority_timings.items()
    )
    return response
