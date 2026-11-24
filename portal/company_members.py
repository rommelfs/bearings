"""Organization-admin invitations. Mailbox proof never grants platform or upstream roles."""

import hashlib
import secrets
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from .access import audit, require
from .models import Membership, Organization, OrganizationInvitation
from .service_mail import public_base, send_service_mail


def admin(actor, org):
    return (
        actor.is_active
        and not org.merged_into_id
        and Membership.objects.filter(user=actor, organization=org, role="admin").exists()
    )


@transaction.atomic
@sensitive_variables()
def invite(actor, org, email, role, *, domain_code=None):
    org = Organization.objects.select_for_update().get(pk=org.pk)
    require(admin(actor, org))
    if role not in dict(Membership.ROLES):
        raise ValidationError("Choose a company role")
    email = email.strip().casefold()
    validate_email(email)
    now = timezone.now()
    recent = OrganizationInvitation.objects.filter(organization=org, created_at__gt=now - timedelta(hours=1))
    if recent.count() >= 30 or recent.filter(email=email, created_at__gt=now - timedelta(minutes=5)).exists():
        raise ValidationError("Invitation limit reached. Wait before sending another invitation.")
    # Public domain requests cannot cancel a personal administrator-issued invitation.
    pending = OrganizationInvitation.objects.filter(
        organization=org, email=email, consumed_at=None, revoked_at=None
    )
    if domain_code is not None:
        from .domain_membership import active, domain_name

        require(
            active(domain_code, org)
            and domain_code.creator_id == actor.pk
            and domain_code.role == role
            and domain_name(email.rsplit("@", 1)[1]) == domain_code.domain
        )
        pending = pending.filter(domain_code=domain_code)
    pending.update(revoked_at=now)
    raw = secrets.token_urlsafe(32)
    item = OrganizationInvitation.objects.create(
        organization=org,
        inviter=actor,
        email=email,
        role=role,
        domain_code=domain_code,
        digest=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=min(now + timedelta(hours=72), domain_code.expires_at)
        if domain_code
        else now + timedelta(hours=72),
    )
    try:
        send_service_mail(
            "Invitation to join a Bearings organization",
            f"You have been invited to join {org.name} as {dict(Membership.ROLES)[role]}.\n\n"
            f"Open {public_base()}/join/#token={raw}\n\nOr enter this code at /join/:\n{raw}\n\n"
            f"Expires at {item.expires_at.isoformat()}. Existing users must sign in to their own account. Opening the link alone does not join. Ignore unexpected invitations.",
            email,
        )
    except Exception:
        item.mail_error = True
        item.save(update_fields=["mail_error"])
    audit(actor, org, "membership.invited", item.pk, role=role, mail_prepared=not item.mail_error)
    return item


@transaction.atomic
@sensitive_variables()
def accept(actor, code, *, username="", first_name="", last_name="", password=""):
    key = hashlib.sha256(code.encode()).hexdigest()
    context = (
        OrganizationInvitation.objects.filter(digest=key).values_list("organization_id", flat=True).first()
    )
    if not context:
        raise ValidationError("Invitation is unavailable or expired")
    org = Organization.objects.select_for_update().get(pk=context)
    item = OrganizationInvitation.objects.select_for_update().select_related("inviter").get(digest=key)
    now = timezone.now()
    if item.revoked_at or item.consumed_at or item.expires_at <= now or not admin(item.inviter, org):
        raise ValidationError("Invitation is unavailable or expired")
    if item.domain_code_id:
        from .domain_membership import active, domain_name

        domain_code = item.domain_code
        if (
            not active(domain_code, org)
            or item.role != domain_code.role
            or domain_name(item.email.rsplit("@", 1)[1]) != domain_code.domain
        ):
            raise ValidationError("Invitation is unavailable or expired")
    User = get_user_model()
    accounts = User.objects.select_for_update().filter(email__iexact=item.email)
    if actor.is_authenticated:
        user = User.objects.select_for_update().get(pk=actor.pk)
        require(user.is_active and user.email.casefold() == item.email and accounts.count() == 1)
    else:
        if accounts.exists():
            raise ValidationError(
                "Sign in with your existing account, then accept this invitation. Your password will not be changed."
            )
        if not username or not first_name or not last_name or not password:
            raise ValidationError("New members must provide a username, first name, last name and password")
        user = User(username=username, email=item.email, first_name=first_name, last_name=last_name)
        validate_password(password, user)
        user.full_clean(exclude=["password"])
        user.set_password(password)
        user.save()
    membership, created = Membership.objects.get_or_create(
        organization=org, user=user, defaults={"role": item.role}
    )
    # An invitation cannot silently change an existing member's privileges.
    item.consumed_at = now
    item.save(update_fields=["consumed_at"])
    audit(user, org, "membership.invitation_accepted", item.pk, created=created, role=membership.role)
    return org


@transaction.atomic
def change_member(actor, org, member_id, role):
    org = Organization.objects.select_for_update().get(pk=org.pk)
    require(admin(actor, org))
    member = Membership.objects.select_for_update().filter(pk=member_id, organization=org).first()
    if member is None:
        raise ValidationError("Membership changed; reload the member list")
    if role not in {"remove", *dict(Membership.ROLES)}:
        raise ValidationError("Choose a company role")
    if (
        member.role == "admin"
        and member.user.is_active
        and role != "admin"
        and org.membership_set.filter(role="admin", user__is_active=True).count() <= 1
    ):
        raise ValidationError("Keep at least one active company administrator")
    audit(actor, org, "membership.changed", member.pk, previous=member.role, role=role)
    if role == "remove":
        member.delete()
    else:
        member.role = role
        member.save(update_fields=["role"])
