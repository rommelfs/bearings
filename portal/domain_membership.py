"""Reusable domain codes request one-use mailbox challenges; they never directly grant access."""

import hashlib
import secrets
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.core.validators import validate_domain_name, validate_email
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from .access import audit, require
from .company_members import admin, invite
from .models import Organization, OrganizationDomainCode, OrganizationInvitation


def domain_name(value):
    try:
        domain = value.strip().removeprefix("@").encode("idna").decode("ascii").lower()
        validate_domain_name(domain)
    except (UnicodeError, ValidationError, AttributeError):
        raise ValidationError("Enter an exact email domain such as circl.lu") from None
    if "." not in domain or domain.endswith(".") or len(domain) > 253:
        raise ValidationError("Enter an exact email domain such as circl.lu")
    return domain


def active(item, org):
    return (
        item.organization_id == org.pk
        and not item.revoked_at
        and item.expires_at > timezone.now()
        and item.role in {"reader", "editor"}
        and admin(item.creator, org)
        and OrganizationInvitation.objects.filter(domain_code=item, consumed_at__isnull=False).count()
        < item.max_acceptances
    )


@transaction.atomic
@sensitive_variables()
def create(actor, org, domain, role="reader", days=30, max_acceptances=100):
    org = Organization.objects.select_for_update().get(pk=org.pk)
    require(admin(actor, org))
    domain = domain_name(domain)
    if role not in {"reader", "editor"} or not 1 <= days <= 90 or not 1 <= max_acceptances <= 10000:
        raise ValidationError("Choose reader/editor, 1–90 days and 1–10,000 acceptances")
    # Keep shared-code administration bounded even if an administrator automates creation.
    if (
        OrganizationDomainCode.objects.filter(
            organization=org, revoked_at=None, expires_at__gt=timezone.now()
        ).count()
        >= 20
    ):
        raise ValidationError("Revoke an existing domain code before adding another")
    raw = secrets.token_urlsafe(32)
    item = OrganizationDomainCode.objects.create(
        organization=org,
        creator=actor,
        domain=domain,
        role=role,
        digest=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=days),
        max_acceptances=max_acceptances,
    )
    audit(
        actor,
        org,
        "membership.domain_code_created",
        item.pk,
        domain=domain,
        role=role,
        max_acceptances=max_acceptances,
    )
    return item, raw


@transaction.atomic
def revoke(actor, org, pk):
    org = Organization.objects.select_for_update().get(pk=org.pk)
    require(admin(actor, org))
    item = OrganizationDomainCode.objects.filter(pk=pk, organization=org).first()
    if not item:
        raise ValidationError("Domain code unavailable")
    item.revoked_at = timezone.now()
    item.save(update_fields=["revoked_at"])
    OrganizationInvitation.objects.filter(domain_code=item, consumed_at=None, revoked_at=None).update(
        revoked_at=item.revoked_at
    )
    audit(actor, org, "membership.domain_code_revoked", item.pk)


@transaction.atomic
@sensitive_variables()
def request_invitation(code, email):
    """The public view gives the same generic response for unavailable/foreign codes."""
    email = email.strip().casefold()
    validate_email(email)
    context = (
        OrganizationDomainCode.objects.filter(digest=hashlib.sha256(code.encode()).hexdigest())
        .values_list("organization_id", flat=True)
        .first()
    )
    if not context:
        return False
    org = Organization.objects.select_for_update().get(pk=context)
    item = OrganizationDomainCode.objects.select_related("creator").get(
        digest=hashlib.sha256(code.encode()).hexdigest()
    )
    try:
        domain = domain_name(email.rsplit("@", 1)[1])
    except (ValidationError, IndexError):
        return False
    if not active(item, org) or domain != item.domain:
        return False
    # Reuse the established mail challenge, creator checks and org/recipient mail limits.
    invitation = invite(item.creator, org, email, item.role, domain_code=item)
    return not invitation.mail_error
