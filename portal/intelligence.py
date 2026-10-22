"""Versioned public catalog evidence and explicitly justified organization-local links."""

import hashlib
import json
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .access import audit, can_edit, can_operator_review, require, visible_findings
from .connectors.http import ConnectorError
from .connectors.mosp import risk_bundle, risk_catalog
from .models import (
    Finding,
    MOSPRisk,
    MOSPRiskRevision,
    MOSPSource,
    Organization,
    RiskLink,
    SourceRecord,
    SourceRecordRevision,
)

CATALOG_ERROR = "MOSP catalog refresh failed; last-known objects retained. Check endpoint, publisher, schema, pagination and CC0 licensing."


def digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def default_catalog():
    source, _ = MOSPSource.objects.get_or_create(
        name="MONARC public catalog",
        defaults={"base_url": settings.MOSP_URL, "publisher": settings.MOSP_PUBLISHER},
    )
    return source


def snapshot_evidence(record):
    revision, _ = SourceRecordRevision.objects.get_or_create(
        record=record, content_hash=digest(record.payload), defaults={"payload": record.payload}
    )
    return revision


def upsert_risk(source, payload):
    risk, _ = MOSPRisk.objects.update_or_create(
        source=source,
        uuid=payload["uuid"],
        defaults={
            "external_id": payload["id"],
            "description": payload["description"],
            "payload": payload,
            "content_hash": digest(payload),
            "last_seen": timezone.now(),
            "missing_since": None,
        },
    )
    return risk


def sync_catalog(source_id, *, due=False):
    failed = False
    with transaction.atomic():
        source = MOSPSource.objects.select_for_update().get(pk=source_id)
        now = timezone.now()
        if due and (
            not source.enabled
            or (source.last_attempt and now - source.last_attempt < timedelta(minutes=source.refresh_minutes))
        ):
            return None
        try:
            with transaction.atomic():
                rows = risk_catalog(source)
                seen = [upsert_risk(source, row).pk for row in rows]
                source.risks.exclude(pk__in=seen).filter(missing_since__isnull=True).update(missing_since=now)
        except ConnectorError:
            source.error = CATALOG_ERROR
            failed = True
        else:
            source.last_success, source.error = timezone.now(), ""
        source.last_attempt = now
        source.save(update_fields=["last_attempt", "last_success", "error"])
        audit(None, None, "mosp.sync_failed" if failed else "mosp.synced", source.pk)
    if failed:
        raise ConnectorError(CATALOG_ERROR)
    return len(rows)


def resolve_risk(source_id, risk_uuid):
    with transaction.atomic():
        source = MOSPSource.objects.select_for_update().get(pk=source_id)
        # No asset names, CVEs, justifications or organization data are sent to MOSP.
        bundle = risk_bundle(source, risk_uuid)
        risk = upsert_risk(source, bundle["risk"])
        revision, _ = MOSPRiskRevision.objects.get_or_create(
            risk=risk,
            content_hash=digest(bundle),
            defaults={"risk_hash": digest(bundle["risk"]), "payload": bundle},
        )
        risk.current_revision = revision
        risk.save(update_fields=["current_revision"])
        return revision


def authorize_link(user, finding):
    org = Organization.objects.get(pk=finding.organization_id)
    require(can_edit(user, org) or can_operator_review(user, org))
    require(visible_findings(user, org).filter(pk=finding.pk).exists())
    finding.full_clean()
    return org


def link_risk(user, finding, source_id, risk_uuid, reason, *, expected_revision=None):
    require(bool(reason.strip()) and len(reason) <= 4000)
    authorize_link(user, finding)
    revision = resolve_risk(source_id, risk_uuid)
    if expected_revision is not None and revision.pk != expected_revision:
        raise ValidationError("The catalog scenario changed. Review the updated preview before confirming.")
    with transaction.atomic():
        finding = Finding.objects.select_for_update().get(pk=finding.pk)
        org = authorize_link(user, finding)
        record = SourceRecord.objects.select_for_update().get(pk=finding.record_id)
        evidence = snapshot_evidence(record)
        link, created = RiskLink.objects.get_or_create(
            finding=finding,
            evidence_revision=evidence,
            risk_revision=revision,
            withdrawn_at=None,
            defaults={"reason": reason.strip(), "created_by": user},
        )
        link.full_clean()
        audit(user, org, "risk.linked", link.pk, created=created, rule="analyst-catalog-reference/v1")
        return link


@transaction.atomic
def withdraw_link(user, pk, reason):
    require(bool(reason.strip()) and len(reason) <= 4000)
    link = RiskLink.objects.select_for_update().select_related("finding").get(pk=pk)
    org = authorize_link(user, link.finding)
    if not link.withdrawn_at:
        link.withdrawn_at, link.withdrawal_reason = timezone.now(), reason.strip()
        link.save(update_fields=["withdrawn_at", "withdrawal_reason"])
        audit(user, org, "risk.withdrawn", link.pk, reason=link.withdrawal_reason)
    return link


def link_state(link):
    risk = link.risk_revision.risk
    return {
        "evidence_changed": digest(link.finding.record.payload) != link.evidence_revision.content_hash,
        "catalog_changed": risk.content_hash != link.risk_revision.risk_hash
        or risk.current_revision_id != link.risk_revision_id,
        "catalog_missing": risk.missing_since is not None,
        "source_disabled": not risk.source.enabled,
    }


def visible_links(user, org):
    # Derive every raw/derived relation through the same evidence visibility policy.
    return RiskLink.objects.filter(finding__in=visible_findings(user, org)).select_related(
        "finding__record",
        "finding__installation__product",
        "finding__installation__asset__source__instance",
        "evidence_revision",
        "risk_revision__risk__source",
        "created_by",
    )
