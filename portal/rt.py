"""Reviewed, source-bound ticket creation. Uncertain POSTs are reconciled through reads."""

import json
import re
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from . import issues
from .access import audit, can_operator_review, require
from .asset_context import asset_context
from .connectors.http import ConnectorError
from .connectors.rt import api
from .models import AssetIssue, RTInstance, RTTicket
from .notifications import digest


def can_read(actor, issue, instance):
    if not actor.is_active or not issues.visible_issues(actor).filter(pk=issue.pk).exists():
        return False
    return (
        instance.organization_id == issue.organization_id
        if instance.organization_id
        else can_operator_review(actor, issue.organization) and issue.organization.operator_visibility
    )


def can_write(actor, issue, instance):
    return (
        can_read(actor, issue, instance)
        and issues.editable(actor, issue)
        and issue.active
        and issue.asset.lifecycle == "active"
        and instance.enabled
        and instance.private_queue_confirmed
        and (issue.finding.record.shareable if issue.finding_id else issue.shareable)
        and not issue.operator_only
    )


def load(pk):
    row = RTTicket.objects.select_related("instance", "creator").get(pk=pk)
    row.issue = AssetIssue.objects.select_related(
        "organization", "asset__source__instance", "installation__product", "finding__record"
    ).get(pk=row.issue_id)
    return row


def snapshot(issue, instance, reason):
    data = {
        "issue": issues.data_for(issue),
        "asset": {
            "name": issue.asset.name,
            "facts": asset_context(issue.asset),
            "criticality": issue.asset.criticality,
            "team": issue.asset.responsible_team,
            "missing_since": str(issue.asset.missing_since or ""),
            "lifecycle": issue.asset.lifecycle,
        },
        "organization": issue.organization.name,
        "queue": instance.queue_id,
        "custom_fields": instance.custom_fields,
        "reason": reason,
        "risks": list(
            issue.risk_scenarios.filter(withdrawn_at__isnull=True).values(
                "issue_revision_id", "risk_revision_id", "reason"
            )
        ),
    }
    if issue.finding_id:
        from .notifications import finding_snapshot

        data["vulnerability"] = finding_snapshot(issue.finding)
        data["risks"] = list(
            issue.finding.risk_links.filter(
                withdrawn_at__isnull=True, evidence_revision__record_id=issue.finding.record_id
            ).values("evidence_revision_id", "risk_revision_id", "reason")
        )
    return data


@transaction.atomic
def preview(actor, issue, instance, reason):
    issue = issues.visible_issues(actor).select_for_update(of=("self",)).get(pk=issue.pk)
    instance = RTInstance.objects.get(pk=instance.pk)
    require(can_write(actor, issue, instance))
    require(bool(reason.strip()) and len(reason) <= 3000)
    instance.full_clean()
    row, created = RTTicket.objects.get_or_create(
        issue=issue,
        instance=instance,
        defaults={
            "creator": actor,
            "snapshot": {},
            "fingerprint": "",
            "subject": "",
            "content": "",
            "reason": reason.strip(),
        },
    )
    row = RTTicket.objects.select_for_update().get(pk=row.pk)
    if not created and row.state not in {"draft", "blocked"} or row.attempted_at:
        return row
    data = snapshot(issue, instance, reason.strip())
    label = re.sub(r"[^A-Za-z0-9 ._-]", "-", issue.asset.name)[:65]
    row.subject = f"Bearings {issue.kind}: {label} [{row.pk}]"
    row.content = (
        "Bearings asset issue. Source CVSS, organizational priority and possible consequences are distinct.\n"
        "Ticket workflow completion does not establish remediation.\n\n"
        + json.dumps(data, indent=2, ensure_ascii=False)
    )
    row.snapshot, row.fingerprint, row.creator, row.reason, row.state, row.error = (
        data,
        digest(data),
        actor,
        reason.strip(),
        "draft",
        "",
    )
    row.save()
    audit(actor, issue.organization, "rt.preview", row.pk, instance=str(instance.pk))
    return row


def require_current(row):
    require(can_write(row.creator, row.issue, row.instance))
    if digest(snapshot(row.issue, row.instance, row.reason)) != row.fingerprint:
        raise ValidationError("Issue, inventory, evidence or destination changed; review before export")


@transaction.atomic
def approve(actor, pk):
    RTTicket.objects.select_for_update().get(pk=pk)
    row = load(pk)
    require(row.creator_id == actor.pk)
    require_current(row)
    if row.state != "draft":
        raise ValidationError("Ticket preview was already approved or attempted")
    row.state, row.approved_at = "queued", timezone.now()
    row.save(update_fields=["state", "approved_at"])
    audit(actor, row.issue.organization, "rt.approved", pk)


def positive_id(value):
    if type(value) not in {str, int} or not re.fullmatch(r"[1-9][0-9]{0,9}", str(value)):
        raise ConnectorError("Invalid RT identity")
    return int(value)


def verified_remote(row):
    data = api(row.instance, "GET", f"ticket/{positive_id(row.remote_id)}", params={"fields[Owner]": "Name"})
    if (
        not isinstance(data, dict)
        or positive_id(data.get("id")) != row.remote_id
        or data.get("Subject") != row.subject
        or not isinstance(data.get("Queue"), dict)
        or positive_id(data["Queue"].get("id")) != row.instance.queue_id
        or (data.get("EffectiveId") is not None and positive_id(data["EffectiveId"]) != row.remote_id)
    ):
        raise ConnectorError("RT ticket identity, queue, subject or merge state changed")
    return data


@transaction.atomic
def claim(pk):
    RTTicket.objects.select_for_update().get(pk=pk)
    row = load(pk)
    if row.state != "queued":
        return False
    try:
        require_current(row)
    except (PermissionDenied, ValidationError):
        row.state, row.error = (
            "blocked",
            "Current access, evidence, inventory or destination prevents export.",
        )
        row.save(update_fields=["state", "error"])
        return False
    row.state, row.attempted_at, row.last_attempt = "creating", timezone.now(), timezone.now()
    row.save(update_fields=["state", "attempted_at", "last_attempt"])
    audit(row.creator, row.issue.organization, "rt.write_claimed", pk)
    return True


def process(pk):
    if not claim(pk):
        return
    row = load(pk)
    try:
        require_current(row)
        payload = {
            "Queue": row.instance.queue_id,
            "Subject": row.subject,
            "Content": row.content,
            "ContentType": "text/plain",
        }
        if row.instance.custom_fields:
            payload["CustomFields"] = row.instance.custom_fields
        if row.issue.action_due:
            payload["Due"] = row.issue.action_due.isoformat() + " 17:00:00 UTC"
        response = api(row.instance, "POST", "ticket", payload=payload)
        if not isinstance(response, dict) or response.get("type") != "ticket":
            raise ConnectorError("Invalid RT creation acknowledgment")
        row.remote_id = positive_id(response.get("id"))
        with transaction.atomic():
            row.save(update_fields=["remote_id"])
        verified_remote(row)
        row.state, row.error, row.last_success = "linked", "", timezone.now()
    except (ConnectorError, PermissionDenied, ValidationError, IntegrityError):
        row.state, row.error = (
            "uncertain",
            "Ticket creation outcome is uncertain; reconcile through reads. POST will not be retried.",
        )
    row.save(update_fields=["state", "error", "last_success"])
    audit(row.creator, row.issue.organization, "rt.write_result", pk, state=row.state)
    if row.state == "linked":
        refresh(pk)


def refresh(pk, actor=None):
    row = load(pk)
    actor = actor or row.creator
    require(can_read(actor, row.issue, row.instance) and row.instance.enabled)
    RTTicket.objects.filter(pk=pk).update(last_attempt=timezone.now())
    try:
        data = verified_remote(row)
        if not isinstance(data.get("Status"), str):
            raise ConnectorError("Invalid RT status")
        owner = data.get("Owner")
        owner_name = (
            str(owner.get("Name") or owner.get("id") or "Unassigned")[:180]
            if isinstance(owner, dict)
            else "Unassigned"
        )
        summary = {"status": data["Status"][:80], "owner": owner_name, "due": str(data.get("Due") or "")[:80]}
        current = load(pk)
        require(can_read(actor, current.issue, current.instance) and current.instance.enabled)
        RTTicket.objects.filter(pk=pk).update(summary=summary, last_success=timezone.now(), error="")
        audit(actor, row.issue.organization, "rt.refreshed", pk)
    except ConnectorError:
        RTTicket.objects.filter(pk=pk).update(
            error="RT read/identity verification failed; last-known status retained."
        )
        raise


def reconcile(pk, actor=None):
    row = load(pk)
    actor = actor or row.creator
    require(can_read(actor, row.issue, row.instance) and row.instance.enabled)
    if not row.attempted_at:
        raise ValidationError("There is no attempted ticket creation to reconcile")
    if (
        row.state == "creating"
        and row.last_attempt
        and row.last_attempt > timezone.now() - timedelta(minutes=2)
    ):
        raise ValidationError("Ticket creation may still be in flight; wait before reconciliation")
    if not row.remote_id:
        # Subject contains generated safe ASCII and UUID; caller text cannot supply RTQL operators.
        response = api(
            row.instance,
            "GET",
            "tickets",
            params={
                "query": f"Queue = {row.instance.queue_id} AND Subject = '{row.subject}'",
                "per_page": 100,
                "page": 1,
            },
        )
        items = response.get("items") if isinstance(response, dict) else None
        if (
            not isinstance(items, list)
            or len(items) != 1
            or response.get("next_page")
            or response.get("total") not in (None, 1)
        ):
            raise ConnectorError(
                "No unique complete matching RT ticket result; operator investigation required, no POST retried"
            )
        if not isinstance(items[0], dict):
            raise ConnectorError("Invalid RT search response")
        row.remote_id = positive_id(items[0].get("id"))
    verified_remote(row)
    with transaction.atomic():
        current = RTTicket.objects.select_for_update().get(pk=pk)
        fresh = load(pk)
        require(can_read(actor, fresh.issue, fresh.instance) and fresh.instance.enabled)
        if current.state == "creating" and current.last_attempt > timezone.now() - timedelta(minutes=2):
            raise ValidationError("Ticket creation is still in flight")
        current.remote_id, current.state, current.error = row.remote_id, "linked", ""
        try:
            with transaction.atomic():
                current.save(update_fields=["remote_id", "state", "error"])
        except IntegrityError:
            raise ConnectorError(
                "RT ticket identity is already bound; investigate without retrying"
            ) from None
    audit(actor, row.issue.organization, "rt.reconciled", pk)
    refresh(pk, actor)
