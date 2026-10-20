"""Scoped asset issue facts and immutable review evidence; no lifecycle-to-CVE inference."""

import hashlib
import json
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from .access import audit, can_edit, can_operator_review, is_analyst, organizations_for, require
from .models import AssetIssue, IssueHistory, IssueRevision, IssueRiskLink

ACTIVE = ["new", "under_review", "confirmed"]
FACT_FIELDS = [
    "title",
    "kind",
    "status",
    "priority",
    "owner_team",
    "event_date",
    "action_due",
    "fact_scope",
    "contract_reference",
    "source_label",
    "source_url",
    "observed_at",
    "valid_from",
    "valid_until",
    "fact_status",
    "evidence_text",
    "consequence",
    "next_action",
    "operator_only",
    "shareable",
]


def visible_issues(user):
    issues = (
        AssetIssue.objects.filter(
            organization__in=organizations_for(user),
            asset__organization_id=F("organization_id"),
            asset__source__organization_id=F("organization_id"),
        )
        .filter(
            Q(installation__isnull=True)
            | Q(
                installation__asset_id=F("asset_id"),
                installation__product__organization_id=F("organization_id"),
            )
        )
        .filter(
            Q(finding__isnull=True)
            | Q(
                finding__organization_id=F("organization_id"),
                finding__record__organization_id=F("organization_id"),
                finding__installation_id=F("installation_id"),
            )
        )
        .select_related("organization", "asset__source__instance", "installation__product", "finding__record")
    )
    if not user.is_superuser:
        allowed = Q(operator_only=False) & (Q(finding__isnull=True) | Q(finding__record__shareable=True))
        if is_analyst(user):
            allowed |= Q(organization__operator_visibility=True)
        issues = issues.filter(allowed)
    from .plum import visible_snapshots

    return issues.exclude(
        Q(exposure_review__isnull=False) & ~Q(exposure_review__observation__in=visible_snapshots(user))
    )


def editable(user, issue):
    return can_edit(user, issue.organization) or can_operator_review(user, issue.organization)


def active_filter():
    return Q(finding__isnull=True, status__in=ACTIVE) | Q(finding__status__in=ACTIVE)


def data_for(issue):
    result = {name: getattr(issue, name) for name in FACT_FIELDS}
    result.update(
        asset_id=str(issue.asset_id), installation_id=issue.installation_id, finding_id=issue.finding_id
    )
    return json.loads(json.dumps(result, default=str))


def snapshot(issue, actor=None):
    data = data_for(issue)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return IssueRevision.objects.get_or_create(
        issue=issue, digest=digest, defaults={"snapshot": data, "actor": actor}
    )[0]


@transaction.atomic
def ensure_vulnerability_issue(finding):
    # The original Finding, its source visibility, history and FlowIntel mapping remain authoritative.
    finding.full_clean()
    issue, created = AssetIssue.objects.get_or_create(
        finding=finding,
        defaults={
            "organization": finding.organization,
            "asset": finding.installation.asset,
            "installation": finding.installation,
            "kind": "vulnerability",
            "title": finding.record.external_id,
            "source_label": finding.record.source,
            "evidence_text": "Linked vulnerability evidence. Open the original review for the current assessment.",
            "observed_at": finding.observed_at or finding.evaluated_at,
            "owner_team": finding.installation.asset.responsible_team,
        },
    )
    if created:
        issue.full_clean()
        snapshot(issue)
    return issue


@transaction.atomic
def save_issue(actor, issue, values, reason):
    org = issue.organization
    require(actor.is_active and (can_edit(actor, org) or can_operator_review(actor, org)))
    require(bool(reason.strip()) and len(reason) <= 4000)
    creating = issue._state.adding
    before = {}
    if not creating:
        issue = AssetIssue.objects.select_for_update().get(pk=issue.pk)
        require(visible_issues(actor).filter(pk=issue.pk).exists())
        before = data_for(issue)
    for name, value in values.items():
        if name not in FACT_FIELDS and not (creating and name in {"asset", "installation"}):
            raise ValidationError("Unsupported issue field")
        if name in {"operator_only"}:
            require(can_operator_review(actor, org))
        if issue.finding_id and name in {
            "kind",
            "status",
            "source_label",
            "source_url",
            "observed_at",
            "evidence_text",
            "fact_status",
            "valid_from",
            "valid_until",
            "event_date",
            "fact_scope",
            "contract_reference",
        }:
            raise ValidationError("Use the original CVE review for vulnerability evidence and workflow")
        setattr(issue, name, value)
    if creating:
        require(issue.kind != "vulnerability" and not issue.finding_id)
        issue.created_by = actor
    issue.full_clean()
    issue.save()
    revision = snapshot(issue, actor)
    after = data_for(issue)
    changes = {
        name: {"before": before.get(name), "after": value}
        for name, value in after.items()
        if before.get(name) != value
    }
    IssueHistory.objects.create(
        issue=issue, revision=revision, actor=actor, reason=reason.strip(), changes=changes
    )
    audit(actor, org, "issue.created" if creating else "issue.updated", issue.pk, revision=revision.pk)
    return issue


@transaction.atomic
def link_risk(actor, issue, risk, reason):
    issue = AssetIssue.objects.select_for_update().get(pk=issue.pk)
    require(visible_issues(actor).filter(pk=issue.pk).exists() and editable(actor, issue))
    require(bool(reason.strip()) and len(reason) <= 4000)
    if issue.finding_id:
        raise ValidationError("Link vulnerability risk scenarios in the original CVE review")
    if not risk.source.enabled or risk.missing_since or not risk.current_revision_id:
        raise ValidationError("Choose an available catalog scenario with a pinned revision")
    revision = snapshot(issue, actor)
    link, created = IssueRiskLink.objects.get_or_create(
        issue=issue,
        issue_revision=revision,
        risk_revision=risk.current_revision,
        withdrawn_at=None,
        defaults={"reason": reason.strip(), "created_by": actor},
    )
    audit(actor, issue.organization, "issue.risk_linked", issue.pk, link=link.pk, created=created)
    return link


@transaction.atomic
def withdraw_risk(actor, link, reason):
    link = IssueRiskLink.objects.select_for_update().select_related("issue__organization").get(pk=link.pk)
    require(visible_issues(actor).filter(pk=link.issue_id).exists() and editable(actor, link.issue))
    require(bool(reason.strip()) and len(reason) <= 4000)
    if link.withdrawn_at is None:
        link.withdrawn_at, link.withdrawal_reason = timezone.now(), reason.strip()
        link.save(update_fields=["withdrawn_at", "withdrawal_reason"])
        audit(actor, link.issue.organization, "issue.risk_withdrawn", link.issue_id, link=link.pk)


def issue_json(issue):
    return {
        "id": str(issue.pk),
        "organization": str(issue.organization_id),
        "asset_id": str(issue.asset_id),
        "installation_id": issue.installation_id,
        "finding_id": issue.finding_id,
        "kind": issue.kind,
        "title": issue.title,
        "status": issue.current_status,
        "priority": issue.priority,
        "owner_team": issue.owner_team,
        "event_date": issue.event_date,
        "action_due": issue.action_due,
        "timing": issue.timing,
        "fact_status": issue.fact_status,
        "source_label": issue.source_label,
        "observed_at": issue.observed_at,
        "updated_at": issue.updated_at,
    }
