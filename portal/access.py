from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import AuditEvent, Organization

ANALYST_GROUP = "CIRCL analysts"


def is_analyst(user):
    return user.is_authenticated and user.groups.filter(name=ANALYST_GROUP).exists()


def organizations_for(user):
    if not user.is_authenticated:
        return Organization.objects.none()
    if user.is_superuser:
        return Organization.objects.all()
    q = Q(membership__user=user)
    if is_analyst(user):
        q |= Q(operator_visibility=True)
    return Organization.objects.filter(q).distinct()


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
    findings = org.findings.select_related("record", "installation__product", "installation__asset")
    if not can_operator_review(user, org):
        findings = findings.filter(record__shareable=True)
    return findings


def visible_findings_for(user):
    """Cross-organization queue with the same current raw/derived policy as workspace reads."""
    from .models import Finding

    findings = Finding.objects.filter(organization__in=organizations_for(user)).select_related(
        "organization", "record", "installation__product", "installation__asset"
    )
    if not user.is_superuser:
        policy = Q(record__shareable=True)
        if is_analyst(user):
            policy |= Q(organization__operator_visibility=True)
        findings = findings.filter(policy)
    return findings
