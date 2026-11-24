"""Explicit source-owned export. Never adopt by name, allocate prefixes, or delete absent observations."""

import hashlib
import ipaddress
import json
import uuid
import time
from django.conf import settings
from django.urls import reverse
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .access import audit
from .agent_protocol import host_claim
from .agents import current
from .connectors.http import ConnectorError, request_json
from .connectors.netbox import connection, in_scope
from .models import AgentDevice, InventorySource


def policy(value):
    if not isinstance(value, dict) or set(value) != {"inventory", "vrf"} or value["inventory"] is not True:
        raise ConnectorError("Enable an explicit inventory export policy")
    if value["vrf"] is not None and (type(value["vrf"]) is not int or value["vrf"] < 1):
        raise ConnectorError("Select an explicit positive NetBox VRF ID or inventory-only export")
    return value


def one(page):
    if (
        not isinstance(page, dict)
        or type(page.get("count")) is not int
        or page["count"] not in (0, 1)
        or not isinstance(page.get("results"), list)
        or len(page["results"]) != page["count"]
        or "next" not in page
        or page["next"]
    ):
        raise ConnectorError("Ambiguous or incomplete export lookup; reconcile explicitly")
    return page["results"][0] if page["count"] else None


def marker(asset, name):
    return str(uuid.uuid5(asset.pk, name))


def object_id(row):
    if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1:
        raise ConnectorError("Invalid NetBox export object identity")
    return row["id"]


def foreign_key(row, key):
    value = row.get(key)
    return value.get("id") if isinstance(value, dict) else value


def owned(row, identity):
    object_id(row)
    if not isinstance(row.get("custom_fields"), dict) or row["custom_fields"].get("bearings_id") != identity:
        raise ConnectorError("Existing NetBox object has no matching Bearings ownership marker")


def snapshot(device):
    components = list(
        device.components.filter(missing_since__isnull=True)
        .order_by("key")
        .values(
            "key",
            "name",
            "manager",
            "architecture",
            "version",
            "observed_at",
            "last_report_id",
            "package_source",
            "package_identity",
            "binary",
            "manifest",
        )[:5017]
    )
    if len(components) > 5016:
        raise ConnectorError("Inventory exceeds the bounded export; no truncated snapshot published")
    for c in components:
        c["observed_at"] = c["observed_at"].isoformat()
        c["last_report_id"] = str(c["last_report_id"])
    result = {
        "schema": "bearings.netbox.inventory.v1",
        "asset_id": str(device.asset_id),
        "bearings_url": settings.PUBLIC_BASE_URL.rstrip("/")
        + reverse("asset", args=[device.organization.slug, device.asset_id]),
        "source_id": str(device.source_id),
        "device_id": str(device.pk),
        "sequence": device.applied_sequence,
        "observed_at": device.last_observed_at.isoformat(),
        "network_observed_at": (device.network_observed_at or device.created_at).isoformat(),
        "network": device.reported_network,
        "os": device.os,
        "services": device.services,
        "software": components,
        "software_count": len(components),
        "software_scope": "observed_components",
        "last_complete_system_packages_at": device.last_complete_at.isoformat()
        if device.last_complete_at
        else None,
        "assertion": "Authenticated client observations; not independent host attestation or CVE applicability",
    }
    if len(json.dumps(result).encode()) > 1_500_000:
        raise ConnectorError("Inventory exceeds export size budget; no partial snapshot published")
    return result


def export(device):
    source, asset = device.source, device.asset
    rules = policy(source.agent_export_policy)
    if not source.agent_managed or not current(device) or device.stale:
        raise ConnectorError("Managed export requires a current enrolled device and observation")
    if not asset.external_id or asset.state != "synced":
        raise ConnectorError("Host registration must be confirmed before inventory export")
    _, base, headers = connection(source, write=True)
    vm = asset.object_type == "virtualization.virtualmachine"
    if not vm and asset.object_type != "dcim.device":
        raise ConnectorError("Only confirmed NetBox hosts support inventory export")
    if (asset.kind == "vm") != vm:
        raise ConnectorError("NetBox inventory kind changed")

    deadline = time.monotonic() + 60

    def api(method, path, **kwargs):
        if time.monotonic() >= deadline:
            raise ConnectorError("Export time budget exceeded; repeat resumes by stable ownership markers")
        return request_json(method, base + path, headers=headers, deadline=deadline, **kwargs)

    host_path = (
        ("/api/virtualization/virtual-machines/" if vm else "/api/dcim/devices/") + asset.external_id + "/"
    )
    host = api("GET", host_path)
    owned(host, str(asset.pk))
    if str(host["id"]) != asset.external_id or not in_scope(source, host):
        raise ConnectorError("Host tenant or external identity changed")
    payload = snapshot(device)
    network = host_claim(device.reported_network) if device.reported_network else {"addresses": []}
    network_fresh = (device.network_observed_at or device.created_at) >= timezone.now() - timedelta(hours=12)
    interface_count = address_count = 0
    if rules["vrf"] is not None and network_fresh:
        vrf = api("GET", f"/api/ipam/vrfs/{rules['vrf']}/")
        if (
            object_id(vrf) != rules["vrf"]
            or vrf.get("enforce_unique") is not True
            or not in_scope(source, vrf)
        ):
            raise ConnectorError("VRF must belong to this source and enforce unique IP addresses")
        interface_path = "/api/virtualization/interfaces/" if vm else "/api/dcim/interfaces/"
        parent = "virtual_machine" if vm else "device"
        interface_type = "virtualization.vminterface" if vm else "dcim.interface"
        interfaces = {}
        for address in network["addresses"]:
            name = address["interface"]
            if name not in interfaces:
                identity = marker(asset, "interface:" + name)
                row = one(
                    api("GET", interface_path, params={parent + "_id": host["id"], "name": name, "limit": 2})
                )
                if row is None:
                    body = {parent: host["id"], "name": name, "custom_fields": {"bearings_id": identity}}
                    if not vm:
                        body["type"] = "other"
                    row = api("POST", interface_path, json=body)
                owned(row, identity)
                if foreign_key(row, parent) != host["id"] or row.get("name") != name:
                    raise ConnectorError("Interface parent or name changed")
                interfaces[name] = object_id(row)
            parsed = ipaddress.ip_interface(address["address"])
            identity = marker(asset, "address:" + name + ":" + str(parsed.ip))
            path = "/api/ipam/ip-addresses/"
            row = one(
                api("GET", path, params={"vrf_id": rules["vrf"], "address": str(parsed.ip), "limit": 2})
            )
            body = {
                "address": str(parsed),
                "vrf": rules["vrf"],
                "assigned_object_type": interface_type,
                "assigned_object_id": interfaces[name],
                "custom_fields": {"bearings_id": identity},
            }
            if source.tenant_id:
                body["tenant"] = source.tenant_id
            if row is None:
                row = api("POST", path, json=body)
            else:
                owned(row, identity)
                if (
                    not in_scope(source, row)
                    or foreign_key(row, "vrf") != rules["vrf"]
                    or row.get("assigned_object_type") != interface_type
                    or row.get("assigned_object_id") != interfaces[name]
                ):
                    raise ConnectorError("Existing address assignment differs; no reassignment")
                if row.get("address") != str(parsed):
                    row = api("PATCH", path + str(row["id"]) + "/", json={"address": str(parsed)})
            owned(row, identity)
            if (
                not in_scope(source, row)
                or row.get("address") != str(parsed)
                or foreign_key(row, "vrf") != rules["vrf"]
                or row.get("assigned_object_type") != interface_type
                or row.get("assigned_object_id") != interfaces[name]
            ):
                raise ConnectorError("NetBox IP export acknowledgement differs")
            address_count += 1
        interface_count = len(interfaces)
    # Native JSON field retains actual software versions, observation dates and provenance.
    updated = api("PATCH", host_path, json={"custom_fields": {"bearings_inventory": payload}})
    owned(updated, str(asset.pk))
    if (
        updated["id"] != host["id"]
        or not in_scope(source, updated)
        or updated["custom_fields"].get("bearings_inventory") != payload
    ):
        raise ConnectorError("NetBox inventory snapshot acknowledgement differs")
    return {
        "sequence": device.applied_sequence,
        "exported_at": timezone.now().isoformat(),
        "interfaces": interface_count,
        "addresses": address_count,
        "software": payload["software_count"],
        "network": "exported" if rules["vrf"] is not None and network_fresh else "not_exported",
        "network_observed_at": payload["network_observed_at"],
        "inventory_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
    }


def process(pk):
    with transaction.atomic():
        device = (
            AgentDevice.objects.select_for_update(of=("self",))
            .select_related("asset", "organization", "source")
            .get(pk=pk)
        )
        source = InventorySource.objects.select_for_update().get(pk=device.source_id)
        device.source = source
        device.asset.refresh_from_db()
        device.organization.refresh_from_db(fields=["merged_into"])
        if not device.netbox_export_pending or device.netbox_export_after > timezone.now():
            return
        try:
            device.netbox_export_receipt = export(device)
        except ConnectorError as exc:
            # Connector exceptions contain only locally controlled messages or HTTP status, never response bodies.
            device.netbox_export_error = ("NetBox export: " + str(exc) + ". No deletions performed.")[:180]
            device.netbox_export_after = timezone.now() + timedelta(minutes=15)
        except (ValueError, TypeError, KeyError):
            device.netbox_export_error = "NetBox inventory export unconfirmed; malformed or changed inventory requires review. No deletions performed."
            device.netbox_export_after = timezone.now() + timedelta(minutes=15)
        else:
            device.netbox_export_error = ""
            device.netbox_export_pending = False
        device.save(
            update_fields=[
                "netbox_export_receipt",
                "netbox_export_error",
                "netbox_export_after",
                "netbox_export_pending",
            ]
        )
        audit(
            None,
            device.organization,
            "inventory.agent_export",
            device.asset_id,
            confirmed=not device.netbox_export_pending,
            sequence=device.applied_sequence,
        )


def process_pending(limit=5):
    ids = list(
        AgentDevice.objects.filter(netbox_export_pending=True, netbox_export_after__lte=timezone.now())
        .order_by("netbox_export_after")
        .values_list("pk", flat=True)[:limit]
    )
    for pk in ids:
        process(pk)
    return len(ids)
