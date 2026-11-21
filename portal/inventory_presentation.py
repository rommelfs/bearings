"""Group explicit NetBox address assignments without merging records or assessments."""

from django.db.models import Count, F, Q
from .models import Asset


def top_level_assets(queryset):
    return queryset.exclude(
        Q(
            object_type="ipam.ipaddress",
            network_host__object_type__in=("dcim.device", "virtualization.virtualmachine"),
            network_host__organization_id=F("organization_id"),
            network_host__source_id=F("source_id"),
        )
    )


def assigned_addresses(organization):
    return (
        Asset.objects.filter(
            organization=organization,
            object_type="ipam.ipaddress",
            network_host__organization=organization,
            network_host__source_id=F("source_id"),
        )
        .select_related("source__instance")
        .annotate(
            address_dns=F("upstream_data__dns_name"),
            address_interface=F("upstream_data__assignment__interface"),
        )
        .defer("upstream_data")
        .order_by("name", "pk")
    )


def decorate_addresses(assets, organization):
    """Two bounded queries for a page; no raw inventory blobs or per-card fetches."""
    addresses = assigned_addresses(organization).filter(network_host_id__in=[a.pk for a in assets])
    counts = dict(
        addresses.order_by()
        .values("network_host_id")
        .annotate(total=Count("pk"))
        .values_list("network_host_id", "total")
    )
    # Window slicing via prefetch keeps at most 16 address previews per host.
    from django.db.models import Prefetch, prefetch_related_objects

    prefetch_related_objects(
        assets,
        Prefetch(
            "assigned_addresses", queryset=assigned_addresses(organization)[:16], to_attr="address_preview"
        ),
    )
    for asset in assets:
        asset.assigned_address_count = counts.get(asset.pk, 0)
