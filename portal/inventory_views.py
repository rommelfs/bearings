"""Company and asset inventory pages."""

import logging
from datetime import timedelta
from time import perf_counter

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import OperationalError
from django.http import HttpResponse, HttpResponseBadRequest
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .access import (
    analyst_read_snapshot,
    audit_organizations,
    can_edit,
    can_operator_review,
    organization,
    organizations_for,
    visible_findings,
    visible_findings_for,
)
from .asset_attention import attention_for
from .asset_context import asset_context
from .forms import (
    ClaimReviewForm,
    MissingReviewForm,
)
from .inventory_presentation import (
    additional_software_filter,
    assigned_addresses,
    decorate_addresses,
    top_level_assets,
)
from .overview_queries import OverviewBudgetExceeded, overview_queries, read_snapshot
from .models import (
    AgentDevice,
    Asset,
    Installation,
)
from .presentation import ACTIVE_REVIEWS, decorate_finding, severity_first

logger = logging.getLogger(__name__)


def company_cards(user, orgs, page_number):
    page = Paginator(orgs, 24).get_page(page_number)
    page.object_list = list(
        page.object_list.select_related("inventory_source__instance").prefetch_related("contacts")
    )
    ids = [org.pk for org in page]
    asset_counts = dict(
        top_level_assets(
            Asset.objects.filter(
                organization_id__in=ids,
                source__organization_id=F("organization_id"),
            )
        )
        .values("organization_id")
        .annotate(total=Count("pk"))
        .values_list("organization_id", "total")
    )
    finding_counts = dict(
        visible_findings_for(user)
        .filter(organization_id__in=ids, status__in=ACTIVE_REVIEWS)
        .order_by()
        .values("organization_id")
        .annotate(total=Count("pk"))
        .values_list("organization_id", "total")
    )
    audit_organizations(user, page.object_list)
    for org in page:
        org.asset_count = asset_counts.get(org.pk, 0)
        org.overdue_count = sum(c.overdue for c in org.contacts.all())
        org.finding_count = finding_counts.get(org.pk, 0)
    return page


@login_required
def inventory(request):
    query = request.GET.get("q", "")[:160].strip()
    orgs = (
        organizations_for(request.user)
        .annotate(inventory_has_records=Exists(Asset.objects.filter(organization_id=OuterRef("pk"))))
        .order_by("-inventory_has_records", "name", "pk")
    )
    if query:
        orgs = orgs.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    page = company_cards(request.user, orgs, request.GET.get("page"))
    main, pending = [], []
    for org in page:
        (pending if not org.inventory_has_records and not org.finding_count and not query else main).append(
            org
        )
    return render(
        request,
        "portal/inventory.html",
        {
            "page": page,
            "query": query,
            "main_orgs": main,
            "pending_orgs": pending,
        },
    )


def _host_inventory_preview(org, query=""):
    from .review_focus import MACHINE_KINDS

    assets = org.assets.filter(source__organization=org, lifecycle="active", kind__in=MACHINE_KINDS)
    if query:
        assets = assets.filter(name__icontains=query)
    try:
        with overview_queries(query_timeout_ms=1500):
            hosts = list(assets.order_by("name", "pk").values("pk", "name", "kind", "missing_since")[:26])
    except OperationalError:
        return {"host_inventory_unavailable": True}
    return {"host_inventory_preview": hosts[:25], "host_inventory_more": len(hosts) > 25}


def _host_context(request, org):
    from .host_overview import overview as host_overview

    started = perf_counter()
    database = None
    try:
        with (
            read_snapshot(),
            overview_queries(query_timeout_ms=5000, budget_ms=12000, planning_limit=4) as database,
        ):
            context = host_overview(request, org)
        return {
            **context,
            "host_database_ms": database.seconds * 1000,
            "host_dbmax_ms": database.slowest * 1000,
        }
    except OperationalError as exc:
        state = getattr(exc.__cause__, "sqlstate", None)
        reason = (
            "request_budget"
            if isinstance(exc, OverviewBudgetExceeded)
            else "query_cancelled"
            if state == "57014"
            else "database"
        )
        logger.warning(
            "Host overview unavailable reason=%s elapsed_ms=%d", reason, (perf_counter() - started) * 1000
        )
        return {
            "host_overview_unavailable": True,
            "host_error_reason": reason,
            "host_database_ms": database.seconds * 1000 if database else 0,
            "host_dbmax_ms": database.slowest * 1000 if database else 0,
            **_host_inventory_preview(org, request.GET.get("host_q", "").strip()[:128]),
        }


@login_required
@never_cache
@require_GET
@analyst_read_snapshot
def hosts(request, slug):
    started = perf_counter()
    org = organization(request, slug)
    try:
        context = _host_context(request, org)
    except ValueError:
        return HttpResponseBadRequest("Unsupported host overview filter or sorting.")
    response = HttpResponse(
        get_template("portal/_host_overview.html").render({"request": request, "org": org, **context}),
        status=503 if context.get("host_overview_unavailable") else 200,
    )
    response["Server-Timing"] = (
        f"hosts;dur={(perf_counter() - started) * 1000:.1f}, "
        f"database;dur={context['host_database_ms']:.1f}, dbmax;dur={context['host_dbmax_ms']:.1f}"
    )
    if context.get("host_overview_unavailable"):
        response["Retry-After"] = "5"
        response["X-Bearings-Host-Error"] = context["host_error_reason"]
    return response


@login_required
@analyst_read_snapshot
def detail(request, slug):
    from .models import OrganizationConfiguration

    started = perf_counter()
    org = organization(request, slug)
    role = org.membership_set.filter(user=request.user).values_list("role", flat=True).first()
    editable = request.user.is_superuser or role in {"admin", "editor"}
    finding_summary = (
        visible_findings(request.user, org)
        .order_by()
        .aggregate(
            total=Count("pk"),
            pending=Count("pk", filter=Q(status__in=["new", "under_review"])),
            confirmed=Count("pk", filter=Q(status="confirmed")),
            accepted_risk=Count("pk", filter=Q(status="accepted_risk")),
            closed=Count("pk", filter=Q(status__in=["resolved", "false_positive"])),
        )
    )
    inventory_started = perf_counter()
    inventory_query = request.GET.get("inventory_q", "").strip()[:128]
    inventory_assets = top_level_assets(org.assets.filter(source__organization=org))
    if inventory_query:
        inventory_assets = inventory_assets.filter(name__icontains=inventory_query)
    extra_software = additional_software_filter()
    inventory_page = Paginator(
        inventory_assets.select_related("source__instance")
        .annotate(upstream_status=F("upstream_data__status"))
        .defer("upstream_data")
        .prefetch_related(
            Prefetch(
                "installations",
                queryset=Installation.objects.filter(extra_software, product__organization=org)
                .select_related("product")
                .annotate(
                    application_priority=Case(
                        When(agent_component__manager="manifest", then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    ),
                    overview_version_stale=Case(
                        When(
                            Q(agent_component__observed_at__lt=timezone.now() - timedelta(hours=12))
                            | Q(agent_component__missing_since__isnull=False)
                            | Q(agent_component__device__enabled=False)
                            | Q(agent_component__device__expires_at__lte=timezone.now()),
                            then=Value(1),
                        ),
                        default=Value(0),
                        output_field=IntegerField(),
                    ),
                )
                .order_by("application_priority", "product__name", "pk")[:3],
                to_attr="software_preview",
            ),
            Prefetch(
                "installations",
                queryset=Installation.objects.filter(product__organization=org, is_operating_system=True)
                .select_related("product")
                .order_by("pk")[:1],
                to_attr="os_preview",
            ),
            Prefetch(
                "agent_devices",
                queryset=AgentDevice.objects.filter(
                    organization=org, source_id=F("asset__source_id"), enabled=True
                ).only("asset_id", "os", "last_observed_at", "expires_at"),
                to_attr="os_devices",
            ),
        )
        .order_by("name", "pk"),
        50,
    ).get_page(request.GET.get("inventory_page"))
    inventory_page.object_list = list(inventory_page.object_list)
    decorate_addresses(inventory_page.object_list, org)
    counts = {
        row["asset_id"]: row
        for row in Installation.objects.filter(
            asset_id__in=[a.pk for a in inventory_page], product__organization=org
        )
        .values("asset_id")
        .annotate(total=Count("pk"), additional=Count("pk", filter=extra_software))
    }
    os_names = {
        "ubuntu": "Ubuntu",
        "debian": "Debian",
        "rhel": "Red Hat Enterprise Linux",
        "centos": "CentOS",
        "rocky": "Rocky Linux",
        "almalinux": "AlmaLinux",
    }
    for asset in inventory_page:
        asset.software_count = counts.get(asset.pk, {}).get("total", 0)
        asset.additional_software_count = counts.get(asset.pk, {}).get("additional", 0)
        asset.additional_software_more = max(0, asset.additional_software_count - len(asset.software_preview))
        asset.overview_os = ""
        asset.overview_os_stale = False
        if asset.os_devices and asset.os_devices[0].os.get("id"):
            device = asset.os_devices[0]
            asset.overview_os = " ".join(
                filter(None, (os_names.get(device.os["id"], device.os["id"]), device.os.get("version", "")))
            )
            asset.overview_os_stale = device.stale or device.expires_at <= timezone.now()
        elif asset.os_preview:
            installed_os = asset.os_preview[0]
            asset.overview_os = " ".join(filter(None, (installed_os.product.name, installed_os.version)))
    inventory_ms = (perf_counter() - inventory_started) * 1000
    # A hash such as #inventory never reaches Django. Load the host cohort
    # independently unless the visitor explicitly requested its filters or page.
    host_context = {}
    if request.GET.keys() & {"host_filter", "host_q", "sort", "direction", "page"}:
        try:
            host_context = _host_context(request, org)
        except ValueError:
            return HttpResponseBadRequest("Unsupported host overview filter or sorting.")
    else:
        host_context = _host_inventory_preview(org)
    render_started = perf_counter()
    response = render(
        request,
        "portal/detail.html",
        {
            "org": org,
            "editable": editable,
            "inventory_writable": editable
            and hasattr(org, "inventory_source")
            and org.inventory_source.can_write,
            "public_keys": OrganizationConfiguration.objects.filter(organization=org)
            .values("pgp_public_key", "smime_certificate")
            .first(),
            "contact_reviewer": request.user.is_superuser or role == "admin",
            "member_admin": role == "admin",
            "operator_reviewer": can_operator_review(request.user, org),
            "finding_summary": finding_summary,
            "contact_page": Paginator(org.contacts.order_by("name", "pk"), 25).get_page(
                request.GET.get("contact_page")
            ),
            "scope_page": Paginator(org.claims.order_by("kind", "value", "pk"), 25).get_page(
                request.GET.get("scope_page")
            ),
            "claim_review_form": ClaimReviewForm(),
            "missing_review_form": MissingReviewForm(),
            "inventory_page": inventory_page,
            "inventory_query": inventory_query,
            **host_context,
        },
    )
    finished = perf_counter()
    response["Server-Timing"] = (
        f"company;dur={(finished - started) * 1000:.1f}, inventory;dur={inventory_ms:.1f}, "
        f"render;dur={(finished - render_started) * 1000:.1f}"
    )
    return response


@login_required
@analyst_read_snapshot
@read_snapshot()
def asset_detail(request, slug, pk):
    from .remediation import notification_access_blocker

    org = organization(request, slug)
    asset = get_object_or_404(
        org.assets.select_related("source__instance", "network_host"),
        pk=pk,
    )
    notification_blocker = notification_access_blocker(request.user, org)
    findings = (
        visible_findings(request.user, org)
        .select_related("installation__asset__source__instance")
        .filter(installation__asset=asset, installation__product__organization=org, record__organization=org)
        .order_by("-evaluated_at", "pk")
    )
    software = (
        asset.installations.filter(product__organization=org)
        .select_related("product", "agent_component__device")
        .order_by("product__name", "pk")
    )
    software_query = request.GET.get("software_q", "")[:128].strip()
    if software_query:
        software = software.filter(
            Q(product__name__icontains=software_query) | Q(product__identifier__icontains=software_query)
        )
    software_page = Paginator(software, 100).get_page(request.GET.get("software_page"))
    from .distro_display import decorate_installations

    software_page.object_list = list(software_page.object_list)
    decorate_installations(request.user, software_page.object_list)
    from .inventory_status import synchronization_status

    agent_device = (
        AgentDevice.objects.filter(asset=asset, organization=org, source_id=asset.source_id)
        .order_by("-enabled", "-created_at")
        .first()
    )
    windows_update = {}
    if agent_device:
        # These identifiers were checked by the scoped device query above.
        agent_device.asset, agent_device.organization, agent_device.source = asset, org, asset.source
    if agent_device and agent_device.os.get("id") == "windows":
        from .windows_updates import presentation

        windows_update = presentation(agent_device)
    asset_attention = attention_for(request.user, asset, agent_device, findings, windows_update)
    review_paginator = Paginator(severity_first(findings), 25)
    if asset_attention:
        review_paginator.count = asset_attention["reviews"]["total"]
    page = review_paginator.get_page(request.GET.get("page"))
    for finding in page:
        decorate_finding(finding)
    return render(
        request,
        "portal/asset.html",
        {
            "org": org,
            "asset": asset,
            "missing_review_form": MissingReviewForm(),
            "can_remediate": asset.lifecycle == "active" and not notification_blocker,
            "notification_blocker": notification_blocker if asset.lifecycle == "active" else "",
            "facts": asset_context(asset, workspace=True),
            "network_host": asset.network_host
            if (
                asset.network_host_id
                and asset.network_host.organization_id == org.pk
                and asset.network_host.source_id == asset.source_id
            )
            else None,
            "assigned_address_page": Paginator(
                assigned_addresses(org).filter(network_host=asset),
                100,
            ).get_page(request.GET.get("address_page")),
            "software_page": software_page,
            "software_query": software_query,
            "agent_device": agent_device,
            "sync_status": synchronization_status(asset, agent_device),
            "windows_update": windows_update,
            "asset_attention": asset_attention,
            "page": page,
            "editable": can_edit(request.user, org),
        },
    )
