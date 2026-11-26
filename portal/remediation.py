"""Scoped remediation plans. Customer delivery waits for a verified private FlowIntel case."""

import html
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from . import flowintel, notifications
from .access import audit, can_operator_review, organizations_for, require, visible_findings
from .models import (
    FlowIntelCase,
    FlowIntelInstance,
    FlowIntelTask,
    NotificationBatch,
    NotificationDelivery,
    NotificationDeliveryFinding,
    NotificationReceipt,
    RemediationReservation,
)
from .notifications import digest
from .presentation import ACTIVE_REVIEWS
from .review_queue import classified, current_version_exclusion
from .review_update_preview import FIX_FEED, FIX_PROOF, fix_targets
from .service_mail import mail_subject

CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,23}", flags=re.IGNORECASE | re.ASCII)
MAX_FINDINGS = 2000
MAX_TASKS = 150
MAX_CONTACTS = 25


def notification_access_blocker(actor, org):
    if not actor.is_active:
        return "Sign in with an active account to prepare notifications."
    if not org.operator_visibility:
        return "This organization has disabled CIRCL analyst visibility. A platform administrator can review that setting."
    if not can_operator_review(actor, org):
        return "A CIRCL analyst or platform administrator can prepare notifications for this organization."
    return ""


def available_to(actor, org):
    return not notification_access_blocker(actor, org)


def findings_for(actor, org):
    return visible_findings(actor, org).filter(
        installation__asset__organization=org,
        installation__asset__source__organization=org,
        installation__product__organization=org,
        record__organization=org,
        record__shareable=True,
    )


def require_access(actor, case):
    org = case.finding.organization
    require(available_to(actor, org) and organizations_for(actor).filter(pk=org.pk).exists())
    ids = case.snapshot["finding_ids"]
    require(findings_for(actor, org).filter(pk__in=ids).count() == len(ids))


def work(actor, org, *, asset=None, cve=None, ids=None):
    qs = (
        findings_for(actor, org)
        .filter(
            status__in=ACTIVE_REVIEWS,
            record__external_id__iregex=f"^{CVE.pattern}$",
            installation__asset__lifecycle="active",
        )
        .exclude(analyst_applicability="not_affected")
        .order_by("pk")
    )
    if asset is not None:
        qs = qs.filter(installation__asset_id=asset)
    if cve is not None:
        qs = qs.filter(record__external_id__iexact=cve)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return (
        classified(qs)
        .exclude(current_version_exclusion())
        .select_related("installation__asset__responsible_contact", "installation__asset__source")
        .defer("record__payload")
    )


def contacts_for(org):
    return notifications.eligible_contacts(org).filter(function__in=["security", "technical", "dpo"])


def target_rows(findings):
    return {
        row["pk"]: fix_targets(row)
        for row in classified(findings)
        .filter(package_current=True, distro_match__queue_proof__verdict="affected")
        .values("pk", FIX_FEED, FIX_PROOF)
    }


def grouped_actions(findings, targets, mitigation, *, skip_reserved=False):
    entries = []
    applied_mitigation = False
    for finding in findings:
        installation = finding.installation
        asset = installation.asset
        cve = finding.record.external_id.upper()
        fixes = targets.get(finding.pk) or []
        detail = None
        if fixes and not asset.missing_since:
            kind, detail = "update", fixes
        elif mitigation and finding.pk == mitigation["finding"]:
            if (
                asset.missing_since
                or not (installation.version or installation.build)
                or (finding.analyst_applicability != "affected" and finding.pk not in targets)
            ):
                raise ValidationError(
                    "A mitigation requires a recorded version and current affected evidence."
                )
            kind, detail = "mitigate", mitigation
            applied_mitigation = True
        else:
            kind = "verify"
        key = digest(
            [
                str(asset.pk),
                installation.pk,
                cve,
                kind,
                installation.version,
                installation.edition,
                installation.build,
                detail if kind == "update" else None,
            ]
        )
        data = {
            "finding": finding.pk,
            "cve": cve,
            "record": finding.record_id,
            "revision": finding.record.ingested_at.isoformat(),
            "source": finding.record.source,
            "assessment": finding.analyst_applicability,
            "status": finding.status,
            "evaluation": finding.applicability,
            "installation": installation.pk,
            "software": installation.product.name,
            "version": installation.version,
            "edition": installation.edition,
            "build": installation.build,
            "detail": detail,
            "mitigation_evidence_hash": digest(finding.record.payload) if kind == "mitigate" else "",
            "key": key,
        }
        entries.append((asset, kind, data))
    if mitigation and not applied_mitigation:
        raise ValidationError("The selected review already has a vendor fix or is outside this selection.")

    existing = {}
    if skip_reserved:
        existing = dict(
            RemediationReservation.objects.filter(
                fingerprint__in={data["key"] for _, _, data in entries}
            ).values_list("fingerprint", "case_id")
        )
    groups = {}
    for asset, kind, item in entries:
        if item["key"] in existing:
            continue
        identity = (str(asset.pk), kind, item["installation"] if kind == "update" else None)
        if identity not in groups:
            groups[identity] = {
                "asset": str(asset.pk),
                "host": asset.name,
                "team": asset.responsible_team,
                "owner": asset.responsible_contact_id,
                "missing": bool(asset.missing_since),
                "kind": kind,
                "items": [],
            }
        groups[identity]["items"].append(item)
    return list(groups.values()), set(existing.values())


def action_title(group):
    if group["kind"] == "update":
        return "Update " + group["items"][0]["software"] + " on " + group["host"]
    if group["kind"] == "mitigate":
        return "Apply reviewed mitigation on " + group["host"]
    return "Verify exposure and find a remedy on " + group["host"]


def evidence_link(bearings_url, org, item):
    return (
        bearings_url
        + reverse("intelligence", args=[org.slug])
        + f"?finding={item['finding']}#finding-{item['finding']}"
    )


def action_text(group, bearings_url, org):
    lines = [action_title(group), "Responsible team: " + (group["team"] or "Assign a responsible team")]
    if group["kind"] == "update":
        lines.extend(
            [
                "Check the package candidate in the host's configured repositories. Install a candidate that meets every applicable vendor fix below, or record the repository or support blocker.",
                "After the change, report fresh inventory and verify the installed version against each vendor rule. Review restart requirements for the affected services.",
            ]
        )
    elif group["kind"] == "mitigate":
        mitigation = group["items"][0]["detail"]
        lines.extend(
            [
                "Mitigation: " + mitigation["action"],
                "Source reference: " + mitigation["source"],
                "Verify: " + mitigation["verification"],
            ]
        )
    else:
        lines.append(
            "Refresh inventory where needed, check the installed release/configuration against the referenced advisory, and record a vendor fix, a reviewed workaround, or why the host is unaffected."
        )
    seen = set()
    for item in group["items"]:
        text = (
            f"{item['cve']} · {item['software']} · installed {item['version'] or item['build'] or 'unknown'}"
        )
        if group["kind"] == "update":
            for fix in item["detail"]:
                channel = " · " + ", ".join(fix["channels"]) if fix["channels"] else ""
                text += f"\n  Vendor fixed version {fix['version']} ({fix['basis']}){channel}"
        if text not in seen:
            lines.append(text)
            seen.add(text)
        lines.append(evidence_link(bearings_url, org, item))
    return "\n".join(lines)


def verification_for(actor, case):
    org = case.finding.organization
    rows = classified(findings_for(actor, org).filter(pk__in=case.snapshot["finding_ids"])).values_list(
        "pk", "status", "analyst_applicability", "package_current", "distro_match__queue_proof__verdict"
    )
    states = {}
    for pk, status, assessment, current, verdict in rows:
        if current and verdict in {"fixed", "not_matched"}:
            label = "Vendor fix verified" if verdict == "fixed" else "Outside current vendor rule"
        elif status == "resolved":
            label = "Resolved in Bearings"
        elif assessment == "not_affected":
            label = "Assessed as unaffected"
        elif current and verdict == "affected":
            label = "Affected package version still present"
        else:
            label = "Verification pending"
        states[pk] = label
    return states


def instance_context(instance):
    return {
        "endpoint": instance.base_url,
        "bearings_url": instance.bearings_url,
        "service_org_id": instance.service_org_id,
        "credential_reference": instance.token_env_var,
        "allow_private": instance.allow_private,
    }


def plan_data(instance, groups, mitigation):
    return {
        **instance_context(instance),
        "groups": groups,
        "mitigation": mitigation,
        "finding_ids": sorted(item["finding"] for group in groups for item in group["items"]),
    }


def message_for(case, contact, groups):
    actions = [
        group
        for group in groups
        if group["kind"] != "verify" and (contact.function != "technical" or group["owner"] == contact.pk)
    ]
    if not actions:
        raise ValidationError("A selected recipient has no actionable items in their responsibility.")
    validate_email(contact.email)
    org = case.finding.organization
    subject = mail_subject(f"[Bearings] {len(actions)} remediation actions for {org.name}"[:250])
    text = "\n\n".join(action_text(group, case.instance.bearings_url, org) for group in actions)
    deadline = f"\nRequested by {case.deadline.isoformat()}." if case.deadline else ""
    body = (
        f"Hello {contact.name},\n\n{org.name} has {len(actions)} remediation actions.{deadline}"
        f"\nReference {case.pk}.\n\n{text}\n"
    )
    if len(body.encode("utf-8")) > 1_000_000:
        raise ValidationError("This message exceeds 1 MB. Choose a narrower scope.")
    snapshot = {
        "contact_id": contact.pk,
        "email": contact.email,
        "contact_policy": [
            contact.function,
            contact.role,
            contact.scope,
            contact.reachable_at.isoformat(),
            contact.reviewed_at.isoformat(),
            contact.next_review.isoformat(),
        ],
        "findings": [{"id": item["finding"]} for group in actions for item in group["items"]],
        "subject": subject,
        "body": body,
    }
    return snapshot, digest(snapshot), subject, body


def validate_contacts(org, ids):
    if len(ids) > MAX_CONTACTS:
        raise ValidationError(f"Choose at most {MAX_CONTACTS} verified contacts.")
    recipients = list(contacts_for(org).filter(pk__in=ids))
    if len(recipients) != len(ids):
        raise ValidationError("Recipient eligibility changed. Review the contact list again.")
    if len({contact.email.casefold() for contact in recipients}) != len(recipients):
        raise ValidationError("Choose one contact per email address.")
    if recipients and notifications.dpo_required(org) and not any(c.function == "dpo" for c in recipients):
        raise ValidationError("Company policy requires a currently eligible DPO among the recipients.")
    return recipients


def fenced(text):
    contents = html.escape(text, quote=False)
    fence = "`" * max(3, 1 + max((len(match) for match in re.findall(r"`+", contents)), default=0))
    return f"{fence}text\n{contents}\n{fence}"


def preview(actor, org, *, asset, cve, instance, deadline, contact_ids, mitigation):
    require(available_to(actor, org) and organizations_for(actor).filter(pk=org.pk).exists())
    require(bool(asset) != bool(cve))
    instance = FlowIntelInstance.objects.get(pk=instance.pk)
    instance.full_clean()
    if not instance.available or not instance.bearings_url:
        raise ValidationError("Choose an enabled FlowIntel destination with a configured Bearings URL.")
    if deadline and deadline < timezone.localdate():
        raise ValidationError("Choose a deadline today or later.")
    qs = work(actor, org, asset=asset, cve=cve)
    findings = list(qs[: MAX_FINDINGS + 1])
    if len(findings) > MAX_FINDINGS:
        raise ValidationError(f"More than {MAX_FINDINGS} active reviews. Start with a narrower scope.")
    groups, existing = grouped_actions(findings, target_rows(qs), mitigation, skip_reserved=True)
    if len(groups) > MAX_TASKS:
        raise ValidationError(f"More than {MAX_TASKS} tasks. Start with a narrower scope.")
    if not groups:
        return None, existing
    return create_draft(actor, org, instance, deadline, contact_ids, mitigation, groups), existing


@transaction.atomic
def create_draft(actor, org, instance, deadline, contact_ids, mitigation, groups):
    recipients = validate_contacts(org, contact_ids)
    transport, transport_hash = notifications.transport_configuration() if recipients else ("file", "")
    batch = NotificationBatch.objects.create(
        creator=actor,
        mode="circl",
        organization=org,
        filters={"remediation": True},
        transport=transport,
        transport_fingerprint=transport_hash,
        status="draft",
    )
    data = plan_data(instance, groups, mitigation)
    case = FlowIntelCase(
        creator=actor,
        instance=instance,
        finding=flowintel.finding_for(data["finding_ids"][0]),
        remediation_batch=batch,
        deadline=deadline,
        snapshot=data,
        fingerprint=digest(data),
        reason="Coordinate remediation, responsible contacts and fresh verification evidence.",
    )
    case.title = f"Bearings remediation [{case.pk}]"
    status_url = instance.bearings_url + reverse("flowintel-case", args=[org.slug, case.pk])
    case.description = (
        fenced(f"Remediation for {org.name}. Track delivery and review host evidence in Bearings.")
        + f"\n\n[Open Bearings remediation record]({status_url})"
    )
    case.save()
    for step, group in enumerate(groups, 1):
        FlowIntelTask.objects.create(
            case=case,
            step=step,
            title=f"{action_title(group)[:180]} [{case.pk}:{step}]",
            description=fenced(action_text(group, instance.bearings_url, org)),
        )
    for contact in recipients:
        snapshot, fingerprint, subject, body = message_for(case, contact, groups)
        delivery = NotificationDelivery.objects.create(
            batch=batch,
            organization=org,
            contact=contact,
            snapshot=snapshot,
            fingerprint=fingerprint,
            subject=subject,
            body=body,
        )
        NotificationDeliveryFinding.objects.bulk_create(
            NotificationDeliveryFinding(delivery=delivery, finding_id=item["id"])
            for item in snapshot["findings"]
        )
    audit(actor, org, "remediation.preview", case.pk, tasks=len(groups), recipients=len(recipients))
    return case


def require_current(case):
    require_access(case.creator, case)
    require(case.instance.available)
    org = case.finding.organization
    ids = case.snapshot["finding_ids"]
    qs = work(case.creator, org, ids=ids)
    findings = list(qs)
    if len(findings) != len(ids):
        raise ValidationError("A review is no longer eligible for this plan.")
    mitigation = case.snapshot["mitigation"]
    groups, _ = grouped_actions(findings, target_rows(qs), mitigation)
    if digest(plan_data(case.instance, groups, mitigation)) != case.fingerprint:
        raise ValidationError("Remediation evidence, owner or destination changed. Prepare a new preview.")
    batch = case.remediation_batch
    deliveries = list(batch.deliveries.all())
    if deliveries:
        notifications.require_transport(batch)
        recipients = {
            contact.pk: contact for contact in validate_contacts(org, [d.contact_id for d in deliveries])
        }
        for delivery in deliveries:
            snapshot, fingerprint, subject, body = message_for(case, recipients[delivery.contact_id], groups)
            if (snapshot, fingerprint, subject, body) != (
                delivery.snapshot,
                delivery.fingerprint,
                delivery.subject,
                delivery.body,
            ):
                raise ValidationError("The recipient or message changed. Prepare a new preview.")


def reserve(case):
    keys = sorted({item["key"] for group in case.snapshot["groups"] for item in group["items"]})
    try:
        with transaction.atomic():
            RemediationReservation.objects.bulk_create(
                RemediationReservation(case=case, fingerprint=key) for key in keys
            )
    except IntegrityError:
        raise ValidationError(
            "A matching action was already approved. Open the current plan from the selection page."
        ) from None


@transaction.atomic
def release_notifications(pk):
    case = FlowIntelCase.objects.select_for_update().select_related("creator", "instance").get(pk=pk)
    if case.state != "linked" or not case.last_success or not case.remote_uuid:
        return
    case.finding = flowintel.finding_for(case.finding_id)
    batch = case.remediation_batch
    if batch.status not in {"draft", "approved"}:
        return
    waiting = batch.deliveries.filter(status__in=["draft", "flowintel_wait"])
    if batch.status == "approved" and not waiting.exists():
        return
    try:
        require_current(case)
    except (PermissionDenied, ValidationError):
        batch.status = "blocked"
        batch.save(update_fields=["status"])
        audit(case.creator, case.finding.organization, "remediation.notification_blocked", case.pk)
        return
    if (
        case.summary.get("completed")
        or not case.tasks.exists()
        or case.tasks.filter(remote_id__isnull=True).exists()
    ):
        return
    for delivery in waiting:
        if delivery.status == "flowintel_wait":
            delivery.status = "queued"
            delivery.save(update_fields=["status"])
            continue
        try:
            with transaction.atomic():
                NotificationReceipt.objects.create(fingerprint=delivery.fingerprint, delivery=delivery)
            delivery.status = "queued"
        except IntegrityError:
            delivery.status = "duplicate"
        delivery.save(update_fields=["status"])
    batch.status, batch.approved_at = "approved", timezone.now()
    batch.save(update_fields=["status", "approved_at"])
    audit(case.creator, case.finding.organization, "remediation.notification_released", case.pk)


def require_delivery(delivery):
    case = flowintel.load(delivery.batch.remediation_case.pk)
    if case.state != "linked" or not case.last_success or not case.remote_uuid:
        raise ValidationError("The FlowIntel case and tasks must be verified before delivery.")
    require_current(case)
    remote = flowintel.remote_case(case)
    tasks = {row["id"]: row.get("title") for row in flowintel.remote_tasks(case)}
    expected = list(case.tasks.values_list("remote_id", "title"))
    if remote["completed"] or not expected or any(tasks.get(pk) != title for pk, title in expected):
        raise ValidationError("The FlowIntel case is closed or its tasks changed.")
    require_current(flowintel.load(case.pk))
