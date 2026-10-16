import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from .access import audit, can_edit, require
from .connectors.http import ConnectorError
from .connectors.netbox import query_objects, write_asset
from .connectors.vulnerability_lookup import lookup
from .models import ContactToken, Finding, FindingHistory, InventorySource, InventoryWrite, SourceRecord


@transaction.atomic
def submit_asset(user, org, form):
    source = org.inventory_source
    require(can_edit(user, org) and source.can_write)
    asset = form.save(commit=False)
    asset.organization, asset.source = org, source
    asset.full_clean()
    asset.save()
    InventoryWrite.objects.create(asset=asset)
    audit(user, org, "inventory.submitted", asset.pk)
    return asset


def process_write(pk, force=False):
    # Row lock serializes workers in PostgreSQL. SQLite is single-worker development only.
    with transaction.atomic():
        source_id = InventoryWrite.objects.values_list("asset__source_id", flat=True).get(pk=pk)
        # Importers take the same source lock before touching assets/jobs.
        source = InventorySource.objects.select_for_update().get(pk=source_id)
        job = InventoryWrite.objects.select_for_update().select_related("asset__source").get(pk=pk)
        if job.completed_at or (not force and job.next_attempt > timezone.now()):
            return
        asset, now = job.asset, timezone.now()
        source.last_attempt = now
        job.attempts += 1
        try:
            object_type, external_id = write_asset(asset)
        except (ConnectorError, ValueError):
            # No upstream bodies, credentials, URLs or untrusted exception messages in logs/state.
            error = "Inventory write unconfirmed. Check operator connector configuration; retry/reconcile required."
            asset.state = "failed"
            job.error = source.error = error
            job.next_attempt = now + timedelta(seconds=min(3600, 30 * 2 ** min(job.attempts, 7)))
        else:
            asset.object_type, asset.external_id, asset.state = object_type, external_id, "synced"
            job.completed_at, job.error = now, ""
            source.last_success, source.error = now, ""
        asset.save()
        if asset.state == "synced" and source.asset_set.filter(state="failed").exists():
            source.error = "Some inventory writes remain failed; inspect assets."
        job.save()
        source.save()
        audit(None, asset.organization, "inventory.write", asset.pk, state=asset.state, attempt=job.attempts)


def query_inventory(source, object_types):
    """Scoped read health only: no partial response changes the inventory projection."""
    source.last_read_attempt = timezone.now()
    source.save(update_fields=["last_read_attempt"])
    try:
        result = {kind: query_objects(source, kind) for kind in object_types}
    except ConnectorError as exc:
        source.read_error = str(exc)[:200]
        source.save(update_fields=["read_error"])
        audit(None, source.organization, "inventory.query_failed", source.pk, object_types=object_types)
        raise
    source.last_read_success, source.read_error = timezone.now(), ""
    source.save(update_fields=["last_read_success", "read_error"])
    audit(
        None,
        source.organization,
        "inventory.queried",
        source.pk,
        object_types=object_types,
        counts={kind: len(rows) for kind, rows in result.items()},
    )
    return result


@transaction.atomic
def review_contact(user, contact):
    now = timezone.now()
    contact.reviewed_at, contact.reviewed_by = now, user
    contact.next_review = now.date() + timedelta(days=settings.CONTACT_REVIEW_DAYS)
    contact.save(update_fields=["reviewed_at", "reviewed_by", "next_review"])
    audit(user, contact.organization, "contact.role_reviewed", contact.pk)


def issue_contact_token(user, contact):
    raw = secrets.token_urlsafe(32)
    with transaction.atomic():
        ContactToken.objects.filter(contact=contact, used_at__isnull=True).update(used_at=timezone.now())
        ContactToken.objects.create(
            contact=contact,
            digest=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        # Local sink only; no production message delivery is configured.
        send_mail(
            "Bearings development: verify contact channel",
            f"LOCAL DEVELOPMENT ONLY. Open /contacts/verify/ and submit this one-use token: {raw}\n"
            "This verifies only email reachability, not authority, role review, or emergency availability.",
            settings.DEFAULT_FROM_EMAIL,
            [contact.email],
        )
        audit(user, contact.organization, "contact.verification_prepared", contact.pk)


@transaction.atomic
def redeem_contact_token(raw):
    if not raw or len(raw) > 128:
        return False
    token = (
        ContactToken.objects.select_for_update()
        .filter(digest=hashlib.sha256(raw.encode()).hexdigest())
        .first()
    )
    if not token or token.used_at or token.expires_at <= timezone.now():
        return False
    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])
    token.contact.reachable_at = token.used_at
    token.contact.invalid_delivery = False
    token.contact.save(update_fields=["reachable_at", "invalid_delivery"])
    audit(None, token.contact.organization, "contact.channel_verified", token.contact_id)
    return True


@transaction.atomic
def persist_lookup(user, installation, source, identifier, payload):
    org = installation.asset.organization
    record, _ = SourceRecord.objects.update_or_create(
        organization=org,
        source=source,
        external_id=identifier,
        defaults={"payload": payload, "ingested_at": timezone.now(), "shareable": True},
    )
    version = installation.version or "unknown"
    explanation = (
        f"A user selected {identifier} for review against {installation.product.name} (version {version}). "
        "The vulnerability record was retrieved, but product/version applicability has not been established. "
        "No exploitation or compromise is inferred. Criticality: "
        + installation.asset.criticality
        + ". Priority is analyst review because applicability is unknown."
    )
    finding, created = Finding.objects.get_or_create(
        installation=installation,
        record=record,
        rule="manual-cve-review/v1",
        defaults={"organization": org, "explanation": explanation},
    )
    if not created:
        finding.evaluated_at = timezone.now()
        finding.save(update_fields=["evaluated_at"])
    audit(user, org, "vulnerability.review_requested", finding.pk, created=created)
    return finding


def lookup_for_installation(user, installation, identifier):
    source, payload = lookup(identifier)
    return persist_lookup(user, installation, source, identifier.upper(), payload)


@transaction.atomic
def transition_finding(user, finding, status, reason, assessment=""):
    require(bool(reason.strip()))
    # Lock the row so concurrent analyst reviews preserve an accurate transition history.
    finding = Finding.objects.select_for_update().get(pk=finding.pk)
    require(status in {"under_review", "confirmed", "resolved", "false_positive", "accepted_risk"})
    require(assessment in {"", "unknown", "potential", "affected", "not_affected"})
    FindingHistory.objects.create(
        finding=finding,
        actor=user,
        previous_status=finding.status,
        status=status,
        reason=reason,
        previous_assessment=finding.analyst_applicability,
        assessment=assessment or finding.analyst_applicability,
    )
    if assessment:
        finding.analyst_applicability = assessment
    finding.status = status
    finding.save(update_fields=["status", "analyst_applicability"])
    audit(user, finding.organization, "finding.status_changed", finding.pk, status=status)
