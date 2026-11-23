"""Recorded distro-check summaries, kept separate from product-watch freshness."""

from datetime import timedelta
from django.db.models import Case, Count, Exists, F, IntegerField, Max, OuterRef, Q, Value, When, Window
from django.utils import timezone
from django.db.models.functions import RowNumber
from .models import AgentComponent, AgentDevice, AgentReport


def reporter_query(org_ids):
    now = timezone.now()
    components = AgentComponent.objects.filter(
        device_id=OuterRef("pk"),
        manager__in=("dpkg", "rpm"),
        missing_since__isnull=True,
        installation__asset_id=OuterRef("asset_id"),
        installation__asset__source_id=OuterRef("source_id"),
        installation__product__organization_id=OuterRef("organization_id"),
    ).filter(
        Q(installation__product__identifier__startswith="pkg:deb/")
        | Q(installation__product__identifier__startswith="pkg:rpm/")
    )
    devices = AgentDevice.objects.filter(
        organization_id__in=org_ids,
        enabled=True,
        asset__lifecycle="active",
        asset__organization_id=F("organization_id"),
        source__organization_id=F("organization_id"),
        asset__source_id=F("source_id"),
    ).filter(Exists(components))
    queued = Q(distro_requested=True) | Q(
        Exists(AgentReport.objects.filter(device_id=OuterRef("pk"), status="pending"))
    )
    unavailable = (
        Q(expires_at__lte=now)
        | Q(last_observed_at__isnull=True)
        | Q(last_observed_at__lt=now - timedelta(hours=12))
    )
    uncertain = (
        Q(distro_checked_at__isnull=True)
        | Q(distro_summary__state__isnull=True)
        | ~Q(distro_summary__state="ready")
    )
    return devices, queued, unavailable, uncertain


def package_reporters(org_ids):
    devices, queued, unavailable, uncertain = reporter_query(org_ids)
    return {
        row.pop("organization_id"): row
        for row in devices.order_by()
        .values("organization_id")
        .annotate(
            package_clients=Count("pk"),
            package_queued=Count("pk", filter=queued),
            package_unavailable=Count("pk", filter=unavailable),
            package_errors=Count("pk", filter=Q(distro_summary__state="error")),
            package_uncertain=Count("pk", filter=uncertain),
            package_last_attempt=Max("distro_checked_at"),
        )
    }


def attention_devices(org_ids):
    """Three concrete problematic package reporters per company, in one scoped query."""
    devices, _, unavailable, uncertain = reporter_query(org_ids)
    priority = Case(
        When(distro_summary__state="error", then=Value(0)),
        When(unavailable, then=Value(1)),
        When(distro_summary__state="partial", distro_summary__missing_source_metadata__gt=0, then=Value(2)),
        When(distro_summary__state="partial", then=Value(3)),
        default=Value(2),
        output_field=IntegerField(),
    )
    devices = (
        devices.filter(Q(distro_summary__state="error") | unavailable | uncertain)
        .annotate(
            attention_position=Window(
                RowNumber(), partition_by=[F("organization_id")], order_by=[priority.asc(), F("pk").asc()]
            )
        )
        .filter(attention_position__lte=3)
        .select_related("asset")
        .only(
            "organization_id",
            "asset__name",
            "source_id",
            "expires_at",
            "last_observed_at",
            "last_received_at",
            "distro_summary",
            "distro_checked_at",
        )
        .order_by("organization_id", "attention_position")
    )
    grouped = {}
    for device in devices:
        grouped.setdefault(device.organization_id, []).append(device)
    return grouped
