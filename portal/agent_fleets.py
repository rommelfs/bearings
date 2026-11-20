"""Narrow rollout authorization: signed key possession, company scope, quota and current policy."""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .access import require, audit
from .agent_protocol import public_key, identifier
from .models import AgentFleet, AgentFleetRegistration, AgentEnrollment, InventorySource, Organization
from . import agents, agent_enrollment_codes


def fingerprint(source):
    data = {
        "source": str(source.pk),
        "organization": source.organization_id,
        "mode": source.mode,
        "instance": str(source.instance_id),
        "tenant": source.tenant_id,
        "endpoint": source.instance.base_url if source.instance_id else "",
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def active(fleet):
    return (
        fleet.enabled
        and fleet.expires_at > timezone.now()
        and agents.administrator(fleet.created_by, fleet.organization)
        and fleet.source.organization_id == fleet.organization_id
        and (not fleet.source.instance_id or fleet.source.instance.enabled)
        and fleet.source_fingerprint == fingerprint(fleet.source)
    )


@transaction.atomic
def create(actor, org, name, new_asset_kind, max_devices=1000, hours=24):
    org = Organization.objects.select_for_update(no_key=True).get(pk=org.pk)
    require(agents.administrator(actor, org))
    if (
        not name.strip()
        or len(name) > 100
        or new_asset_kind not in {"vm", "server", "desktop", "laptop"}
        or not 1 <= max_devices <= 100000
        or not 1 <= hours <= 168
    ):
        raise ValidationError("Choose a name, supported host type, 1–100000 devices and 1–168 hours")
    agent_enrollment_codes.trusted_origin()
    source = InventorySource.objects.select_related("instance").get(organization=org)
    if source.instance_id and not source.instance.enabled:
        raise ValidationError("Inventory connection is disabled")
    secret = secrets.token_urlsafe(32)
    fleet = AgentFleet.objects.create(
        organization=org,
        source=source,
        created_by=actor,
        name=name.strip(),
        new_asset_kind=new_asset_kind,
        max_devices=max_devices,
        expires_at=timezone.now() + timedelta(hours=hours),
        token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        source_fingerprint=fingerprint(source),
    )
    audit(
        actor,
        org,
        "agent.fleet_created",
        fleet.pk,
        max_devices=max_devices,
        hours=hours,
        mode="observed-only",
    )
    return fleet, str(fleet.pk) + "." + secret


def grant_secret(fleet, grant, secret):
    return salted_hmac(
        "bearings.agent.fleet-grant/v1",
        f"{fleet.pk}:{fleet.organization_id}:{grant.pk}:{grant.public_key}",
        secret=secret,
        algorithm="sha256",
    ).hexdigest()


@transaction.atomic
def issue(fleet_id, secret, key, request_id):
    public_key(key)
    request_id = identifier(request_id)
    context = AgentFleet.objects.only("organization_id", "token_hash", "enabled").get(pk=fleet_id)
    if not context.enabled or not hmac.compare_digest(
        context.token_hash, hashlib.sha256(secret.encode()).hexdigest()
    ):
        raise ValueError("Rollout authorization unavailable")
    Organization.objects.select_for_update(no_key=True).get(pk=context.organization_id)
    fleet = (
        AgentFleet.objects.select_for_update(of=("self",))
        .select_related("organization", "source__instance", "created_by")
        .get(pk=fleet_id)
    )
    if not active(fleet) or not hmac.compare_digest(
        fleet.token_hash, hashlib.sha256(secret.encode()).hexdigest()
    ):
        raise ValueError("Rollout authorization unavailable")
    existing = AgentFleetRegistration.objects.select_related("enrollment").filter(public_key=key).first()
    if existing:
        if existing.fleet_id != fleet.pk or existing.request_id != request_id:
            raise ValueError("Device identity already reserved; inspect its pending registration")
        grant = existing.enrollment
        if grant.expires_at <= timezone.now():
            raise ValueError("Pending registration expired or cancelled; review before replacing")
        token = None
        for candidate in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]:
            derived = grant_secret(fleet, grant, candidate)
            if hmac.compare_digest(hashlib.sha256(derived.encode()).hexdigest(), grant.token_hash):
                token = str(grant.pk) + "." + derived
                break
        if token is None:
            raise ValueError("Pending registration secret unavailable")
    else:
        if (
            fleet.issued_devices >= fleet.max_devices
            or AgentEnrollment.objects.filter(public_key=key).exists()
        ):
            raise ValueError("Rollout limit or device identity conflict")
        grant, _ = agents.create_enrollment(
            fleet.created_by,
            fleet.organization,
            None,
            key,
            fleet.new_asset_kind,
            fleet=fleet,
            observed_only=True,
        )
        derived = grant_secret(fleet, grant, settings.SECRET_KEY)
        grant.token_hash = hashlib.sha256(derived.encode()).hexdigest()
        grant.expires_at = min(grant.expires_at, fleet.expires_at)
        grant.save(update_fields=["token_hash", "expires_at"])
        token = str(grant.pk) + "." + derived
        AgentFleetRegistration.objects.create(
            fleet=fleet, public_key=key, request_id=request_id, enrollment=grant
        )
        fleet.issued_devices += 1
        fleet.save(update_fields=["issued_devices"])
    payload = agent_enrollment_codes.payload(grant, token)
    payload.update(asset_id="", register_host=True)
    return payload


@transaction.atomic
def revoke(actor, org, pk):
    org = Organization.objects.select_for_update(no_key=True).get(pk=org.pk)
    require(agents.administrator(actor, org))
    fleet = AgentFleet.objects.select_for_update().get(pk=pk, organization=org)
    fleet.enabled = False
    fleet.save(update_fields=["enabled"])
    audit(actor, org, "agent.fleet_revoked", fleet.pk)
