import os
import re
from urllib.parse import parse_qs, urlsplit
from .http import ConnectorError, approved_base, request_json
from ..models import NetBoxInstance


OBJECT_TYPES = {
    "devices": ("/api/dcim/devices/", "dcim.device"),
    "virtual-machines": ("/api/virtualization/virtual-machines/", "virtualization.virtualmachine"),
    "ip-addresses": ("/api/ipam/ip-addresses/", "ipam.ipaddress"),
    "prefixes": ("/api/ipam/prefixes/", "ipam.prefix"),
}


def connection(source, *, write=False):
    if source.mode not in {"central", "external"} or not source.instance_id:
        raise ConnectorError("Configure a NetBox instance for this source")
    instance = NetBoxInstance.objects.get(pk=source.instance_id)
    if instance.access_mode not in {"read_only", "read_write"} or instance.auth_scheme not in {
        "Token",
        "Bearer",
    }:
        raise ConnectorError("Invalid operator NetBox capability or authentication configuration")
    if not instance.enabled:
        raise ConnectorError("NetBox instance is disabled")
    if write and instance.access_mode != "read_write":
        raise ConnectorError("NetBox instance is read-only; inventory writes are denied")
    if instance.organization_id and instance.organization_id != source.organization_id:
        raise ConnectorError("Dedicated instance belongs to a different organization")
    if source.tenant_id is not None and source.tenant_id < 1:
        raise ConnectorError("NetBox tenant ID must be positive")
    if source.tenant_id is None and instance.organization_id != source.organization_id:
        raise ConnectorError("Shared instances require an explicit tenant-scoped binding")
    if not re.fullmatch(r"NETBOX_[A-Z0-9_]*TOKEN", instance.token_env_var):
        raise ConnectorError("Configure a NetBox-specific credential reference")
    token = os.environ.get(instance.token_env_var)
    if not token:
        raise ConnectorError("NetBox credential binding is not set")
    base = approved_base(instance.base_url, instance.allow_private)
    return instance, base, {"Authorization": f"{instance.auth_scheme} {token}", "Accept": "application/json"}


def in_scope(source, record):
    tenant = record.get("tenant") or {}
    return not source.tenant_id or (
        isinstance(tenant, dict) and type(tenant.get("id")) is int and tenant.get("id") == source.tenant_id
    )


def query_objects(source, object_type="devices"):
    """Read complete, bounded pages from ONE authorized instance/binding. Never follow arbitrary URLs."""
    if object_type not in OBJECT_TYPES:
        raise ConnectorError("Unsupported NetBox object type")
    _, base, headers = connection(source)
    path, canonical_type = OBJECT_TYPES[object_type]
    url = base + path
    scope = {"tenant_id": source.tenant_id} if source.tenant_id else {}
    records, identities, expected_count = [], set(), None
    for _ in range(100):
        offset = len(records)
        page = request_json("GET", url, headers=headers, params={**scope, "limit": 100, "offset": offset})
        count, rows = page.get("count"), page.get("results")
        if (
            type(count) is not int
            or count < 0
            or count > 10000
            or not isinstance(rows, list)
            or "next" not in page
        ):
            raise ConnectorError("Incomplete or oversized NetBox page; query discarded")
        if expected_count is None:
            expected_count = count
        if count != expected_count:
            raise ConnectorError("NetBox changed during pagination; retry a complete query")
        for row in rows:
            if (
                not isinstance(row, dict)
                or type(row.get("id")) is not int
                or row["id"] < 1
                or not in_scope(source, row)
            ):
                raise ConnectorError("NetBox identity or tenant mismatch; query discarded")
            if row["id"] in identities:
                raise ConnectorError("Duplicate NetBox identity across pages; query discarded")
            identities.add(row["id"])
            records.append(
                {
                    "source_id": str(source.pk),
                    "instance_id": str(source.instance_id),
                    "object_type": canonical_type,
                    "external_id": str(row["id"]),
                    "record": row,
                }
            )
        if len(records) > count:
            raise ConnectorError("Inconsistent NetBox page count; query discarded")
        next_url = page.get("next")
        if not next_url:
            if len(records) != count:
                raise ConnectorError("Missing NetBox pages; query discarded")
            return records
        if not rows or len(records) >= count or not isinstance(next_url, str):
            raise ConnectorError("Inconsistent NetBox pagination; query discarded")
        # Validate continuation without forwarding credentials to it. Reconstruct our own next GET.
        try:
            next_parts, original = urlsplit(next_url), urlsplit(url)
        except ValueError:
            raise ConnectorError("Invalid NetBox continuation URL; query discarded") from None
        if (next_parts.scheme, next_parts.netloc, next_parts.path) != (
            original.scheme,
            original.netloc,
            original.path,
        ) or next_parts.fragment:
            raise ConnectorError("NetBox pagination changed destination; query discarded")
        params = parse_qs(next_parts.query)
        expected = {
            "limit": ["100"],
            "offset": [str(len(records))],
            **{k: [str(v)] for k, v in scope.items()},
        }
        if params != expected:
            raise ConnectorError("NetBox pagination changed scope or offset; query discarded")
    raise ConnectorError("NetBox page limit reached; query discarded")


def write_asset(asset):
    if asset.kind in {"ip_address", "prefix"}:
        raise ConnectorError("IP addresses and prefixes are imported only; portal writes are unsupported")
    source = asset.source
    if source.mode == "development" and not source.instance_id:
        return "development.asset", f"fixture-{asset.pk}"
    instance, base, headers = connection(source, write=True)
    vm = asset.kind == "vm"
    endpoint = "/api/virtualization/virtual-machines/" if vm else "/api/dcim/devices/"
    # Operator must provision a text custom field 'bearings_id' on devices and virtual machines.
    # Read-before-retry recovers an accepted POST whose response was lost.
    existing = request_json(
        "GET",
        base + endpoint,
        headers=headers,
        params={
            "cf_bearings_id": str(asset.pk),
            "limit": 2,
            **({"tenant_id": source.tenant_id} if source.tenant_id else {}),
        },
    )
    if (
        not isinstance(existing.get("results"), list)
        or type(existing.get("count")) is not int
        or existing["count"] < 0
        or "next" not in existing
    ):
        raise ConnectorError("Incomplete NetBox query; reconciliation required")
    if existing.get("next") or existing["count"] != len(existing["results"]) or existing["count"] > 1:
        raise ConnectorError("Ambiguous or partial NetBox query; reconciliation required")
    if existing["results"]:
        record = existing["results"][0]
    else:
        body = {
            "name": asset.name,
            "status": "active" if asset.lifecycle == "active" else "offline",
            "custom_fields": {"bearings_id": str(asset.pk)},
        }
        if source.tenant_id:
            body["tenant"] = source.tenant_id
        if vm and instance.site_id:
            body["site"] = instance.site_id
        if not vm:
            for field, value in [
                ("site", instance.site_id),
                ("role", instance.role_id),
                ("device_type", instance.device_type_id),
            ]:
                if not value:
                    raise ConnectorError("Configure NetBox site, role, and device type IDs")
                body[field] = int(value)
        record = request_json("POST", base + endpoint, headers=headers, json=body)
    if (
        not isinstance(record, dict)
        or type(record.get("id")) is not int
        or record["id"] < 1
        or not in_scope(source, record)
        or not isinstance(record.get("custom_fields"), dict)
        or record["custom_fields"].get("bearings_id") != str(asset.pk)
    ):
        raise ConnectorError("NetBox identity or tenant mismatch; reconciliation required")
    return ("virtualization.virtualmachine" if vm else "dcim.device"), str(record["id"])
