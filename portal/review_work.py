"""Separate vulnerability work from retained evidence and comparable progress."""

from datetime import timedelta

from django.db.models import BooleanField, Case, When, Exists, F, OuterRef, Q, Subquery, TextField, Value
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.utils import timezone
from django.db.models.functions import Coalesce

from .models import DistroMatchRevision, IssueHistory, IssueRevision
from .presentation import ACTIVE_REVIEWS
from .review_cases import case_identity
from .review_queue import classified

# A current affected-version match still needs attention after a workflow closure.
CURRENT_AFFECTED = Q(package_current=True, distro_match__queue_proof__verdict="affected")
OPEN_WORK = (
    Q(status__in=[*ACTIVE_REVIEWS, "accepted_risk"])
    | CURRENT_AFFECTED
    | Q(discovery__review_required=True)
    | Q(distro_match__review_required=True)
    | Q(distro_match__isnull=False, queue_bucket__in=("pending", "unresolved"))
)
CONFLICTING = CURRENT_AFFECTED & Q(analyst_applicability="not_affected")
NEEDS_ATTENTION = (OPEN_WORK & ~Q(queue_bucket="cleared")) | CONFLICTING
REVIEW_SCOPES = (
    ("attention", "Needs attention"),
    ("action", "Version matches and reviews"),
    ("unresolved", "Vendor clarification"),
    ("pending", "Awaiting evaluation"),
    ("cleared", "Fixed or not affected"),
    ("all", "All evidence"),
)


def scoped_work(findings, scope):
    if scope == "all":
        return findings
    findings = classified(findings)
    if scope == "attention":
        return findings.filter(NEEDS_ATTENTION)
    if scope == "cleared":
        return findings.filter(queue_bucket=scope).exclude(CONFLICTING)
    if scope == "action":
        return findings.filter(Q(OPEN_WORK, queue_bucket=scope) | CONFLICTING)
    return findings.filter(OPEN_WORK, queue_bucket=scope)


def without_cleared_issue_shells(issues, findings):
    """Suppress automatic issue shells while retaining explicit operational work."""
    cleared = scoped_work(findings.filter(pk=OuterRef("finding_id")), "cleared")
    shell = Q(
        kind="vulnerability",
        status="new",
        priority="review",
        action_due__isnull=True,
        event_date__isnull=True,
        next_action="",
        consequence="",
    )
    acted_on = Exists(IssueHistory.objects.filter(issue_id=OuterRef("pk"))) | Exists(
        IssueRevision.objects.filter(issue_id=OuterRef("pk"), actor__isnull=False)
    )
    return issues.exclude(
        Case(When(shell, then=Exists(cleared) & ~acted_on), default=Value(False), output_field=BooleanField())
    )


def positive_package_coverage(summary, evaluated):
    packages = summary.get("packages")
    return (
        evaluated
        and summary.get("state") == "ready"
        and summary.get("package_state") == "ready"
        and type(packages) is int
        and packages > 0
    )


def verified_fix_progress(findings):
    """Count distinct CVE/installations with a recent comparable affected → fixed pair."""
    history = DistroMatchRevision.objects.filter(match_id=OuterRef("distro_match__pk")).order_by(
        "-created_at", "-pk"
    )
    identity = {
        "product": "package__product",
        "os_id": "os__id",
        "os_version": "os__version",
        "architecture": "os__architecture",
        "source_package": "source_package__name",
        "feed": "feed",
        "rule": "rule_sha256",
    }

    # The versioned purl and running kernel can change as part of remediation.
    # The package product key identifies the product and package architecture.
    def text_value(field, path):
        *parents, key = path.split("__")
        expression = F(field)
        for parent in parents:
            expression = KeyTransform(parent, expression)
        return KeyTextTransform(key, expression)

    def text_identity(field, path):
        return Coalesce(text_value(field, path), Value(""), output_field=TextField())

    previous = history.annotate(
        version_text=text_value("snapshot", "version"),
        verdict_text=text_value("snapshot", "package_check__verdict"),
        **{f"proof_{name}": text_identity("snapshot", path) for name, path in identity.items()},
    )[1:2]
    current = classified(findings).filter(package_current=True, distro_match__queue_proof__verdict="fixed")
    changes = (
        current.order_by()
        .alias(
            latest_hash=Subquery(history.values("fingerprint")[:1]),
            latest_at=Subquery(history.values("created_at")[:1]),
            previous_verdict=Subquery(previous.values("verdict_text")),
            previous_version=Subquery(previous.values("version_text")),
            **{f"previous_{name}": Subquery(previous.values(f"proof_{name}")) for name in identity},
        )
        .filter(
            latest_hash=F("distro_match__input_hash"),
            latest_at__gte=timezone.now() - timedelta(days=30),
            previous_verdict="affected",
            **{
                f"previous_{name}": text_identity("distro_match__queue_proof", path)
                for name, path in identity.items()
            },
        )
        .filter(previous_version__isnull=False)
        .exclude(previous_product="")
        .exclude(previous_version=text_value("distro_match__queue_proof", "version"))
    )
    rows = case_identity(changes).values("installation_id", "case_identifier").distinct()
    return rows.count()
