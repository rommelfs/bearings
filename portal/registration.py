"""Email proof opens private access; CIRCL sharing needs separate approval; never claim infrastructure ownership."""

import hashlib
import ipaddress
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .access import audit, is_analyst, require
from .models import (
    Contact,
    InfrastructureClaim,
    InfrastructureRegistration,
    InventoryReviewPolicy,
    InventorySource,
    Membership,
    Organization,
    PublicRegistrationBucket,
)
from .service_mail import public_base, send_service_mail
from .registration_forms import REGISTRATION_COMMITMENTS_VERSION


def permit_public_attempt(request):
    peer = request.META.get("REMOTE_ADDR", "unknown")
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        try:
            peer = str(ipaddress.ip_address(request.META.get("HTTP_X_FORWARDED_FOR", peer)))
        except ValueError:
            pass
    hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    key = salted_hmac("reporting-registration-rate", f"{peer}|{hour.isoformat()}").hexdigest()
    with transaction.atomic():
        bucket, _ = PublicRegistrationBucket.objects.get_or_create(
            key=key, defaults={"expires_at": hour + timedelta(hours=2)}
        )
        bucket = PublicRegistrationBucket.objects.select_for_update().get(pk=bucket.pk)
        if bucket.attempts >= settings.PUBLIC_REGISTRATION_LIMIT:
            return False
        bucket.attempts += 1
        bucket.save(update_fields=["attempts"])
    return True


@transaction.atomic
def submit_registration(form):
    user = form.save(commit=False)
    user.email = form.cleaned_data["email"]
    user.is_active = False
    user.set_unusable_password()
    user.save()
    now = timezone.now()
    return InfrastructureRegistration.objects.create(
        user=user,
        company_name=form.cleaned_data["company_name"],
        contact_name=form.cleaned_data["contact_name"],
        email=user.email,
        emergency_phone=form.cleaned_data["emergency_phone"],
        authority_attested_at=now,
        periodic_review_consented_at=now,
        updates_committed_at=now,
        commitments_version=REGISTRATION_COMMITMENTS_VERSION,
        scopes=form.cleaned_data["scopes"],
        review_days=InventoryReviewPolicy._meta.get_field("interval_days").get_default(),
        email_reminders=True,
        verification_digest=secrets.token_hex(32),
        verification_expires=timezone.now(),
    )


@transaction.atomic
def issue_verification(pk):
    item = InfrastructureRegistration.objects.select_for_update().get(pk=pk)
    now = timezone.now()
    if item.status != "awaiting_email" or (
        item.verification_attempted_at and item.verification_attempted_at > now - timedelta(minutes=15)
    ):
        return False
    raw = secrets.token_urlsafe(32)
    item.verification_digest = hashlib.sha256(raw.encode()).hexdigest()
    item.verification_expires = now + timedelta(hours=24)
    item.verification_attempted_at = now
    item.verification_error = False
    try:
        base = public_base()
        send_service_mail(
            "Confirm your Bearings registration email",
            f"An organization registration was requested for {item.company_name}. Confirm the email and set your own password to open your private workspace. CIRCL will review sharing separately.\n\n"
            f"Open {base}/register/verify/#token={raw}\n\n"
            f"Or open {base}/register/verify/ and enter this one-use code:\n{raw}\n\n"
            "This code expires in 24 hours. Opening the link alone does not confirm anything. Ignore this message if you did not request an account.",
            item.email,
        )
    except Exception:
        # No SMTP bodies, tokens or credentials enter logs or persistent errors.
        item.verification_error = True
    item.save(
        update_fields=[
            "verification_digest",
            "verification_expires",
            "verification_attempted_at",
            "verification_error",
        ]
    )
    audit(None, None, "registration.verification_prepared", item.pk, success=not item.verification_error)
    return not item.verification_error


@transaction.atomic
def verify_registration(raw, password):
    if not raw or len(raw) > 128:
        return False
    item = (
        InfrastructureRegistration.objects.select_for_update()
        .filter(verification_digest=hashlib.sha256(raw.encode()).hexdigest())
        .first()
    )
    if not item or item.status != "awaiting_email" or item.verification_expires <= timezone.now():
        return False
    user = get_user_model().objects.select_for_update().get(pk=item.user_id)
    if (
        user.is_active
        or user.is_staff
        or user.is_superuser
        or user.groups.exists()
        or user.has_usable_password()
        or Membership.objects.filter(user=user).exists()
    ):
        return False
    validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    item.email_verified_at = timezone.now()
    org = Organization.objects.create(
        name=item.company_name, slug=f"reporting-{item.pk.hex[:20]}", operator_visibility=False
    )
    InventorySource.objects.create(organization=org, mode="manual", import_enabled=False)
    for scope in item.scopes:
        claim = InfrastructureClaim(
            organization=org,
            kind=scope["kind"],
            value=scope["value"],
            network_context=scope.get("network_context", ""),
            status="declared",
        )
        claim.full_clean()
        claim.save()
    Contact.objects.create(
        organization=org,
        name=item.contact_name,
        email=item.email,
        emergency_phone=item.emergency_phone,
        role="Registered infrastructure responsible",
        reachable_at=item.email_verified_at,
        notification_enabled=item.email_reminders,
        next_review=timezone.localdate(),
    )
    Membership.objects.create(organization=org, user=user, role="admin")
    InventoryReviewPolicy.objects.create(
        organization=org,
        interval_days=item.review_days,
        email_enabled=item.email_reminders,
        next_due=timezone.localdate(),
        next_reminder_at=timezone.now() + timedelta(days=1),
    )
    user.is_active = True
    user.save(update_fields=["is_active"])
    item.organization = org
    item.status = "awaiting_review"
    item.save(update_fields=["email_verified_at", "organization", "status"])
    audit(None, item.organization, "registration.email_verified", item.pk)
    return item


@transaction.atomic
def decide_registration(actor, pk, decision, note):
    require(actor.is_superuser or is_analyst(actor))
    item = InfrastructureRegistration.objects.select_for_update().get(pk=pk)
    if decision == "notify":
        require(item.status in {"approved", "rejected"})
        return item
    require(item.status == "awaiting_review")
    if decision == "approve":
        require(item.status == "awaiting_review" and item.email_verified_at is not None)
        user = get_user_model().objects.select_for_update().get(pk=item.user_id)
        require(
            user.is_active
            and item.organization_id is not None
            and Membership.objects.filter(
                user=user, organization_id=item.organization_id, role="admin"
            ).exists()
        )
        org = Organization.objects.select_for_update().get(pk=item.organization_id)
        require(not org.operator_visibility)
        org.operator_visibility = True
        org.save(update_fields=["operator_visibility"])
        item.status = "approved"
    elif decision == "reject":
        item.status = "rejected"
    else:
        raise ValidationError("Unsupported registration decision")
    item.reviewed_by, item.reviewed_at, item.review_note = actor, timezone.now(), note
    item.save(update_fields=["organization", "status", "reviewed_by", "reviewed_at", "review_note"])
    audit(actor, item.organization, "registration.reviewed", item.pk, decision=decision)
    return item


@transaction.atomic
def notify_decision(pk):
    item = (
        InfrastructureRegistration.objects.select_for_update()
        .select_related("user", "organization")
        .get(pk=pk)
    )
    if (
        not item.email_verified_at
        or item.status not in {"approved", "rejected"}
        or item.decision_mail_sent_at
    ):
        return False
    try:
        base = public_base()
        if item.status == "approved":
            body = f"CIRCL access is approved for your organization. Continue signing in with your portal username {item.user.username}.\n{base}/organizations/{item.organization.slug}/review/\n\nReview your declared scopes and contacts, and add servers/software versions when available. Scope authority is not automatically verified. SSO accounts are managed separately."
        else:
            body = f"CIRCL visibility was not approved. Your private workspace remains available. Contact the operator if you need assistance.\n{base}/accounts/login/"
        send_service_mail("Your Bearings reporting application", body, item.email)
    except Exception:
        audit(None, item.organization, "registration.decision_mail_failed", item.pk)
        return False
    item.decision_mail_sent_at = timezone.now()
    item.save(update_fields=["decision_mail_sent_at"])
    return True
