"""Group explicit NetBox address assignments without merging records or assessments."""

from django.db.models import Count, F, Q, Window
from .models import Asset


def grouped_address_filter():
    return Q(
        object_type="ipam.ipaddress",
        network_host__object_type__in=("dcim.device", "virtualization.virtualmachine"),
        network_host__organization_id=F("organization_id"),
        network_host__source_id=F("source_id"),
    )


def top_level_assets(queryset):
    return queryset.exclude(grouped_address_filter())


def assigned_addresses(organization=None):
    # Without an organization this is only a base for a pre-authorized host-ID
    # batch, never an authorization boundary or a directly rendered query.
    addresses = Asset.objects.filter(
        network_host__object_type__in=("dcim.device", "virtualization.virtualmachine"),
        network_host__organization_id=F("organization_id"),
        object_type="ipam.ipaddress",
        network_host__source_id=F("source_id"),
    )
    if organization is not None:
        addresses = addresses.filter(organization=organization)
    return (
        addresses.select_related("source__instance")
        .annotate(
            address_dns=F("upstream_data__dns_name"),
            address_interface=F("upstream_data__assignment__interface"),
        )
        .defer("upstream_data")
        .order_by("name", "pk")
    )


def decorate_addresses(assets, organization=None):
    """One bounded query for a page; no raw inventory blobs or per-card fetches."""
    if not assets:
        return
    from django.db.models import Prefetch, prefetch_related_objects

    addresses = assigned_addresses(organization).annotate(
        assignment_total=Window(expression=Count("pk"), partition_by=[F("network_host_id")])
    )
    # Count over the full partition before prefetch's per-host window slice.
    prefetch_related_objects(
        assets,
        Prefetch("assigned_addresses", queryset=addresses[:16], to_attr="address_preview"),
    )
    for asset in assets:
        asset.assigned_address_count = (
            asset.address_preview[0].assignment_total if asset.address_preview else 0
        )


def host_network_summary(asset):
    """Use only already-prefetched assignments; never look up DNS or infer ownership."""
    import ipaddress
    from django.urls import reverse
    from .asset_context import asset_context, label

    context = asset_context(asset)
    for entry in context["addresses"]:
        entry["primary"] = True
        entry["last_known"] = bool(asset.missing_since)
    for address in getattr(asset, "address_preview", ()):
        try:
            parsed = ipaddress.ip_interface(address.name)
        except ValueError:
            continue
        url = address.source_url
        entry = next((item for item in context["addresses"] if url and item["url"] == url), None)
        if entry is None:
            entry = {"address": str(parsed.ip), "prefix": str(parsed), "url": url, "primary": False}
            context["addresses"].append(entry)
        entry.update(
            workspace_url=reverse("asset", args=[asset.organization.slug, address.pk]),
            last_known=bool(address.missing_since or asset.missing_since),
            lifecycle=address.lifecycle,
        )
        dns = label(address.address_dns)
        if dns and not any(item["name"] == dns for item in context["dns_names"]):
            context["dns_names"].append({"name": dns, "url": url})
    context["assigned_address_count"] = getattr(asset, "assigned_address_count", 0)
    context["addresses_truncated"] = context["assigned_address_count"] > 16
    return context


def additional_software_filter():
    """Overview classification only; package monitoring/inventory remain complete."""
    return Q(is_operating_system=False) & ~(
        Q(product__identifier__startswith="pkg:deb/")
        | Q(product__identifier__startswith="pkg:rpm/")
        | Q(agent_component__manager__in=("dpkg", "rpm"))
    )
