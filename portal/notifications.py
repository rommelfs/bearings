"""Consent-aware, organization-scoped notification previews and local file outbox."""

import hashlib
import json
import os
import re
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.mail.backends.filebased import EmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Value, When
from django.template import Context, Engine
from django.urls import reverse
from django.utils import timezone
from .access import (
    audit,
    can_edit,
    can_operator_review,
    is_analyst,
    organizations_for,
    require,
    visible_findings_for,
)
from .asset_context import asset_context
from .models import AssetIssue, Contact, NotificationBatch, NotificationDelivery, NotificationReceipt
from .presentation import ACTIVE_REVIEWS

SEVERITIES = ["critical", "high", "medium", "low", "none", "unknown"]
VARIABLES = {
    "organization",
    "contact_name",
    "contact_role",
    "language",
    "findings",
    "finding_count",
    "action",
    "audience",
    "item_count",
    "items",
}
DEFAULT_SUBJECT = "[Bearings] {{ finding_count }} vulnerability reviews · {{ organization }}"
DEFAULT_BODY = """Hello {{ contact_name }},

{{ audience }}
{{ finding_count }} active reviews concern registered software at {{ organization }}.

{{ findings }}

{{ action }}
Product registration alone does not confirm affectedness. CVSS is source severity, not business risk.
This is a local development message; no external delivery or compromise is asserted.
"""


def transport_configuration():
    mode = settings.NOTIFICATION_TRANSPORT
    if mode == "file":
        return mode, digest({"transport": "file"})
    if mode != "smtp" or settings.DEBUG or os.getenv("BEARINGS_DEV_STACK") == "1":
        raise ValidationError("SMTP outreach requires an explicitly configured non-development deployment")
    if (
        not settings.EMAIL_HOST
        or not 1 <= settings.EMAIL_PORT <= 65535
        or bool(settings.EMAIL_USE_TLS) == bool(settings.EMAIL_USE_SSL)
    ):
        raise ValidationError("Configure an approved SMTP host/port and exactly one verified TLS mode")
    validate_email(settings.DEFAULT_FROM_EMAIL)
    if settings.DEFAULT_FROM_EMAIL.lower().endswith((".invalid", "@localhost")):
        raise ValidationError("Configure a real approved notification sender")
    return mode, digest(
        {
            "transport": mode,
            "host": settings.EMAIL_HOST,
            "port": settings.EMAIL_PORT,
            "tls": settings.EMAIL_USE_TLS,
            "ssl": settings.EMAIL_USE_SSL,
            "user": settings.EMAIL_HOST_USER,
            "sender": settings.DEFAULT_FROM_EMAIL,
        }
    )


def require_transport(batch):
    mode, signature = transport_configuration()
    if batch.transport != mode or (batch.transport_fingerprint and batch.transport_fingerprint != signature):
        raise ValidationError("Notification transport/sender configuration changed; create a new preview")
    return mode


def scoped_organizations(user, mode):
    orgs = organizations_for(user)
    if mode == "circl":
        if not (user.is_superuser or is_analyst(user)):
            return orgs.none()
        return orgs.filter(operator_visibility=True)
    if user.is_superuser:
        return orgs
    return orgs.filter(membership__user=user, membership__role__in=["admin", "editor"]).distinct()


def render_text(template, values):
    # Real Django variable rendering, restricted to a documented, flat string context.
    # No tags, includes, filters, attribute traversal, callable/model values or loaders.
    if "{%" in template or "{#" in template:
        raise ValidationError("Template tags and comments are disabled. Use the documented variables only.")
    tokens = re.findall(r"{{(.*?)}}", template, flags=re.S)
    if any(t.strip() not in VARIABLES for t in tokens):
        raise ValidationError("Unknown template variable. Use the documented variables only.")
    remainder = re.sub(r"{{.*?}}", "", template, flags=re.S)
    if "{{" in remainder or "}}" in remainder:
        raise ValidationError("Unbalanced template variable.")
    return Engine(loaders=[]).from_string(template).render(Context(values, autoescape=False))


class NotificationForm(forms.Form):
    subscription_name = forms.CharField(
        max_length=120, required=False, label="Subscription name (draft preparation only)"
    )
    domain = forms.ChoiceField(
        required=False,
        choices=[
            ("vulnerabilities", "Vulnerability reviews"),
            ("asset_issues", "Lifecycle / exposure issues"),
        ],
        initial="vulnerabilities",
    )
    kind = forms.ChoiceField(
        required=False,
        choices=[("", "All issue types")]
        + [(key, label) for key, label in AssetIssue.KINDS if key != "vulnerability"],
    )

    mode = forms.ChoiceField(
        choices=[("circl", "CIRCL → affected organizations"), ("company", "Company → internal contacts")]
    )
    organization = forms.ModelChoiceField(queryset=Contact.objects.none(), required=False)
    product = forms.CharField(max_length=160, required=False, label="Installed product contains")
    cve = forms.CharField(max_length=120, required=False, label="Vulnerability identifier contains")
    severity = forms.ChoiceField(
        choices=[("", "All source severities (CVE only)")] + [(v, v.title()) for v in SEVERITIES],
        required=False,
        initial="high",
    )
    assessment = forms.ChoiceField(
        choices=[
            ("", "All actionable assessments"),
            ("affected", "Analyst: affected"),
            ("potential", "Analyst: potential"),
            ("unassessed", "Analyst: unassessed"),
            ("unknown", "Analyst: unknown"),
        ],
        required=False,
    )
    sort = forms.ChoiceField(
        choices=[
            ("severity", "Severity → criticality → organization"),
            ("organization", "Organization → product → asset"),
            ("product", "Product → organization → asset"),
        ]
    )
    subject_template = forms.CharField(max_length=250, initial=DEFAULT_SUBJECT)
    body_template = forms.CharField(
        max_length=12000, initial=DEFAULT_BODY, widget=forms.Textarea(attrs={"rows": 13})
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        mode = self.data.get("mode", "company") if self.is_bound else self.initial.get("mode", "company")
        self.fields["organization"].queryset = scoped_organizations(user, mode)
        if not (user.is_superuser or is_analyst(user)):
            self.fields["mode"].choices = [("company", "Company → internal contacts")]

    def clean(self):
        data = super().clean()
        if data.get("mode") == "company" and not data.get("organization"):
            self.add_error("organization", "Choose your company workspace.")
        for field in ["subject_template", "body_template"]:
            if field in data:
                try:
                    rendered = render_text(data[field], dict.fromkeys(VARIABLES, "Example"))
                    if field == "subject_template" and ("\n" in rendered or "\r" in rendered):
                        raise ValidationError("Subject must be a single line.")
                except ValidationError as exc:
                    self.add_error(field, exc)
        return data

    def filters(self):
        return {
            k: (
                self.cleaned_data[k].pk
                if k == "organization" and self.cleaned_data[k]
                else self.cleaned_data[k]
            )
            for k in ["organization", "product", "cve", "severity", "assessment", "sort", "domain", "kind"]
        }


def candidates(user, mode, filters):
    if filters.get("domain") == "asset_issues":
        from .issues import exportable_issues, active_filter

        qs = (
            exportable_issues(user)
            .filter(
                organization__in=scoped_organizations(user, mode),
                shareable=True,
                operator_only=False,
                finding__isnull=True,
                asset__lifecycle="active",
            )
            .filter(active_filter())
        )
        if mode == "company" and not filters.get("organization"):
            return qs.none()
        if filters.get("organization"):
            qs = qs.filter(organization_id=filters["organization"])
        if filters.get("kind"):
            qs = qs.filter(kind=filters["kind"])
        if filters.get("product"):
            qs = qs.filter(installation__product__name__icontains=filters["product"])
        qs = qs.annotate(
            notification_priority=Case(
                When(priority="critical", then=Value(0)),
                When(priority="high", then=Value(1)),
                When(priority="review", then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        order = {
            "organization": ["organization__name", "asset__name"],
            "product": ["installation__product__name", "organization__name"],
        }.get(filters.get("sort"), ["notification_priority", "organization__name"])
        return qs.order_by(*order, "asset__name", "pk")
    # Operator-only evidence can be investigated, but cannot be redistributed to companies.
    qs = (
        visible_findings_for(user)
        .filter(
            organization__in=scoped_organizations(user, mode),
            record__shareable=True,
            status__in=ACTIVE_REVIEWS,
            installation__asset__lifecycle="active",
        )
        .exclude(analyst_applicability="not_affected")
    )
    if filters.get("organization"):
        qs = qs.filter(organization_id=filters["organization"])
    if mode == "company" and not filters.get("organization"):
        return qs.none()
    for key, field in [
        ("product", "installation__product__name__icontains"),
        ("cve", "record__external_id__icontains"),
        ("severity", "record__source_severity"),
        ("assessment", "analyst_applicability"),
    ]:
        if filters.get(key):
            qs = qs.filter(**{field: filters[key]})
    qs = qs.annotate(
        notification_severity=Case(
            *[When(record__source_severity=v, then=Value(i)) for i, v in enumerate(SEVERITIES)],
            default=Value(5),
            output_field=IntegerField(),
        ),
        notification_criticality=Case(
            When(installation__asset__criticality="high", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
    )
    orders = {
        "severity": ["notification_severity", "notification_criticality", "organization__name"],
        "organization": ["organization__name", "installation__product__name"],
        "product": ["installation__product__name", "organization__name"],
    }
    return qs.order_by(
        *orders.get(filters.get("sort"), orders["severity"]), "installation__asset__name", "pk"
    )


def eligible_contacts(org):
    return Contact.objects.filter(
        organization=org,
        notification_enabled=True,
        invalid_delivery=False,
        reachable_at__isnull=False,
        reviewed_at__isnull=False,
        next_review__gt=timezone.localdate(),
    ).order_by("escalation_order", "pk")


def finding_snapshot(f):
    from .models import AssetIssue

    if isinstance(f, AssetIssue):
        from .issues import data_for

        data = data_for(f)
        facts = asset_context(f.asset)
        data["asset"] = {
            "name": f.asset.name,
            "criticality": f.asset.criticality,
            "team": f.asset.responsible_team,
            "facts": facts,
            "missing_since": str(f.asset.missing_since or ""),
        }
        data["timing"] = f.timing
        data["risks"] = list(
            f.risk_scenarios.filter(withdrawn_at__isnull=True)
            .order_by("pk")
            .values("issue_revision_id", "risk_revision_id", "reason")
        )
        path = reverse("issue", args=[f.organization.slug, f.pk])
        text = f"""{f.get_kind_display()}: {f.title} · Organizational priority {f.priority}
Asset: {f.asset.name} · criticality {f.asset.criticality} · owner {f.owner_team or f.asset.responsible_team or "Unassigned"}
IP: {", ".join(a["prefix"] for a in facts["addresses"]) or "Not recorded"} · DNS: {", ".join(d["name"] for d in facts["dns_names"]) or "Not recorded"}
Location: {" / ".join(r["name"] for r in facts["references"] if r["field"] in {"site", "location", "rack", "cluster"}) or "Not recorded"}
Product: {f.installation.product.name if f.installation_id else "Asset/contract issue"}
Reported expiry / EOL: {f.event_date or "Unknown / not applicable"} · Action due: {f.action_due or "Not recorded"}
Fact scope: {f.get_fact_scope_display()} · Evidence status: {f.fact_status} · Workflow: {f.current_status}
Source: {f.source_label} · {f.source_url or "No external URL"} · Observed {f.observed_at}
Evidence: {f.evidence_text}
Possible consequences: {f.consequence or "Unassessed"}
Next action: {f.next_action or "Review evidence and assign an owner"}
Bearings: {path}
NetBox: {f.asset.source_url or "No external source"}
These are evidence-backed review items, not automatically calculated business risk."""
        return {
            "id": str(f.pk),
            "evidence_hash": digest(data),
            "text": text,
            "source": f.source_label,
            "rule": "asset-issue/v1",
            "product_identifier": f.installation.product.identifier if f.installation_id else "",
        }
    asset, inst = f.installation.asset, f.installation
    facts = asset_context(asset)
    location = (
        " / ".join(
            ref["name"]
            for ref in facts["references"]
            if ref["field"] in {"site", "location", "rack", "cluster"}
        )
        or "Not recorded"
    )
    ips = ", ".join(a["prefix"] for a in facts["addresses"]) or "Not recorded"
    dns = ", ".join(d["name"] for d in facts["dns_names"]) or "Not recorded"
    path = reverse("intelligence", args=[f.organization.slug]) + f"?finding={f.pk}#finding-{f.pk}"
    text = f"""{f.record.external_id} · source severity {f.record.source_severity.upper()}
Product: {inst.product.name} · version {inst.version or "unknown"} · edition {inst.edition or "unknown"} · build {inst.build or "unknown"}
Asset: {asset.name} · criticality {asset.criticality} · team {asset.responsible_team or "Not assigned"}
IP: {ips} · DNS: {dns}
Location: {location} · U{facts["position"] or "?"} {facts["face"]}
Analyst assessment: {f.analyst_applicability} · automated applicability: {f.applicability} · workflow: {f.status}
Inventory missing since: {asset.missing_since or "not marked missing"}
Evidence and action in Bearings: {path}
NetBox: {asset.source_url or "No external source"}
Review explanation: {f.explanation[:3000]}"""
    return {
        "id": f.pk,
        "evidence_hash": digest(f.record.payload),
        "text": text,
        "source": f.record.source,
        "rule": f.rule,
        "product_identifier": inst.product.identifier,
    }


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def message_snapshot(mode, contact, findings, subject_template, body_template):
    snapshots = [finding_snapshot(f) for f in findings]
    issue_domain = bool(findings and getattr(findings[0], "kind", None))
    values = {
        "organization": contact.organization.name,
        "contact_name": contact.name,
        "contact_role": contact.role,
        "language": contact.language,
        "finding_count": str(len(findings)),
        "item_count": str(len(findings)),
        "items": "\n\n".join(s["text"] for s in snapshots),
        "findings": "\n\n".join(s["text"] for s in snapshots),
        "audience": "CIRCL requests your organization to review these findings."
        if mode == "circl"
        else "Internal security notification for your company.",
        "action": "Please review affectedness, assign an owner, plan remediation and acknowledge this notification in Bearings.",
    }
    subject = render_text(subject_template, values)
    body = render_text(body_template, values)
    if len(body.encode("utf-8")) > 1_000_000:
        raise ValidationError("Rendered message exceeds 1 MB; narrow the filters before previewing")
    if "\n" in subject or "\r" in subject or len(subject) > 250:
        raise ValidationError("Rendered subject must be one line and at most 250 characters.")
    snapshot = {
        "contact_id": contact.pk,
        "email": contact.email,
        "mode": mode,
        "findings": snapshots,
        "subject": subject,
        "body": body,
    }
    if settings.NOTIFICATION_TRANSPORT == "smtp":
        snapshot["transport"], snapshot["transport_configuration"] = transport_configuration()
    if issue_domain:
        snapshot["domain"] = "asset_issues"
    return snapshot, digest(snapshot), subject, body


@transaction.atomic
def preview_batch(user, mode, filters, subject_template, body_template):
    require(user.is_active and mode in {"circl", "company"})
    transport, transport_signature = transport_configuration()
    findings = list(candidates(user, mode, filters)[:501])
    if not findings:
        raise ValidationError("No active, redistributable findings match these filters.")
    if len(findings) > 500:
        raise ValidationError("More than 500 reviews match. Narrow the filters before previewing.")
    grouped = {}
    for f in findings:
        grouped.setdefault(f.organization_id, []).append(f)
    batch = NotificationBatch.objects.create(
        creator=user,
        mode=mode,
        transport=transport,
        transport_fingerprint=transport_signature,
        organization_id=filters.get("organization"),
        filters=filters,
        subject_template=subject_template,
        body_template=body_template,
    )
    count = 0
    for group in grouped.values():
        org = group[0].organization
        require(can_operator_review(user, org) if mode == "circl" else can_edit(user, org))
        audit(
            user,
            org,
            "notification.preview",
            batch.pk,
            finding_ids=[str(f.pk) if isinstance(f, AssetIssue) else f.pk for f in group],
        )
        contacts = list(eligible_contacts(org))
        if not contacts:
            raise ValidationError(
                "A matching organization has no opted-in contacts with verified email and a current role review. Update contacts or narrow the organization filter; no recipients were silently skipped."
            )
        for contact in contacts:
            count += 1
            if count > 100:
                raise ValidationError("More than 100 recipients match. Narrow the filters.")
            snapshot, fingerprint, subject, body = message_snapshot(
                mode, contact, group, subject_template, body_template
            )
            delivery = NotificationDelivery.objects.create(
                batch=batch,
                organization=org,
                contact=contact,
                snapshot=snapshot,
                fingerprint=fingerprint,
                subject=subject,
                body=body,
            )
            if filters.get("domain") == "asset_issues":
                delivery.issues.add(*group)
            else:
                delivery.findings.add(*group)
    if not count:
        raise ValidationError(
            "No opted-in contacts with verified email and a current role review. Update contacts first."
        )
    return batch


def authorized_delivery(user, delivery):
    org = delivery.organization
    if not organizations_for(user).filter(pk=org.pk).exists():
        return False
    ids = [f["id"] for f in delivery.snapshot["findings"]]
    if delivery.snapshot.get("domain") == "asset_issues":
        from .issues import exportable_issues

        return exportable_issues(user).filter(
            pk__in=ids, organization=org, shareable=True, operator_only=False
        ).count() == len(ids)
    # Even historical previews/messages disappear when redistribution is revoked.
    return visible_findings_for(user).filter(
        pk__in=ids, organization=org, record__shareable=True
    ).count() == len(ids)


@transaction.atomic
def claim_batch(user, batch_id, selected):
    batch = NotificationBatch.objects.select_for_update().get(pk=batch_id)
    require(batch.creator_id == user.pk and user.is_active)
    require_transport(batch)
    if batch.status != "draft":
        raise ValidationError("This batch was already approved. Create a new preview for further messages.")
    deliveries = list(
        batch.deliveries.select_related("organization", "contact__organization")
        .filter(pk__in=selected)
        .order_by("pk")
    )
    if not deliveries or len(deliveries) != len(selected):
        raise ValidationError("Choose recipients from this preview.")
    # All selected messages must still agree with their preview before any attempt is claimed.
    for d in deliveries:
        require(authorized_delivery(user, d))
        require(scoped_organizations(user, batch.mode).filter(pk=d.organization_id).exists())
        contact = eligible_contacts(d.organization).filter(pk=d.contact_id).first()
        if contact is None:
            raise ValidationError("Recipient review or consent changed. Create a new preview.")
        ids = [f["id"] for f in d.snapshot["findings"]]
        current = list(candidates(user, batch.mode, batch.filters).filter(pk__in=ids))
        if (
            len(current) != len(ids)
            or message_snapshot(batch.mode, contact, current, batch.subject_template, batch.body_template)[1]
            != d.fingerprint
        ):
            raise ValidationError(
                "Evidence, assessment, inventory or recipient changed. Create a new preview."
            )
    batch.status, batch.approved_at = "approved", timezone.now()
    batch.save(update_fields=["status", "approved_at"])
    for d in deliveries:
        try:
            with transaction.atomic():
                NotificationReceipt.objects.create(fingerprint=d.fingerprint, delivery=d)
            d.status = "filing"
        except IntegrityError:
            d.status = "duplicate"
        d.save(update_fields=["status"])
        audit(user, d.organization, "notification.approved", d.pk, status=d.status, batch=str(batch.pk))
    batch.deliveries.exclude(pk__in=selected).update(status="excluded")
    return [d.pk for d in deliveries if d.status == "filing"]


def approve_local(user, batch_id, selected):
    ids = claim_batch(user, batch_id, selected)
    # Separate committed attempt from file I/O. A crash leaves an explicit uncertain state;
    # the unique receipt prevents a second file from an automatic retry.
    for pk in ids:
        d = NotificationDelivery.objects.select_related("organization", "contact", "batch").get(pk=pk)
        # Recheck immediately before the only I/O. Policy edits can invalidate a claimed preview.
        try:
            if (
                not authorized_delivery(user, d)
                or not scoped_organizations(user, d.batch.mode).filter(pk=d.organization_id).exists()
            ):
                raise ValidationError("Current visibility no longer permits this message.")
            contact = eligible_contacts(d.organization).filter(pk=d.contact_id).first()
            current = list(
                candidates(user, d.batch.mode, d.batch.filters).filter(
                    pk__in=[f["id"] for f in d.snapshot["findings"]]
                )
            )
            if (
                contact is None
                or message_snapshot(
                    d.batch.mode, contact, current, d.batch.subject_template, d.batch.body_template
                )[1]
                != d.fingerprint
            ):
                raise ValidationError("Preview is stale.")
            # The reviewed batch pins the transport; changing EMAIL_BACKEND alone cannot send outreach.
            transport = require_transport(d.batch)
            backend = (
                EmailBackend(file_path=settings.EMAIL_FILE_PATH)
                if transport == "file"
                else SMTPBackend(timeout=10)
            )
            with backend as connection:
                sent = EmailMessage(
                    d.subject,
                    d.body,
                    settings.DEFAULT_FROM_EMAIL,
                    [d.snapshot["email"]],
                    connection=connection,
                    headers={"X-Bearings-Notification": str(d.pk)},
                ).send()
            if sent != 1:
                raise OSError("Local file backend did not confirm writing the message.")
            d.status, d.filed_at = ("filed" if transport == "file" else "accepted"), timezone.now()
        except (OSError, ValidationError, ValueError):
            d.status = "uncertain"
        d.save(update_fields=["status", "filed_at"])
        audit(
            user,
            d.organization,
            "notification.local_result" if d.batch.transport == "file" else "notification.smtp_result",
            d.pk,
            status=d.status,
        )
    return NotificationBatch.objects.get(pk=batch_id)
