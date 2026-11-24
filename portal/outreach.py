"""Timed follow-up drafts. Every external delivery still requires separate review/approval."""

from datetime import timedelta
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .access import audit, require
from .models import NotificationDelivery, NotificationFollowup, OutreachPolicy
from .notifications import authorized_delivery, preview_batch, scoped_organizations


class PolicyForm(forms.ModelForm):
    class Meta:
        model = OutreachPolicy
        fields = ["include_dpo", "reminder_days", "escalation_days"]


@transaction.atomic
def prepare_followups(pk):
    original = (
        NotificationDelivery.objects.select_for_update()
        .select_related("batch__creator", "organization", "contact")
        .get(pk=pk)
    )
    original.followup_checked_at = timezone.now()
    original.save(update_fields=["followup_checked_at"])
    if original.batch_id and NotificationFollowup.objects.filter(batch_id=original.batch_id).exists():
        return 0
    if original.acknowledged_at:
        for row in original.followups.select_related("batch"):
            if row.batch_id and row.batch.status == "draft":
                row.batch.status = "cancelled"
                row.batch.save(update_fields=["status"])
                row.batch.deliveries.filter(status="draft").update(status="cancelled")
        return 0
    policy = OutreachPolicy.objects.filter(organization=original.organization).first()
    if not policy or original.status not in {"filed", "accepted"} or not original.filed_at:
        return 0
    count = 0
    for kind, days in [("reminder", policy.reminder_days), ("escalation", policy.escalation_days)]:
        if not days or original.filed_at + timedelta(days=days) > timezone.now():
            continue
        row, _ = NotificationFollowup.objects.get_or_create(delivery=original, kind=kind)
        if row.batch_id or row.checked_at > timezone.now() - timedelta(minutes=10) and row.error:
            continue
        actor = original.batch.creator
        try:
            with transaction.atomic():
                require(actor.is_active and authorized_delivery(actor, original))
                require(
                    scoped_organizations(actor, original.batch.mode)
                    .filter(pk=original.organization_id)
                    .exists()
                )
                filters = dict(original.batch.filters)
                filters.update(
                    organization=original.organization_id,
                    organizations=[],
                    audience_scope="single",
                    missing_contacts="block",
                    review_ids=[f["id"] for f in original.snapshot["findings"]],
                    followup_delivery=original.pk,
                    followup_kind=kind,
                )
                if kind == "reminder":
                    filters["recipient_contact"] = original.contact_id
                else:
                    filters.update(escalation_only=True, after_order=original.contact.escalation_order)
                batch = preview_batch(
                    actor,
                    original.batch.mode,
                    filters,
                    f"[Bearings {kind}] {{{{ item_count }}}} open reviews · {{{{ organization }}}}",
                    f"{kind.title()}: the original notification from {original.filed_at.date()} has not been acknowledged in Bearings.\n\n"
                    + original.batch.body_template,
                )
        except (ValidationError, PermissionDenied):
            row.error = "Follow-up blocked: review current access, active evidence and eligible recipient roles. No message approved or sent."
        else:
            row.batch, row.error = batch, ""
            audit(
                actor,
                original.organization,
                "notification.followup_prepared",
                row.pk,
                kind=kind,
                batch=str(batch.pk),
            )
            count += 1
        row.checked_at = timezone.now()
        row.save(update_fields=["batch", "error", "checked_at"])
    return count
