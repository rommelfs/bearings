"""Recorded distro-check summaries, kept separate from product-watch freshness."""

from datetime import timedelta
from django.db.models import Count, Exists, F, Max, OuterRef, Q
from django.utils import timezone
from .models import AgentComponent, AgentDevice, AgentReport


def package_reporters(org_ids):
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
