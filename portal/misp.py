"""Restricted local MISP cache. Complete read snapshots, fail-closed access, no upstream writes."""

import hashlib
import json
import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .access import audit, is_analyst, require, ANALYST_GROUP
from .connectors.http import ConnectorError
from .connectors.misp import snapshot
from .models import MISPEvent, MISPInstance, Membership


def digest(event):
    return hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def owner_eligible(source):
    if not source.owner_id or not source.owner.is_active:
        return False
    if source.organization_id:
        if source.credential_kind != "encrypted" or not source.credential_ciphertext or not source.server_id:
            return False
        return Membership.objects.filter(
            user_id=source.owner_id, organization_id=source.organization_id
        ).exists()
    return source.owner.is_superuser or is_analyst(source.owner)


def endpoint_eligible(source):
    return not source.server_id or (
        source.server.enabled
        and source.server.base_url.rstrip("/") == source.base_url.rstrip("/")
        and source.server.allow_private == source.allow_private
    )


def ready(source):
    return bool(
        source.enabled
        and source.owner_id
        and source.misp_user_id
        and owner_eligible(source)
        and endpoint_eligible(source)
        and source.last_success
        and not source.error
        and not source.syncing_until
        and source.last_success >= timezone.now() - timedelta(minutes=source.max_age_minutes)
    )


def visible_events(actor):
    qs = MISPEvent.objects.filter(
        available=True, source__enabled=True, source__error="", source__syncing_until__isnull=True
    )
    if not actor.is_authenticated or not actor.is_active:
        return qs.none()
    # Apply each operator source's own freshness bound before listing event rows.
    sources = [
        s.pk
        for s in MISPInstance.objects.filter(enabled=True, owner=actor).select_related(
            "owner", "organization", "server"
        )
        if ready(s)
    ]
    qs = qs.filter(source_id__in=sources)
    context = Q(source__organization__membership__user=actor) | (
        Q(source__organization__isnull=True)
        & (Q(source__owner__is_superuser=True) | Q(source__owner__groups__name=ANALYST_GROUP))
    )
    qs = qs.filter(context, source__owner=actor, source__owner__is_active=True).filter(
        Q(source__server__isnull=True) | Q(source__server__enabled=True)
    )
    return qs.select_related("source").defer("payload").distinct()


def sync_source(pk, *, due=False):
    """Short lease transactions surround network I/O; readers fail closed during reconciliation."""
    now = timezone.now()
    generation = uuid.uuid4()
    with transaction.atomic():
        source = MISPInstance.objects.select_for_update().get(pk=pk)
        if not source.enabled:
            if due:
                return None
            raise ConnectorError("MISP source is disabled")
        if source.syncing_until and source.syncing_until > now:
            return None
        if (
            due
            and not source.syncing_until
            and source.last_attempt
            and source.last_attempt
            > now
            - timedelta(minutes=min(source.refresh_minutes, 5) if source.error else source.refresh_minutes)
        ):
            return None
        source.generation, source.syncing_until, source.last_attempt = (
            generation,
            now + timedelta(minutes=2),
            now,
        )
        source.save(update_fields=["generation", "syncing_until", "last_attempt"])
    try:
        rows = snapshot(source)
        with transaction.atomic():
            current = MISPInstance.objects.select_for_update().get(pk=pk)
            if (
                not current.syncing_until
                or current.syncing_until < timezone.now()
                or current.generation != generation
                or not current.enabled
                or current.base_url != source.base_url
                or current.token_env_var != source.token_env_var
                or current.owner_id != source.owner_id
                or current.misp_user_id != source.misp_user_id
                or current.organization_id != source.organization_id
                or current.server_id != source.server_id
                or current.credential_kind != source.credential_kind
                or current.credential_ciphertext != source.credential_ciphertext
            ):
                raise ConnectorError("MISP source changed during refresh; snapshot refused")
            current.full_clean()
            seen = []
            for payload in rows:
                key, timestamp, remote_id = payload["uuid"], int(payload["timestamp"]), int(payload["id"])
                event = MISPEvent.objects.select_for_update().filter(source=current, event_uuid=key).first()
                content_digest = digest(payload)
                if event:
                    if event.remote_id != remote_id or timestamp < event.timestamp:
                        raise ConnectorError("MISP event identity/timestamp regressed; snapshot refused")
                    if event.digest != content_digest or not event.available:
                        event.review_digest = (
                            ""  # Policy/content changes and reappearance invalidate reader attestations.
                        )
                    event.payload, event.digest, event.info = payload, content_digest, payload["info"]
                    event.timestamp, event.cached_at, event.available = timestamp, now, True
                    event.save()
                else:
                    event = MISPEvent.objects.create(
                        source=current,
                        event_uuid=key,
                        remote_id=remote_id,
                        timestamp=timestamp,
                        info=payload["info"],
                        payload=payload,
                        digest=content_digest,
                        cached_at=now,
                    )
                seen.append(event.pk)
            current.events.exclude(pk__in=seen).update(available=False, review_digest="")
            current.last_success, current.error, current.syncing_until = now, "", None
            current.save(update_fields=["last_success", "error", "syncing_until"])
            audit(None, None, "misp.cache_refreshed", current.pk, events=len(rows))
        return len(rows)
    except (ConnectorError, ValidationError):
        # Retain the previous complete cache but hide it after every uncertain/auth/partial failure.
        MISPInstance.objects.filter(pk=pk, generation=generation).update(
            error="MISP refresh failed; previous cache retained but unavailable for research",
            syncing_until=None,
        )
        raise ConnectorError("MISP refresh failed; cached data retained and access suspended") from None


def grant_readers(actor, event_id, readers, note, *, expected_digest):
    # Old callers must fail closed; no Bearings grant substitutes for personal upstream authorization.
    require(False)


def research(actor, event):
    """Transient exact infrastructure leads; no persisted finding or participant redistribution."""
    import ipaddress
    from .access import organizations_for
    from .models import InfrastructureClaim
    from .scope import matches, normalize

    require(visible_events(actor).filter(pk=event.pk, digest=event.digest).exists())
    payload = event.payload
    attributes = list(payload.get("Attribute", []))
    for obj in payload.get("Object", [])[:100]:
        if isinstance(obj, dict) and isinstance(obj.get("Attribute"), list):
            attributes.extend(obj["Attribute"][:100])
    indicators = []
    for item in attributes[:100]:
        if not isinstance(item, dict) or item.get("deleted") not in (None, False, 0, "0"):
            continue
        kind, value = item.get("type"), item.get("value")
        if not isinstance(value, str) or len(value) > 500:
            continue
        parts = [(kind, value)]
        if kind == "domain|ip" and value.count("|") == 1:
            domain, ip = value.split("|")
            parts = [("domain", domain), ("ip-dst", ip)]
        for kind, value in parts:
            try:
                if kind in {"domain", "hostname"}:
                    indicators.append(("domain", normalize("domain", value)))
                elif kind in {"ip-src", "ip-dst"}:
                    address = ipaddress.ip_address(value)
                    if address.is_global:
                        indicators.append(("ip", str(address)))
            except (ValidationError, ValueError):
                continue
    now = timezone.now()
    company_scope = organizations_for(actor)
    if event.source.organization_id:
        company_scope = company_scope.filter(pk=event.source.organization_id)
    claims = list(
        InfrastructureClaim.objects.filter(
            organization__in=company_scope,
            status="verified",
            valid_from__lte=now,
        )
        .select_related("organization")
        .order_by("pk")[:2001]
    )
    results, seen = [], set()
    for kind, indicator in dict.fromkeys(indicators):
        for claim in claims[:2000]:
            if (kind == "domain") != (claim.kind == "domain"):
                continue
            if matches(claim, indicator, now) and (claim.organization_id, indicator) not in seen:
                results.append(
                    {
                        "organization": claim.organization,
                        "indicator": indicator,
                        "claim": claim,
                        "reason": "Current verified infrastructure assignment",
                    }
                )
                seen.add((claim.organization_id, indicator))
                if len(results) >= 100:
                    return results, True
    return results, len(claims) > 2000 or len(attributes) > 100 or len(payload.get("Object", [])) > 100
