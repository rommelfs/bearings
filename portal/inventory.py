"""Atomic GET-only NetBox projection. Local assessments are never upstream-owned."""

import ipaddress
from decimal import Decimal, InvalidOperation
import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from .access import audit
from .connectors.http import ConnectorError
from .connectors.netbox import OBJECT_TYPES, query_objects
from .models import Asset, InventorySource, InventoryWrite, NetBoxInstance

KINDS = {"devices": "server", "virtual-machines": "vm", "ip-addresses": "ip_address", "prefixes": "prefix"}
IMPORT_ERROR = "NetBox import failed. Complete inventory retained; check connection, scope, response schema and identity conflicts."


def text(value, maximum=180, *, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ConnectorError("Invalid NetBox inventory field; complete import discarded")
    return value


def project(kind, wrapper):
    row = wrapper["record"]
    if kind in {"ip-addresses", "prefixes"}:
        field = "address" if kind == "ip-addresses" else "prefix"
        value = text(row.get(field), required=True)
        try:
            name = str(
                ipaddress.ip_interface(value)
                if field == "address"
                else ipaddress.ip_network(value, strict=True)
            )
        except ValueError:
            raise ConnectorError("Invalid NetBox address or prefix; complete import discarded") from None
        data = {field: name}
    else:
        name = text(row.get("name"), required=True)
        data = {"name": name}
    status = row.get("status", {})
    if isinstance(status, dict):
        status = status.get("value", "")
    data["status"] = text(status, 40)
    # Deliberately retain a small allowlist, never arbitrary custom fields or upstream URLs.
    for field in ["site", "location", "rack", "role", "device_type", "cluster", "vrf", "platform", "tenant"]:
        value = row.get(field)
        if value is not None:
            if kind == "ip-addresses" and field == "role" and isinstance(value, dict):
                data[field] = text(value.get("value"), 40)
                continue
            if not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] < 1:
                raise ConnectorError("Invalid NetBox reference; complete import discarded")
            data[field] = {"id": value["id"], "name": text(value.get("name", value.get("display", "")))}
    for field in ["primary_ip4", "primary_ip6"]:
        value = row.get(field)
        if value is not None:
            try:
                data[field] = str(ipaddress.ip_interface(text(value.get("address"), required=True)))
                if ipaddress.ip_interface(data[field]).version != (4 if field == "primary_ip4" else 6):
                    raise ConnectorError("Primary IP family mismatch; complete import discarded")
                if value.get("id") is not None:
                    if type(value["id"]) is not int or value["id"] < 1:
                        raise ConnectorError("Invalid primary IP identity; complete import discarded")
                    data[field + "_id"] = value["id"]
            except (ValueError, AttributeError):
                raise ConnectorError("Invalid primary IP; complete import discarded") from None
    for field in ["serial", "asset_tag", "dns_name"]:
        if row.get(field) is not None:
            data[field] = text(row[field], 255)
    if row.get("position") is not None:
        try:
            position = Decimal(str(row["position"]))
            if not position.is_finite() or not 0 <= position <= 10000:
                raise InvalidOperation
            data["position"] = format(position.normalize(), "f")
        except (InvalidOperation, ValueError):
            raise ConnectorError("Invalid rack position; complete import discarded") from None
    if row.get("face") is not None:
        face = row["face"]
        data["face"] = text(face.get("value") if isinstance(face, dict) else face, 20)
    custom = row.get("custom_fields", {})
    if not isinstance(custom, dict):
        raise ConnectorError("Invalid custom fields; complete import discarded")
    marker = custom.get("bearings_id")
    try:
        marker = uuid.UUID(marker) if isinstance(marker, str) else None
    except ValueError:
        marker = None
    return name, data, marker


def refresh_inventory(source_id, *, due=False):
    """Commit a complete source snapshot or safe failure while holding its lock.

    The nested savepoint rolls back projections without releasing the source lock,
    so an older failure cannot overwrite the health of a newer concurrent import.
    """
    failed = False
    with transaction.atomic():
        source = InventorySource.objects.select_for_update().get(pk=source_id)
        now = timezone.now()
        if (
            due
            and not source.import_requested
            and (
                not source.import_enabled
                or (
                    source.last_import_attempt
                    and now - source.last_import_attempt < timedelta(minutes=source.import_interval_minutes)
                )
            )
        ):
            return None
        try:
            with transaction.atomic():
                counts = refresh_locked(source, now)
        except (ConnectorError, ValidationError, IntegrityError):
            source.refresh_from_db()
            source.last_import_attempt, source.import_error, source.import_requested = (
                now,
                IMPORT_ERROR,
                False,
            )
            source.save(update_fields=["last_import_attempt", "import_error", "import_requested"])
            audit(None, source.organization, "inventory.import_failed", source.pk)
            failed = True
    if failed:
        raise ConnectorError(IMPORT_ERROR) from None
    return counts


def refresh_locked(source, now):
    if source.mode not in {"central", "external"} or not source.instance_id:
        raise ConnectorError("A configured live NetBox source is required")
    instance = NetBoxInstance.objects.select_for_update().get(pk=source.instance_id)
    if not instance.enabled:
        raise ConnectorError("NetBox instance is disabled")
    result = {kind: query_objects(source, kind) for kind in OBJECT_TYPES}
    # Validate the entire snapshot before any local projection changes.
    prepared = [(kind, row, *project(kind, row)) for kind, rows in result.items() for row in rows]
    # Resolve DNS only by the primary IP's source-local ID within this complete scoped IP snapshot.
    ips = {row["external_id"]: data for kind, row, name, data, marker in prepared if kind == "ip-addresses"}
    for kind, row, name, data, marker in prepared:
        if kind not in {"devices", "virtual-machines"}:
            continue
        for field in ["primary_ip4", "primary_ip6"]:
            ip = ips.get(str(data.get(field + "_id")))
            if ip and ip.get("address") == data.get(field) and ip.get("dns_name"):
                data[field + "_dns_name"] = ip["dns_name"]
            if ip and ip.get("address") == data.get(field) and ip.get("vrf"):
                data[field + "_vrf"] = ip["vrf"]
    counts = dict(
        created=0, updated=0, unchanged=0, missing=0, reappeared=0, reconciled=0, total=len(prepared)
    )
    seen = []
    for kind, row, name, data, marker in prepared:
        identity = dict(source=source, object_type=row["object_type"], external_id=row["external_id"])
        asset = Asset.objects.filter(**identity).first()
        pending = (
            Asset.objects.filter(pk=marker, source=source, organization_id=source.organization_id).first()
            if marker
            else None
        )
        if pending and (
            pending.pk != getattr(asset, "pk", None)
            or InventoryWrite.objects.filter(asset=pending, completed_at__isnull=True).exists()
        ):
            if (
                (asset and asset.pk != pending.pk)
                or (pending.external_id and pending.external_id != row["external_id"])
                or kind not in {"devices", "virtual-machines"}
                or (pending.kind == "vm") != (kind == "virtual-machines")
                or pending.kind in {"ip_address", "prefix"}
                or not InventoryWrite.objects.filter(asset=pending, completed_at__isnull=True).exists()
            ):
                raise ConnectorError("NetBox identity conflict; complete import discarded")
            asset = pending
            asset.object_type, asset.external_id, asset.state = (
                row["object_type"],
                row["external_id"],
                "synced",
            )
            InventoryWrite.objects.filter(asset=asset).update(completed_at=now, error="")
            counts["reconciled"] += 1
        created = asset is None
        if created:
            asset = Asset(
                organization_id=source.organization_id, kind=KINDS[kind], state="synced", **identity
            )
            counts["created"] += 1
        elif asset.organization_id != source.organization_id:
            raise ConnectorError("Local inventory ownership conflict")
        elif asset.name != name or asset.upstream_data != data:
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
        if asset.missing_since:
            counts["reappeared"] += 1
        asset.name, asset.upstream_data, asset.inventory_seen_at = name, data, now
        asset.missing_since = asset.missing_reviewed_at = None
        asset.missing_review_reason = ""
        # Keep local kind refinements, lifecycle, criticality, team, software and findings.
        asset.full_clean()
        asset.save()
        seen.append(asset.pk)
    missing = (
        source.asset_set.filter(object_type__in=[v[1] for v in OBJECT_TYPES.values()], state="synced")
        .exclude(external_id="")
        .exclude(pk__in=seen)
    )
    counts["missing"] = missing.count()
    missing.filter(missing_since__isnull=True).update(
        missing_since=now, missing_reviewed_at=None, missing_review_reason=""
    )
    source.last_import_attempt, source.last_import_success = now, timezone.now()
    source.import_error, source.import_requested, source.import_summary = "", False, counts
    source.save(
        update_fields=[
            "last_import_attempt",
            "last_import_success",
            "import_error",
            "import_requested",
            "import_summary",
        ]
    )
    audit(None, source.organization, "inventory.imported", source.pk, **counts)
    return counts


def due_sources():
    # Recheck due status under each source lock; multiple workers cannot import twice.
    return InventorySource.objects.filter(mode__in=["central", "external"], instance__enabled=True).filter(
        Q(import_enabled=True) | Q(import_requested=True)
    )
