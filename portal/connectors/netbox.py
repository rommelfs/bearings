from django.conf import settings
from .http import ConnectorError, approved_base, request_json


def write_asset(asset):
    source = asset.source
    if source.mode == "development":
        return "development.asset", f"fixture-{asset.pk}"
    if source.mode != "central" or not source.tenant_id or not settings.NETBOX_TOKEN:
        raise ConnectorError("Central NetBox credentials and tenant mapping are required")
    base = approved_base(settings.NETBOX_URL, getattr(settings, "NETBOX_ALLOW_PRIVATE", False))
    vm = asset.kind == "vm"
    endpoint = "/api/virtualization/virtual-machines/" if vm else "/api/dcim/devices/"
    headers = {"Authorization": f"Token {settings.NETBOX_TOKEN}", "Accept": "application/json"}
    # Operator must provision a text custom field 'bearings_id' on devices and virtual machines.
    # Read-before-retry recovers an accepted POST whose response was lost.
    existing = request_json(
        "GET",
        base + endpoint,
        headers=headers,
        params={"cf_bearings_id": str(asset.pk), "tenant_id": source.tenant_id, "limit": 2},
    )
    if not isinstance(existing.get("results"), list) or "count" not in existing:
        raise ConnectorError("Incomplete NetBox query; reconciliation required")
    if existing.get("next") or existing["count"] != len(existing["results"]) or existing["count"] > 1:
        raise ConnectorError("Ambiguous or partial NetBox query; reconciliation required")
    if existing["results"]:
        record = existing["results"][0]
    else:
        body = {
            "name": asset.name,
            "tenant": source.tenant_id,
            "status": "active" if asset.lifecycle == "active" else "offline",
            "custom_fields": {"bearings_id": str(asset.pk)},
        }
        if not vm:
            for field, value in [
                ("site", settings.NETBOX_SITE_ID),
                ("role", settings.NETBOX_ROLE_ID),
                ("device_type", settings.NETBOX_DEVICE_TYPE_ID),
            ]:
                if not value:
                    raise ConnectorError("Configure NetBox site, role, and device type IDs")
                body[field] = int(value)
        record = request_json("POST", base + endpoint, headers=headers, json=body)
    tenant = record.get("tenant") or {}
    if (
        not record.get("id")
        or not isinstance(tenant, dict)
        or tenant.get("id") != source.tenant_id
        or record.get("custom_fields", {}).get("bearings_id") != str(asset.pk)
    ):
        raise ConnectorError("NetBox identity or tenant mismatch; reconciliation required")
    return ("virtualization.virtualmachine" if vm else "dcim.device"), str(record["id"])
