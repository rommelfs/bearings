"""Read-only, organization-scoped software accounting and evidence navigation."""

from urllib.parse import urlencode
import uuid

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.views.decorators.http import require_safe
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .access import analyst_read_snapshot, audit_operator_access, organizations_for
from .models import Asset
from .overview_queries import bounded_list, read_snapshot
from . import software_coverage as coverage


@login_required
@require_safe
@analyst_read_snapshot
def ledger(request, slug):
    with read_snapshot():
        return _ledger(request, slug)


@bounded_list
def _ledger(request, slug):
    org = get_object_or_404(organizations_for(request.user), slug=slug)
    audit_operator_access(request.user, org)
    category = request.GET.get("category", "")
    if category and category not in coverage.CATEGORIES:
        raise Http404
    query = request.GET.get("q", "")[:128].strip()
    with read_snapshot():
        qs = coverage.inventory(request.user, [org.pk])
        asset = None
        if request.GET.get("asset"):
            value = request.GET["asset"]
            try:
                if len(value) != 36:
                    raise ValueError
                asset_id = uuid.UUID(value)
            except ValueError:
                raise Http404 from None
            asset = get_object_or_404(Asset.objects.filter(organization=org), pk=asset_id)
            qs = qs.filter(asset=asset)
        view = request.GET.get("view", "installations")
        if view == "observations":
            return _observations(request, org, asset, query)
        if view != "installations":
            raise Http404
        # Search never uses another company's product data through a corrupt FK.
        if query:
            from django.db.models import Q

            qs = qs.filter(
                Q(asset__name__icontains=query) | Q(coverage_integrity=True, product__name__icontains=query)
            )
        summary = coverage.accounting(qs).get(org.pk, {"total": 0, "categories": []})
        if category:
            qs = qs.filter(coverage_category=category)
        page = Paginator(qs.order_by("asset__name", "pk"), 25).get_page(request.GET.get("page"))
        page.object_list = list(
            page.object_list.select_related("asset__organization").defer("asset__upstream_data")
        )
        # Hydrate only ownership-consistent links. A corrupt foreign product/device
        # is accounted for but its name, payload and source never enter the page.
        safe = (
            qs.filter(
                pk__in=[i.pk for i in page.object_list],
                coverage_integrity=True,
                coverage_component_integrity=True,
            )
            .select_related(
                "asset__organization",
                "product__watch",
                "agent_component__device__asset",
                "agent_component__device__source",
                "agent_component__device__organization",
                "agent_component__last_report",
            )
            .defer(
                "agent_component__last_report__body",
                "asset__upstream_data",
                "agent_component__device__reported_network",
                "agent_component__device__services",
            )
        )
        safe = {i.pk: i for i in safe}
        page.object_list = [safe.get(i.pk, i) for i in page.object_list]
        coverage.decorate(request.user, page.object_list)
    unlinked_scope = coverage.observations(request.user, [org.pk])
    if asset:
        unlinked_scope = unlinked_scope.filter(device__asset=asset)
    unlinked = unlinked_scope.count()
    params = {"q": query, "category": category}
    if asset:
        params["asset"] = asset.pk
    for item in summary["categories"]:
        item["url"] = coverage.url(org.slug, **{**params, "category": item["key"]})
    return render(
        request,
        "portal/software_coverage.html",
        {
            "org": org,
            "asset": asset,
            "page": page,
            "summary": summary,
            "unlinked": unlinked,
            "query": query,
            "category": category,
            "categories": coverage.CATEGORIES.items(),
            "previous_url": "?" + urlencode({**params, "page": page.previous_page_number()})
            if page.has_previous()
            else "",
            "next_url": "?" + urlencode({**params, "page": page.next_page_number()})
            if page.has_next()
            else "",
        },
    )


def _observations(request, org, asset, query):
    from django.db.models import Q

    qs = coverage.observations(request.user, [org.pk])
    if asset:
        qs = qs.filter(device__asset=asset)
    if query:
        qs = qs.filter(coverage_integrity=True).filter(
            Q(name__icontains=query) | Q(device__asset__name__icontains=query)
        )
    page = Paginator(
        qs.order_by("pk").values(
            "pk",
            "coverage_integrity",
            "coverage_name",
            "coverage_version",
            "coverage_host",
            "coverage_observed",
            "device_id",
            "inventory_excluded",
        ),
        25,
    ).get_page(request.GET.get("page"))
    page.object_list = list(page.object_list)
    for row in page:
        row["client_url"] = (
            reverse("agent-center", args=[org.slug])
            + "?"
            + urlencode({"device": row["device_id"], "q": row["coverage_name"]})
            if row["coverage_integrity"]
            else ""
        )
    params = {"view": "observations", "q": query}
    if asset:
        params["asset"] = asset.pk
    return render(
        request,
        "portal/software_observations.html",
        {
            "org": org,
            "asset": asset,
            "query": query,
            "page": page,
            "previous_url": "?" + urlencode({**params, "page": page.previous_page_number()})
            if page.has_previous()
            else "",
            "next_url": "?" + urlencode({**params, "page": page.next_page_number()})
            if page.has_next()
            else "",
        },
    )
