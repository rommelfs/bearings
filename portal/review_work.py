"""Separate vulnerability work from retained evidence and comparable progress."""

from datetime import timedelta

from django.db.models import BooleanField, Case, When, Exists, F, OuterRef, Q, Subquery, TextField, Value
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.utils import timezone
from django.db.models.functions import Coalesce

from .discovery import RULE as DISCOVERY_RULE
from .models import DistroMatchRevision, Finding, IssueHistory, IssueRevision
from .presentation import ACTIVE_REVIEWS
from .ubuntu_status import TRIAGE_LABEL
from .query_integrity import consistent
from .review_cases import CVE_ID, case_identity
from .review_queue import (
    MISP_CATALOGUE_GAP,
    NON_ACTION_BUCKETS,
    SAVED_AFFECTED,
    classified,
    current_affected,
    current_discovery_match,
)

# A current affected-version match still needs attention after a workflow closure.
AFFECTED_CVE = Q(record__external_id__iregex=CVE_ID) & (current_affected() | SAVED_AFFECTED)
OPEN_WORK = (
    Q(status__in=[*ACTIVE_REVIEWS, "accepted_risk"])
    | current_affected()
    | Q(discovery__review_required=True)
    | Q(distro_match__review_required=True)
    | Q(distro_match__isnull=False, queue_bucket__in=("pending", "unresolved"))
)
CONFLICTING = current_affected() & Q(analyst_applicability="not_affected")
RECHECK_DISCOVERY = Q(discovery__review_required=True, analyst_applicability="not_affected") & ~Q(
    discovery__result="not_affected"
)
NEEDS_ATTENTION = (
    (OPEN_WORK & ~Q(queue_bucket__in=NON_ACTION_BUCKETS) & ~MISP_CATALOGUE_GAP)
    | CONFLICTING
    | RECHECK_DISCOVERY
)
REVIEW_SCOPES = (
    ("attention", "Needs attention"),
    ("affected", "Affected CVEs only"),
    ("action", "Version matches and reviews"),
    ("unresolved", "Vendor clarification"),
    ("pending", "Awaiting evaluation"),
    ("vendor_no_fix", "No Ubuntu fix published"),
    ("vendor_triage", TRIAGE_LABEL),
    ("cleared", "Fixed or not affected"),
    ("all", "All evidence"),
)


def scoped_work(findings, scope):
    if scope == "all":
        return findings
    findings = classified(findings)
    if scope == "attention":
        return findings.filter(NEEDS_ATTENTION)
    if scope == "affected":
        # Both branches of AFFECTED_CVE already need attention, including
        # current package matches that conflict with a saved decision.
        return findings.filter(AFFECTED_CVE, installation__asset__lifecycle="active").filter(
            consistent(
                installation__asset__organization_id=F("organization_id"),
                installation__asset__source__organization_id=F("organization_id"),
                installation__product__organization_id=F("organization_id"),
                record__organization_id=F("organization_id"),
            )
        )
    if scope in NON_ACTION_BUCKETS:
        return findings.filter(queue_bucket=scope).exclude(CONFLICTING | RECHECK_DISCOVERY)
    if scope == "action":
        return findings.filter(Q(OPEN_WORK, queue_bucket=scope) | CONFLICTING | RECHECK_DISCOVERY)
    return findings.filter(OPEN_WORK, queue_bucket=scope)


def without_unworked_issue_shells(issues, findings=None):
    """Keep catalogue-only and cleared evidence out of operational issue queues."""
    catalogue = Q(
        finding__rule=DISCOVERY_RULE,
        finding__status="new",
        finding__analyst_applicability__in=["unknown", "unassessed"],
    )
    stale_misp = Finding.objects.filter(
        pk=OuterRef("finding_id"),
        discovery__result="potential",
        discovery__watch__vendor__iexact="misp",
        discovery__watch__product_key__iexact="misp",
    ).exclude(current_discovery_match())
    hidden_evidence = catalogue & (
        Q(finding__discovery__result__in=["unknown", "not_affected"]) | Q(Exists(stale_misp))
    )
    if findings is not None:
        non_actionable = classified(findings.filter(pk=OuterRef("finding_id"))).filter(
            queue_bucket__in=NON_ACTION_BUCKETS
        )
        hidden_evidence |= Q(Exists(non_actionable.exclude(CONFLICTING | RECHECK_DISCOVERY)))
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
        Case(When(shell, then=hidden_evidence & ~acted_on), default=Value(False), output_field=BooleanField())
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
