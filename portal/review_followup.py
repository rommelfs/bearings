"""Reviewed follow-through using the existing durable review deliveries; no automatic escalation."""

import hashlib
from datetime import timedelta
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from .access import audit, require
from .inventory_review import can_configure_review, reminder_recipients
from .models import InventoryReviewPolicy, InventoryReviewDelivery, InventoryReviewConfirmation


def deliveries_for(policy):
    completed = InventoryReviewConfirmation.objects.filter(
        policy=policy, review_due_date=OuterRef("due_date"), reviewed_at__gte=OuterRef("created_at")
    )
    return policy.deliveries.annotate(acknowledged=Exists(completed)).order_by("-created_at", "-pk")


def delivery_label(item):
    if item.acknowledged:
        return "Data review completed"
    if item.delivery_outcome == "bounced":
        return "Bounce reported · response outstanding"
    if item.delivery_outcome == "delivered":
        return "Delivery reported · response outstanding"
    if item.status == "sent":
        return (
            "Written to local mail files · response outstanding"
            if item.transport == "file"
            else "Accepted by SMTP relay · response outstanding"
            if item.transport == "smtp"
            else "Sent using legacy transport · delivery and response unknown"
        )
    if item.status == "error":
        return "Send failed · retries exhausted" if item.attempts >= 3 else "Send failed · retry scheduled"
    return "Queued" if item.status == "pending" else "Suppressed by current policy"


def preview_token(actor, policy, recipient):
    require(can_configure_review(actor, policy.organization))
    if policy.next_due > timezone.localdate() or recipient not in reminder_recipients(policy):
        raise ValidationError(
            "Review is no longer due or this recipient is not currently eligible. Verify contact details first."
        )
    recent = policy.deliveries.filter(
        due_date=policy.next_due,
        recipient=recipient,
        created_at__gte=timezone.now() - timedelta(days=policy.reminder_days),
    ).exists()
    if recent:
        raise ValidationError(
            "A request for this recipient already exists within the reminder cooldown. Inspect its status first."
        )
    return signing.dumps(
        {
            "actor": actor.pk,
            "policy": policy.pk,
            "due": str(policy.next_due),
            "recipient": recipient,
            "revision": policy.updated_at.isoformat(),
        },
        salt="review-followup",
    )


@transaction.atomic
def queue_followup(actor, policy_id, token):
    policy = (
        InventoryReviewPolicy.objects.select_for_update().select_related("organization").get(pk=policy_id)
    )
    require(can_configure_review(actor, policy.organization))
    try:
        proof = signing.loads(token, salt="review-followup", max_age=900)
    except signing.BadSignature:
        raise ValidationError("Follow-up preview expired. Review the recipients again.") from None
    expected = {
        "actor": actor.pk,
        "policy": policy.pk,
        "due": str(policy.next_due),
        "recipient": proof.get("recipient"),
        "revision": policy.updated_at.isoformat(),
    }
    if proof != expected:
        raise ValidationError("Review or recipient context changed; preview the follow-up again.")
    preview_token(actor, policy, proof["recipient"])
    key = hashlib.sha256(
        f"{policy.pk}|{policy.next_due}|{timezone.localdate()}|{proof['recipient']}".encode()
    ).hexdigest()
    item, created = InventoryReviewDelivery.objects.get_or_create(
        fingerprint=key,
        defaults={
            "policy": policy,
            "due_date": policy.next_due,
            "recipient": proof["recipient"],
            "requested_by": actor,
        },
    )
    audit(actor, policy.organization, "inventory.review_followup_requested", item.pk, created=created)
    return item


@transaction.atomic
def record_feedback(actor, item_id, outcome, note):
    policy_id = InventoryReviewDelivery.objects.values_list("policy_id", flat=True).get(pk=item_id)
    policy = (
        InventoryReviewPolicy.objects.select_for_update().select_related("organization").get(pk=policy_id)
    )
    require(can_configure_review(actor, policy.organization))
    item = InventoryReviewDelivery.objects.select_for_update().get(pk=item_id, policy=policy)
    if (
        outcome not in {"bounced", "delivered"}
        or not note.strip()
        or len(note) > 1000
        or item.status != "sent"
        or item.transport != "smtp"
    ):
        raise ValidationError(
            "Record delivery/bounce evidence only for an SMTP-accepted message, with a short source justification"
        )
    before = item.delivery_outcome
    item.delivery_outcome, item.feedback_note = outcome, note.strip()
    item.feedback_at, item.feedback_by = timezone.now(), actor
    item.save(update_fields=["delivery_outcome", "feedback_note", "feedback_at", "feedback_by"])
    audit(
        actor,
        policy.organization,
        "inventory.delivery_feedback",
        item.pk,
        before=before,
        outcome=outcome,
        note=note.strip(),
    )
    return item
