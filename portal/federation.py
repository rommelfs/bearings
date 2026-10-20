"""Bounded, explicitly granted read-only company snapshots; never authoritative local inventory."""

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from .access import audit, can_review_contact, require
from .connectors.http import ConnectorError, approved_base, request_json
from .issues import issue_json, visible_issues
from .models import Asset, CompanyInstance, FederatedReport, FederationGrant
from .asset_context import asset_context

MAX_RECORDS = 500
MAX_BYTES = 1_500_000


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def grant_active(grant):
    return (
        grant.enabled
        and grant.expires_at > timezone.now()
        and grant.publisher.is_active
        and can_review_contact(grant.publisher, grant.organization)
    )


@transaction.atomic
def create_grant(actor, org, client_id, inventory=False, days=30):
    require(actor.is_active and can_review_contact(actor, org))
    if not 1 <= days <= 90:
        raise ValidationError("Grant validity must be between 1 and 90 days")
    secret = secrets.token_urlsafe(40)
    row = FederationGrant.objects.create(
        organization=org,
        publisher=actor,
        client_id=client_id,
        inventory=inventory,
        token_hash=digest(secret),
        expires_at=timezone.now() + timedelta(days=days),
    )
    audit(actor, org, "federation.granted", row.pk, inventory=inventory, client=str(client_id))
    return row, str(row.pk) + "." + secret


@require_GET
def export(request):
    # Production endpoints require TLS even when behind an operator-configured trusted proxy.
    if not request.is_secure():
        return JsonResponse({"error": "HTTPS required"}, status=403)
    try:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or len(header) > 300:
            raise ValueError
        identity, secret = header[7:].split(".", 1)
        client = uuid.UUID(request.headers.get("X-Bearings-Client", ""))
        grant = FederationGrant.objects.select_related("publisher", "organization").get(
            pk=uuid.UUID(identity)
        )
        if (
            not hmac.compare_digest(grant.token_hash, digest(secret))
            or client != grant.client_id
            or not grant_active(grant)
        ):
            raise ValueError
    except (ValueError, FederationGrant.DoesNotExist):
        return JsonResponse({"error": "Export grant unavailable"}, status=403)
    org = grant.organization
    qs = (
        visible_issues(grant.publisher)
        .filter(organization=org, operator_only=False)
        .filter(Q(finding__isnull=True, shareable=True) | Q(finding__record__shareable=True))
    )
    rows = list(qs.order_by("pk")[: MAX_RECORDS + 1])
    assets = (
        list(
            Asset.objects.filter(organization=org, source__organization=org).order_by("pk")[: MAX_RECORDS + 1]
        )
        if grant.inventory
        else []
    )
    if len(rows) > MAX_RECORDS or len(assets) > MAX_RECORDS:
        return JsonResponse({"error": "Snapshot limit exceeded; partitioned export required"}, status=413)
    issues = []
    for row in rows:
        item = issue_json(row)
        item.update(consequence=row.consequence, next_action=row.next_action, asset_name=row.asset.name)
        if row.finding_id:
            item["vulnerability"] = {
                "id": row.finding.record.external_id,
                "assessment": row.finding.analyst_applicability,
                "source": row.finding.record.source,
            }
        issues.append(item)
    inventory = [
        {
            "id": str(a.pk),
            "name": a.name,
            "kind": a.kind,
            "lifecycle": a.lifecycle,
            "location": asset_context(a),
        }
        for a in assets
    ]
    # Revalidate the grant after assembling the snapshot. No raw source bodies or contacts are exported.
    grant.refresh_from_db()
    if not grant_active(grant):
        return JsonResponse({"error": "Export grant unavailable"}, status=403)
    response = JsonResponse(
        {
            "schema": "bearings.federation/v1",
            "organization": str(grant.pk),
            "generated_at": timezone.now(),
            "complete": True,
            "resources": ["issues", "inventory"] if grant.inventory else ["issues"],
            "issues": issues,
            "inventory": inventory,
        }
    )
    if len(response.content) > MAX_BYTES:
        return JsonResponse({"error": "Snapshot byte limit exceeded"}, status=413)
    response["Cache-Control"] = "no-store"
    audit(grant.publisher, org, "federation.exported", grant.pk, issues=len(issues), assets=len(inventory))
    return response


def pull(pk):
    source = CompanyInstance.objects.get(pk=pk)
    started = timezone.now()
    CompanyInstance.objects.filter(pk=pk).update(last_attempt=started)
    try:
        source.full_clean()
        if not source.enabled:
            raise ConnectorError("Company source disabled")
        token = os.getenv(source.token_env_var, "").strip()
        if not token:
            raise ConnectorError("Company source credential unavailable")
        base = approved_base(source.base_url, source.allow_private)
        payload = request_json(
            "GET",
            base.rstrip("/") + "/api/v1/federation/export/",
            timeout=10,
            headers={"Authorization": "Bearer " + token, "X-Bearings-Client": str(source.client_id)},
        )
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != "bearings.federation/v1"
            or payload.get("complete") is not True
            or payload.get("organization") != str(source.remote_organization)
        ):
            raise ConnectorError("Invalid company snapshot identity/schema")
        when = parse_datetime(payload.get("generated_at", ""))
        if not when or timezone.is_naive(when) or abs((timezone.now() - when).total_seconds()) > 900:
            raise ConnectorError("Company snapshot timestamp is stale or invalid")
        resources = payload.get("resources")
        if resources not in (["issues"], ["issues", "inventory"]):
            raise ConnectorError("Invalid company resources")
        records = []
        for resource in ["issues", "inventory"]:
            items = payload.get(resource)
            if (
                not isinstance(items, list)
                or len(items) > MAX_RECORDS
                or (resource not in resources and items)
            ):
                raise ConnectorError("Invalid or oversized company snapshot")
            seen = set()
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise ConnectorError("Invalid company record")
                identity = uuid.UUID(item["id"])
                if identity in seen:
                    raise ConnectorError("Duplicate company record")
                seen.add(identity)
                encoded = json.dumps(item, sort_keys=True, separators=(",", ":"))
                if len(encoded.encode()) > 100_000:
                    raise ConnectorError("Company record exceeds limit")
                records.append((resource, identity, item, digest(encoded)))
        with transaction.atomic():
            locked = CompanyInstance.objects.select_for_update().get(pk=pk)
            if (
                locked.last_attempt != started
                or not locked.enabled
                or any(
                    getattr(locked, f) != getattr(source, f)
                    for f in [
                        "base_url",
                        "token_env_var",
                        "organization_id",
                        "remote_organization",
                        "client_id",
                    ]
                )
            ):
                raise ConnectorError("Company configuration changed during read")
            now = timezone.now()
            for resource, identity, item, sha in records:
                FederatedReport.objects.update_or_create(
                    source=locked,
                    resource=resource,
                    remote_id=identity,
                    defaults={"payload": item, "digest": sha, "seen_at": now, "missing_since": None},
                )
            # Absence or withdrawn resource access retains history with an explicit missing marker.
            locked.reports.exclude(seen_at=now).filter(missing_since__isnull=True).update(missing_since=now)
            locked.last_success, locked.error = now, ""
            locked.save(update_fields=["last_success", "error"])
        return len(records)
    except (ConnectorError, ValidationError, ValueError, TypeError, KeyError):
        CompanyInstance.objects.filter(pk=pk).update(
            error="Company snapshot unavailable or invalid. Last-known reports retained; no authoritative inventory changed."
        )
        raise ConnectorError("Company snapshot failed; last-known reports retained") from None
