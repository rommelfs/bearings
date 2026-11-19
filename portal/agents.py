"""Device-owned observations and explicit software projection; never writes upstream or closes findings."""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from urllib.parse import quote
from django.core.exceptions import ValidationError
from django.db import transaction, OperationalError
from django.utils import timezone
from .access import audit, require, role_for
from .agent_protocol import public_key, package_scope, report_data, identifier
from .models import (
    AgentEnrollment,
    AgentDevice,
    AgentReport,
    AgentComponent,
    Organization,
    Installation,
    Product,
    ProductWatch,
    InventorySource,
    CSVAssetBinding,
    Asset,
    InventoryWrite,
)


def administrator(user, org):
    return user.is_active and not org.merged_into_id and (user.is_superuser or role_for(user, org) == "admin")


def current(device):
    return (
        device.enabled
        and device.expires_at > timezone.now()
        and not device.organization.merged_into_id
        and device.asset.organization_id == device.organization_id
        and device.asset.source_id == device.source_id
        and device.source.organization_id == device.organization_id
        and device.asset.lifecycle == "active"
    )


@transaction.atomic
def create_enrollment(actor, org, asset, key, new_asset_kind=""):
    Organization.objects.select_for_update(of=("self",)).get(pk=org.pk)
    require(administrator(actor, org))
    public_key(key)
    if asset is None:
        source = InventorySource.objects.filter(organization=org).first()
        if source is None:
            raise ValidationError("Configure an inventory source before enrolling a new host")
        require(source.can_write and new_asset_kind in {"vm", "server", "desktop", "laptop"})
    else:
        require(
            asset.organization_id == org.pk
            and asset.source.organization_id == org.pk
            and asset.lifecycle == "active"
        )
        source = asset.source
        new_asset_kind = ""
    if asset is not None and AgentDevice.objects.filter(asset=asset, enabled=True).exists():
        raise ValidationError("Revoke the existing device before enrolling a replacement")
    if AgentDevice.objects.filter(public_key=key).exists():
        raise ValidationError("Create a fresh key for this enrollment; never reuse a revoked key")
    secret = secrets.token_urlsafe(32)
    grant = AgentEnrollment.objects.create(
        organization=org,
        asset=asset,
        source=source,
        new_asset_kind=new_asset_kind,
        created_by=actor,
        public_key=key,
        token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    audit(
        actor,
        org,
        "agent.enrollment_created",
        grant.pk,
        asset=str(asset.pk) if asset else "new-host",
        fingerprint=hashlib.sha256(public_key(key).public_bytes_raw()).hexdigest(),
    )
    return grant, f"{grant.pk}.{secret}"


@transaction.atomic
def redeem(grant_id, secret, raw, signature_input, signature, request_url):
    grant = (
        AgentEnrollment.objects.select_for_update(of=("self",))
        .select_related("organization", "asset__source", "created_by")
        .get(pk=grant_id)
    )
    if (
        not hmac.compare_digest(grant.token_hash, hashlib.sha256(secret.encode()).hexdigest())
        or grant.expires_at <= timezone.now()
        or not administrator(grant.created_by, grant.organization)
    ):
        raise ValueError("Enrollment unavailable")
    data = json.loads(raw)
    if (
        set(data) not in ({"schema", "request_id"}, {"schema", "request_id", "host"})
        or data["schema"] != "bearings.agent.enroll.v1"
    ):
        raise ValueError("Invalid enrollment")
    identifier(data["request_id"])
    digest = hashlib.sha256(raw).hexdigest()
    if grant.used_at:
        if grant.request_hash != digest:
            raise ValueError("Grant already used")
        device = AgentDevice.objects.select_related("organization", "asset", "source").get(pk=grant.device_id)
        if not current(device):
            raise ValueError("Device unavailable")
        return device
    # Serialize replacement against concurrent grants for this same asset.
    source = InventorySource.objects.select_for_update(of=("self",)).get(pk=grant.source_id)
    network = {}
    if "host" in data:
        from .agent_protocol import host_claim

        network = host_claim(data["host"])
    if grant.asset_id is None:
        if not network or not source.can_write or source.organization_id != grant.organization_id:
            raise ValueError("New-host registration unavailable")
        if Asset.objects.filter(organization=grant.organization, name__iexact=network["hostname"]).exists():
            raise ValueError("Existing hostname requires explicit asset selection; never auto-merge")
        asset = Asset(
            organization=grant.organization,
            source=source,
            name=network["hostname"],
            kind=grant.new_asset_kind,
            object_type="virtualization.virtualmachine" if grant.new_asset_kind == "vm" else "dcim.device",
            state="recorded" if source.mode == "manual" else "pending",
        )
        asset.full_clean()
        asset.save()
        if source.mode != "manual":
            InventoryWrite.objects.create(asset=asset)
        grant.asset = asset
        grant.save(update_fields=["asset"])
        audit(
            grant.created_by,
            grant.organization,
            "agent.host_submitted",
            asset.pk,
            network="self-reported",
            source=str(source.pk),
        )
    else:
        grant.asset.refresh_from_db()
    if (
        grant.asset.source_id != source.pk
        or grant.asset.organization_id != grant.organization_id
        or source.organization_id != grant.organization_id
        or grant.asset.lifecycle != "active"
    ):
        raise ValueError("Asset or source changed")
    device = AgentDevice(
        id=grant.device_id,
        organization=grant.organization,
        asset=grant.asset,
        source=grant.source,
        public_key=grant.public_key,
        reported_network=network,
        expires_at=timezone.now() + timedelta(days=90),
    )
    device.full_clean()
    device.save()
    grant.used_at = timezone.now()
    grant.request_hash = digest
    grant.signed_body = raw
    grant.signature_input = signature_input
    grant.signature = signature
    grant.request_url = request_url
    grant.save(
        update_fields=[
            "used_at",
            "request_hash",
            "signed_body",
            "signature_input",
            "signature",
            "request_url",
        ]
    )
    audit(
        grant.created_by,
        grant.organization,
        "agent.enrolled",
        device.pk,
        asset=str(device.asset_id),
        credential_days=90,
    )
    return device


@transaction.atomic
def receive(device_id, raw, signature_input, signature, request_url, content_type):
    device = (
        AgentDevice.objects.select_for_update(of=("self",))
        .select_related("organization", "asset", "source")
        .get(pk=device_id)
    )
    if not current(device):
        raise ValueError("Device unavailable")
    from .agent_protocol import decode

    data = decode(raw)
    observed = report_data(data)
    digest = hashlib.sha256(raw).hexdigest()
    existing = AgentReport.objects.filter(pk=data["report_id"]).first()
    if existing:
        if existing.device_id != device.pk or not hmac.compare_digest(existing.body_hash, digest):
            raise ValueError("Report identity conflict")
        return existing
    if data["sequence"] <= device.last_sequence:
        raise ValueError("Sequence replay; explicit recovery required")
    today = timezone.now().date()
    if not device.last_received_at or device.last_received_at.date() != today:
        device.daily_bytes = device.daily_reports = 0
    if device.daily_reports >= 200 or device.daily_bytes + len(raw) > 32 * 1024 * 1024:
        raise OverflowError("Daily device admission budget exceeded")
    if device.last_received_at and timezone.now() - device.last_received_at < timedelta(seconds=10):
        raise OverflowError("Reports must be at least ten seconds apart")
    if device.reports.filter(status="pending").count() >= 10:
        raise OverflowError("Pending queue full")
    row = AgentReport.objects.create(
        id=data["report_id"],
        device=device,
        sequence=data["sequence"],
        observed_at=observed,
        body=raw,
        body_hash=digest,
        signature_input=signature_input,
        signature=signature,
        request_url=request_url,
        content_type=content_type,
        public_key=device.public_key,
        component_count=len(data["components"]),
    )
    device.daily_reports += 1
    device.daily_bytes += len(raw)
    device.last_sequence = data["sequence"]
    device.last_received_at = timezone.now()
    device.save(update_fields=["last_sequence", "last_received_at", "daily_reports", "daily_bytes"])
    return row


def receipt(row):
    return {
        "schema": "bearings.agent.receipt.v1",
        "report_id": str(row.pk),
        "sequence": row.sequence,
        "body_sha256": row.body_hash,
        "status": row.status,
        "error": row.error,
        "received_at": row.received_at.isoformat(),
    }


def _version_changed(component, installation):
    if (
        installation.asset_id != component.device.asset_id
        or installation.product.organization_id != component.device.organization_id
    ):
        raise ValidationError("Installation ownership changed")
    return (
        component.observed_at >= timezone.now() - timedelta(hours=12)
        and installation.version != component.version
    )


def _project(component, installation):
    if _version_changed(component, installation):
        installation.version = component.version
        installation.full_clean()
        installation.save(update_fields=["version"])
        ProductWatch.objects.filter(product_id=installation.product_id).update(requested=True)


@transaction.atomic
def process_one(device_id, report_id):
    device = (
        AgentDevice.objects.select_for_update(of=("self",))
        .select_related("organization", "asset", "source")
        .get(pk=device_id)
    )
    row = AgentReport.objects.select_for_update(of=("self",)).get(pk=report_id, device=device)
    if row.status != "pending":
        return row
    if not current(device):
        row.status = "rejected"
        row.error = "Device revoked, expired or source changed"
    elif row.sequence <= device.applied_sequence:
        row.status = "superseded"
        row.error = "A newer observation has already been applied"
    elif device.last_observed_at and row.observed_at < device.last_observed_at:
        row.status = "rejected"
        row.error = "Observation clock moved backwards; explicit review required"
    else:
        InventorySource.objects.select_for_update(of=("self",)).get(pk=device.source_id)
        device.asset.refresh_from_db()
        if not current(device):
            row.status = "rejected"
            row.error = "Source changed"
        else:
            data = json.loads(bytes(row.body))
            report_data(data)
            previous = {c.key: c for c in device.components.select_related("installation__product", "device")}
            creates = []
            updates = []
            installation_updates = []
            watched_products = set()
            seen = set()
            for value in data["components"]:
                c = previous.get(value["key"])
                if c is None:
                    c = AgentComponent(device=device, key=value["key"])
                    creates.append(c)
                else:
                    updates.append(c)
                for field in ("name", "manager", "architecture", "version"):
                    setattr(c, field, value[field])
                c.observed_at = row.observed_at
                c.missing_since = None
                c.last_report = row
                seen.add(c.key)
                if c.installation_id and _version_changed(c, c.installation):
                    # The report schema already validates the sole owned field (version).
                    # Ownership is checked above; no per-row FK lookup or watch update is needed.
                    c.installation.version = c.version
                    installation_updates.append(c.installation)
                    watched_products.add(c.installation.product_id)
            AgentComponent.objects.bulk_create(creates, batch_size=250)
            AgentComponent.objects.bulk_update(
                updates,
                ["name", "manager", "architecture", "version", "observed_at", "missing_since", "last_report"],
                batch_size=250,
            )
            Installation.objects.bulk_update(installation_updates, ["version"], batch_size=250)
            if watched_products:
                ProductWatch.objects.filter(product_id__in=watched_products).update(requested=True)
            if data["complete"]:
                manager = data["components"][0]["manager"]
                missing = [
                    c.pk
                    for c in previous.values()
                    if c.manager == manager
                    and c.key not in seen
                    and package_scope(c.name, data["scope"])
                    and c.missing_since is None
                ]
                AgentComponent.objects.filter(pk__in=missing).update(missing_since=row.observed_at)
            device.os = data["os"]
            runtime = {s["name"]: s for s in device.services}
            for value in data["services"]:
                runtime[value["name"]] = {**value, "observed_at": row.observed_at.isoformat()}
            device.services = list(runtime.values())
            if data["complete"] and data["scope"] == "system-packages":
                device.last_complete_at = row.observed_at
            device.last_observed_at = row.observed_at
            device.applied_sequence = row.sequence
            device.save(
                update_fields=["os", "services", "last_observed_at", "last_complete_at", "applied_sequence"]
            )
            row.status = "applied"
    row.processed_at = timezone.now()
    row.save(update_fields=["status", "error", "processed_at"])
    return row


def process_pending(limit=25):
    total = 0
    # Each device lock serializes publication and revocation; duplicate workers are harmless.
    for device_id, pk in (
        AgentReport.objects.filter(status="pending")
        .order_by("received_at", "sequence")
        .values_list("device_id", "pk")[:limit]
    ):
        try:
            process_one(device_id, pk)
            total += 1
        except (ValidationError, ValueError):
            AgentReport.objects.filter(pk=pk, status="pending").update(
                status="rejected",
                error="Invalid observation or changed software ownership; review required",
                processed_at=timezone.now(),
            )
        except OperationalError:
            # Rollback retains pending input. Database outage/deadlock cannot publish a partial state.
            continue
    return total


@transaction.atomic
def bind(actor, org, component_id, installation_id=None, create=False):
    component = AgentComponent.objects.select_related("device").get(pk=component_id, device__organization=org)
    device = (
        AgentDevice.objects.select_for_update(of=("self",))
        .select_related("organization", "asset", "source")
        .get(pk=component.device_id)
    )
    require(administrator(actor, org) and current(device))
    component = AgentComponent.objects.select_for_update(of=("self",)).get(pk=component.pk)
    InventorySource.objects.select_for_update(of=("self",)).get(pk=device.source_id)
    device.asset.refresh_from_db()
    require(current(device))
    if device.stale or component.stale or component.missing_since:
        raise ValidationError("A fresh, present observation is required")
    if component.installation_id:
        raise ValidationError("Already bound; detach explicitly before changing ownership")
    if create:
        family = "deb" if component.manager == "dpkg" else "rpm"
        identifier = f"pkg:{family}/{quote(device.os.get('id', 'linux'), safe='')}/{quote(component.name, safe='')}?arch={quote(component.architecture, safe='')}"
        if len(identifier) > 255:
            raise ValidationError("Package identifier exceeds the supported length")
        product, _ = Product.objects.get_or_create(
            organization=org, name=component.name, identifier=identifier
        )
        installation = Installation.objects.create(asset=device.asset, product=product, version="")
    else:
        installation = (
            Installation.objects.select_for_update(of=("self",))
            .select_related("product")
            .get(pk=installation_id, asset=device.asset, product__organization=org)
        )
        if AgentComponent.objects.filter(installation=installation).exists():
            raise ValidationError("Another publisher already owns this version field")
        if CSVAssetBinding.objects.filter(asset=device.asset).exists():
            raise ValidationError("Reconcile CSV ownership before binding existing software")
    old = installation.version
    component.installation = installation
    component.save(update_fields=["installation"])
    component.device = device
    _project(component, installation)
    audit(
        actor,
        org,
        "agent.software_bound",
        component.pk,
        installation=installation.pk,
        previous_version=old,
        version=component.version,
    )
    return installation


@transaction.atomic
def revoke(actor, org, device_id):
    device = AgentDevice.objects.select_for_update(of=("self",)).get(pk=device_id, organization=org)
    require(administrator(actor, org))
    device.enabled = False
    device.revoked_at = timezone.now()
    device.save(update_fields=["enabled", "revoked_at"])
    AgentReport.objects.filter(device=device, status="pending").update(
        status="rejected", error="Device revoked", processed_at=timezone.now()
    )
    audit(actor, org, "agent.revoked", device.pk)


@transaction.atomic
def detach(actor, org, component_id):
    component = AgentComponent.objects.select_related("device").get(pk=component_id, device__organization=org)
    AgentDevice.objects.select_for_update(of=("self",)).get(pk=component.device_id)
    require(administrator(actor, org))
    component = AgentComponent.objects.select_for_update(of=("self",)).get(pk=component.pk)
    previous = component.installation_id
    component.installation = None
    component.save(update_fields=["installation"])
    audit(actor, org, "agent.software_detached", component.pk, installation=previous)


@transaction.atomic
def cancel_enrollment(actor, org, grant_id):
    grant = AgentEnrollment.objects.select_for_update(of=("self",)).get(pk=grant_id, organization=org)
    require(administrator(actor, org))
    grant.expires_at = timezone.now()
    grant.save(update_fields=["expires_at"])
    if grant.used_at:
        revoke(actor, org, grant.device_id)
    audit(actor, org, "agent.enrollment_cancelled", grant.pk)
