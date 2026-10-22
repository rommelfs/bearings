"""Prepare reviewed drafts on content changes; subscriptions never approve or send messages."""

from datetime import timedelta
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .access import audit, require
from .models import NotificationBatch, NotificationSubscription
from .notifications import (
    candidates,
    digest,
    eligible_contacts,
    message_snapshot,
    preview_batch,
    scoped_organizations,
    transport_configuration,
    campaign_audience,
    campaign_limits,
)


@transaction.atomic
def create(actor, form):
    require(actor.is_active and form.is_valid())
    name = form.cleaned_data.get("subscription_name", "").strip()
    if not name:
        raise ValidationError("Name the subscription before enabling draft preparation")
    mode, filters = form.cleaned_data["mode"], form.filters()
    if filters.get("organization"):
        require(scoped_organizations(actor, mode).filter(pk=filters["organization"]).exists())
    else:
        require(mode == "circl" and scoped_organizations(actor, mode).exists())
    row = NotificationSubscription.objects.create(
        creator=actor,
        name=name,
        mode=mode,
        organization_id=filters.get("organization"),
        filters=filters,
        subject_template=form.cleaned_data["subject_template"],
        body_template=form.cleaned_data["body_template"],
    )
    audit(actor, row.organization, "notification.subscription_created", row.pk)
    return row


@transaction.atomic
def prepare(pk, due=False):
    row = (
        NotificationSubscription.objects.select_for_update(of=("self",))
        .select_related("creator", "organization")
        .get(pk=pk)
    )
    if not row.enabled or (
        due and row.last_checked and row.last_checked > timezone.now() - timedelta(minutes=10)
    ):
        return None
    row.last_checked = timezone.now()
    row.save(update_fields=["last_checked"])
    require(row.creator.is_active)
    if row.organization_id:
        require(scoped_organizations(row.creator, row.mode).filter(pk=row.organization_id).exists())
    else:
        require(row.mode == "circl" and scoped_organizations(row.creator, row.mode).exists())
    review_limit, recipient_limit = campaign_limits(row.mode, row.filters)
    current = list(candidates(row.creator, row.mode, row.filters)[: review_limit + 1])
    if len(current) > review_limit:
        raise ValidationError(f"Subscription matches more than {review_limit} reviews; narrow filters")
    if not current:
        row.error = "No currently eligible reviews; no new draft prepared."
        row.save(update_fields=["error"])
        return None
    groups = {}
    for item in current:
        groups.setdefault(item.organization_id, []).append(item)
    fingerprints = []
    for group in groups.values():
        contacts = list(eligible_contacts(group[0].organization))
        if not contacts:
            if row.mode == "circl" and row.filters.get("missing_contacts") == "exclude":
                continue
            raise ValidationError("A matching organization has no currently eligible contacts")
        for contact in contacts:
            fingerprints.append(
                message_snapshot(row.mode, contact, group, row.subject_template, row.body_template)[1]
            )
            if len(fingerprints) > recipient_limit:
                raise ValidationError(
                    f"Subscription matches more than {recipient_limit} recipients; narrow filters"
                )
    transport, transport_signature = transport_configuration()
    signature = digest(
        {
            "messages": sorted(fingerprints),
            "transport": transport,
            "configuration": transport_signature,
            "audience": campaign_audience(row.creator, row.mode, row.filters),
        }
    )
    if row.last_fingerprint == signature:
        row.error = ""
        row.save(update_fields=["error"])
        return row.last_batch
    batch = preview_batch(row.creator, row.mode, row.filters, row.subject_template, row.body_template)
    if row.last_batch_id:
        previous = NotificationBatch.objects.select_for_update().get(pk=row.last_batch_id)
        if previous.status == "draft":
            previous.status = "superseded"
            previous.save(update_fields=["status"])
            previous.deliveries.filter(status="draft").update(status="superseded")
    row.last_fingerprint, row.last_batch, row.error = signature, batch, ""
    row.save(update_fields=["last_fingerprint", "last_batch", "error"])
    audit(row.creator, row.organization, "notification.subscription_prepared", row.pk, batch=str(batch.pk))
    return batch
