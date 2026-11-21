from django.core.exceptions import PermissionDenied
from django.db.models import Q, Exists, OuterRef
from .models import AuditEvent, Organization, Membership

ANALYST_GROUP = "CIRCL analysts"


def is_analyst(user):
    return user.is_authenticated and user.groups.filter(name=ANALYST_GROUP).exists()


def organizations_for(user):
    if not user.is_authenticated:
        return Organization.objects.none()
    if user.is_superuser:
        return Organization.objects.filter(merged_into__isnull=True)
    if not is_analyst(user):
        return Organization.objects.filter(membership__user=user, merged_into__isnull=True)
    membership = Membership.objects.filter(user=user, organization_id=OuterRef("pk"))
    policy = Q(Exists(membership))
    policy |= Q(operator_visibility=True)
    return Organization.objects.filter(policy, merged_into__isnull=True)


def role_for(user, org):
    return org.membership_set.filter(user=user).values_list("role", flat=True).first()


def can_edit(user, org):
    return user.is_superuser or role_for(user, org) in {"admin", "editor"}


def can_review_contact(user, org):
    return user.is_superuser or role_for(user, org) == "admin"


def can_operator_review(user, org):
    return user.is_superuser or (is_analyst(user) and org.operator_visibility)


def require(condition):
    if not condition:
        raise PermissionDenied


def audit(user, org, action, target="", **details):
    return AuditEvent.objects.create(
        actor=user, organization=org, action=action, target=str(target), details=details
    )


def audit_operator_access(user, org):
    if user.is_superuser or (is_analyst(user) and not role_for(user, org)):
        audit(user, org, "operator.access")


def visible_findings(user, org):
    findings = org.findings.select_related(
        "organization", "record", "installation__product", "installation__asset"
    )
    if not can_operator_review(user, org):
        findings = findings.filter(record__shareable=True)
    return findings


def visible_findings_for(user):
    """Cross-organization queue with the same current raw/derived policy as workspace reads."""
    from .models import Finding

    analyst = is_analyst(user) if not user.is_superuser else False
    orgs = organizations_for(user)
    findings = Finding.objects.filter(organization__in=orgs).select_related(
        "organization", "record", "installation__product", "installation__asset__source__instance"
    )
    if not user.is_superuser:
        if not analyst:
            ids = list(orgs.values_list("pk", flat=True)[:101])
            if len(ids) <= 100:
                findings = findings.filter(organization_id__in=ids)
        policy = Q(record__shareable=True)
        if analyst:
            policy |= Q(organization__operator_visibility=True)
        findings = findings.filter(policy)
    return findings


def audit_organizations(user, orgs):
    """Audit actually displayed companies with bounded membership checks/inserts."""
    orgs = list({org.pk: org for org in orgs}.values())
    if not user.is_superuser and not is_analyst(user):
        return
    member_ids = set(
        Membership.objects.filter(user=user, organization__in=orgs).values_list("organization_id", flat=True)
    )
    AuditEvent.objects.bulk_create(
        [
            AuditEvent(actor=user, organization=org, action="operator.access")
            for org in orgs
            if user.is_superuser or org.pk not in member_ids
        ],
        batch_size=100,
    )
