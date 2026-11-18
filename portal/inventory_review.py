"""Owner attestations and durable, deduplicated service reminders; no authority inference."""

import hashlib
import json
from datetime import datetime, time, timedelta
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .access import audit, is_analyst, require, role_for
from .models import (
    Asset,
    Contact,
    InfrastructureClaim,
    InfrastructureRegistration,
    Installation,
    InventoryReviewConfirmation,
    InventoryReviewDelivery,
    InventoryReviewPolicy,
    InventorySource,
    Organization,
    OrganizationConfiguration,
)
from .service_mail import public_base, send_service_mail

SALT = "inventory-owner-review/v1"


def owner_can_review(user, org):
    return user.is_superuser or role_for(user, org) == "admin"


def can_configure_review(user, org):
    return user.is_active and (
        user.is_superuser
        or (is_analyst(user) and Organization.objects.filter(pk=org.pk, operator_visibility=True).exists())
    )


def mandatory_review_mail(org):
    return InfrastructureRegistration.objects.filter(
        organization=org, periodic_review_consented_at__isnull=False
    ).exists()


def snapshot(org):
    assets = Asset.objects.filter(organization=org, source__organization=org)
    installed = Installation.objects.filter(asset__in=assets, product__organization=org)
    configuration = OrganizationConfiguration.objects.filter(organization=org)
    queries = [
        ("configuration", configuration.values("id", "pgp_public_key", "smime_certificate", "ail_enabled", "ail_keywords", "ail_honeytokens", "ail_notification_email")),
        (
            "contacts",
            Contact.objects.filter(organization=org).values(
                "id",
                "name",
                "email",
                "phone",
                "emergency_phone",
                "function",
                "role",
                "notification_enabled",
                "reachable_at",
                "invalid_delivery",
                "reviewed_at",
                "next_review",
            ),
        ),
        (
            "scopes",
            InfrastructureClaim.objects.filter(organization=org).values(
                "id", "kind", "value", "network_context", "status", "valid_from", "valid_until"
            ),
        ),
        (
            "assets",
            assets.values(
                "id",
                "name",
                "kind",
                "criticality",
                "lifecycle",
                "source_id",
                "responsible_team",
                "responsible_contact_id",
                "upstream_data",
                "missing_since",
            ),
        ),
        (
            "installations",
            installed.values(
                "id",
                "asset_id",
                "product_id",
                "product__name",
                "product__identifier",
                "version",
                "build",
                "edition",
                "component_type",
                "is_operating_system",
            ),
        ),
    ]
    digest, counts = hashlib.sha256(), {"unknown_versions": 0}
    digest.update(
        json.dumps(
            {
                "organization": org.pk,
                "postal_address": Organization.objects.values_list("postal_address", flat=True).get(
                    pk=org.pk
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    for label, query in queries:
        digest.update(label.encode())
        counts[label] = 0
        for row in query.order_by("pk").iterator(chunk_size=500):
            digest.update(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode())
            counts[label] += 1
            if label == "installations" and not row["version"]:
                counts["unknown_versions"] += 1
    return digest.hexdigest(), counts


def review_token(user, policy, data_digest):
    return signing.dumps(
        {
            "actor": user.pk,
            "organization": policy.organization_id,
            "revision": policy.updated_at.isoformat(),
            "digest": data_digest,
        },
        salt=SALT,
        compress=True,
    )


@transaction.atomic
def configure_review(user, org, data):
    org = Organization.objects.select_for_update().get(pk=org.pk)
    require(can_configure_review(user, org))
    policy, _ = InventoryReviewPolicy.objects.get_or_create(organization=org)
    policy = InventoryReviewPolicy.objects.select_for_update().get(pk=policy.pk)
    for field in ["interval_days", "reminder_days"]:
        setattr(policy, field, data[field])
    policy.email_enabled = True if mandatory_review_mail(org) else data["email_enabled"]
    policy.next_due = (
        policy.last_reviewed_at.date() + timedelta(days=policy.interval_days)
        if policy.last_reviewed_at
        else timezone.localdate()
    )
    policy.next_reminder_at = (
        timezone.now()
        if policy.next_due <= timezone.localdate()
        else timezone.make_aware(datetime.combine(policy.next_due, time.min))
    )
    policy.full_clean()
    policy.save()
    audit(
        user,
        org,
        "inventory.review_schedule_changed",
        policy.pk,
        interval_days=policy.interval_days,
        reminder_days=policy.reminder_days,
        email_enabled=policy.email_enabled,
    )
    return policy


@transaction.atomic
def confirm_review(user, org, token):
    require(owner_can_review(user, org))
    Organization.objects.select_for_update().get(pk=org.pk)
    # Imports and manual asset submissions lock this authoritative source too.
    list(InventorySource.objects.select_for_update().filter(organization=org))
    policy = InventoryReviewPolicy.objects.select_for_update().get(organization=org)
    try:
        proof = signing.loads(token, salt=SALT, max_age=3600)
    except signing.BadSignature:
        raise ValidationError("The review form expired. Reload and check the current data.") from None
    digest, counts = snapshot(org)
    if proof != {
        "actor": user.pk,
        "organization": org.pk,
        "revision": policy.updated_at.isoformat(),
        "digest": digest,
    }:
        raise ValidationError(
            "The reporting data or schedule changed. Reload and review the current data before confirming."
        )
    now = timezone.now()
    due = timezone.localdate() + timedelta(days=policy.interval_days)
    key = hashlib.sha256(f"{policy.pk}|{timezone.localdate()}|{digest}".encode()).hexdigest()
    record, created = InventoryReviewConfirmation.objects.get_or_create(
        fingerprint=key,
        defaults={"policy": policy, "actor": user, "data_digest": digest, "counts": counts, "next_due": due},
    )
    if created:
        policy.last_reviewed_at, policy.last_reviewed_by, policy.next_due = now, user, due
        policy.next_reminder_at = timezone.make_aware(datetime.combine(due, time.min))
        policy.save()
        InventoryReviewDelivery.objects.filter(policy=policy, status__in=["pending", "error"]).update(
            status="suppressed", error="Reporting data was reviewed"
        )
        audit(user, org, "inventory.owner_reviewed", record.pk, digest=digest, counts=counts)
    return record


def reminder_recipients(policy):
    org = policy.organization
    contacts = set(
        Contact.objects.filter(
            organization=org, notification_enabled=True, reachable_at__isnull=False, invalid_delivery=False
        )
        .exclude(function="dpo")
        .values_list("email", flat=True)
    )
    owners = InfrastructureRegistration.objects.filter(
        organization=org,
        status__in=["awaiting_review", "approved", "rejected"],
        email_verified_at__isnull=False,
        user__is_active=True,
        user__membership__organization=org,
        user__membership__role="admin",
    ).select_related("user")
    for owner in owners:
        if owner.user.email.casefold() == owner.email:
            contacts.add(owner.email)
    return sorted({email.casefold() for email in contacts if email})


@transaction.atomic
def queue_review_reminders(pk):
    policy = InventoryReviewPolicy.objects.select_for_update().select_related("organization").get(pk=pk)
    now, today = timezone.now(), timezone.localdate()
    if not policy.email_enabled or policy.next_due > today or policy.next_reminder_at > now:
        return 0
    recipients = reminder_recipients(policy)
    total = 0
    for recipient in recipients:
        key = hashlib.sha256(f"{policy.pk}|{policy.next_due}|{today}|{recipient}".encode()).hexdigest()
        _, created = InventoryReviewDelivery.objects.get_or_create(
            fingerprint=key, defaults={"policy": policy, "due_date": policy.next_due, "recipient": recipient}
        )
        total += int(created)
    policy.next_reminder_at = now + timedelta(days=policy.reminder_days if recipients else 1)
    # Queue scheduling must not invalidate a human's open review form.
    InventoryReviewPolicy.objects.filter(pk=policy.pk).update(next_reminder_at=policy.next_reminder_at)
    audit(None, policy.organization, "inventory.review_reminders_queued", policy.pk, count=total)
    return total


@transaction.atomic
def deliver_review_reminder(pk):
    policy_id = InventoryReviewDelivery.objects.values_list("policy_id", flat=True).get(pk=pk)
    policy = (
        InventoryReviewPolicy.objects.select_for_update().select_related("organization").get(pk=policy_id)
    )
    item = InventoryReviewDelivery.objects.select_for_update().get(pk=pk)
    if item.status not in {"pending", "error"} or item.attempts >= 3 or item.next_attempt > timezone.now():
        return
    if (
        not policy.email_enabled
        or policy.next_due != item.due_date
        or policy.next_due > timezone.localdate()
        or item.recipient not in reminder_recipients(policy)
    ):
        item.status, item.error = "suppressed", "Current review schedule or recipient eligibility changed"
    else:
        item.attempts += 1
        try:
            send_service_mail(
                "Please review your infrastructure data",
                f"Your periodic infrastructure-data review and email reactivity check are due. Sign in at {public_base()}/organizations/{policy.organization.slug}/review/\n\n"
                "Please check contacts, declared IP ranges, static IPs, domains and any assets/software versions. Confirm the current data or correct it first. An active response is required; opening this email alone does not complete the review. This is a data-review service reminder, not a vulnerability alert.\n"
                "Review frequency is managed by the platform administrator or CIRCL. Confirm your data review in your organization area.",
                item.recipient,
                item.fingerprint,
            )
        except Exception:
            item.status, item.error = "error", "Service email failed; check the operator mail configuration"
            item.next_attempt = timezone.now() + timedelta(minutes=15 * 2 ** (item.attempts - 1))
        else:
            item.status, item.error, item.sent_at = "sent", "", timezone.now()
    item.save()
    audit(
        None,
        policy.organization,
        "inventory.review_reminder_delivery",
        item.pk,
        status=item.status,
        attempt=item.attempts,
    )
