"""Classify scoped review rows before counting/paging; never mutate human workflow."""

from datetime import timedelta
from django.contrib.postgres.fields import ArrayField
from django.db import connection
from django.db.models import (
    BigIntegerField,
    BooleanField,
    Case,
    CharField,
    Exists,
    ExpressionWrapper,
    F,
    Func,
    OuterRef,
    Q,
    Value,
    When,
)
from django.utils import timezone
from django.db.models.fields.json import KT
from django.db.models.functions import Cast
from .agent_freshness import inventory_applied, recent_component
from . import distro_oval, distro_results, distro_sources
from .discovery import RULE as DISCOVERY_RULE
from .models import DiscoveryRevision, DistroMatch
from .misp_cves import COMPATIBLE_PROOFS, MATCHED_RANGE
from .distro_projection import ComparableJSON
from .overview_queries import SNAPSHOT_PROOF_IDS
from .presentation import ACTIVE_REVIEWS
from .ubuntu_status import NO_FIX_REASON_LABELS, TRIAGE_LABEL, TRIAGE_REASON


BUCKETS = (
    ("action", "Version matches & cases to assess"),
    ("unresolved", "Vendor clarification needed"),
    ("pending", "Awaiting current evaluation"),
    ("vendor_no_fix", "No Ubuntu fix published"),
    ("vendor_triage", TRIAGE_LABEL),
    ("cleared", "Fixed or not affected"),
    ("all", "All retained open reviews"),
)


def current_package_proofs():
    # Same proof/input contract as DistroMatch.inputs_changed, evaluated in SQL so
    # a page never requires hydrating the entire inventory or counting stale proof.
    feed_keys = Q(pk__in=[])
    for key in distro_sources.supported_keys():
        feed_keys |= Q(advisory__feed__key=key) & distro_sources.host_release_filter(
            key, os_path="component__device__os"
        )
    return (
        DistroMatch.objects.annotate(
            saved_version=KT("queue_proof__version"),
            saved_feed=KT("queue_proof__feed"),
            saved_rule=KT("queue_proof__rule_sha256"),
            saved_sequence=Cast(KT("queue_proof__inventory_sequence"), CharField()),
            saved_ubuntu_hash=KT("queue_proof__ubuntu_hash"),
            saved_ubuntu_cve=KT("queue_proof__ubuntu_cve"),
        )
        .filter(
            recent_component("component__"),
            inventory_applied("component__device__"),
            queue_proof__evaluator_version=distro_results.VERSION,
            queue_proof__schema="bearings.package-check.v2",
            saved_version=F("component__version"),
            queue_proof__package=ComparableJSON("component__package_identity"),
            queue_proof__source_package=ComparableJSON("component__package_source"),
            queue_proof__os=ComparableJSON("component__device__os"),
            saved_sequence=Cast("component__device__applied_sequence", CharField()),
            saved_feed=F("advisory__feed__key"),
            saved_rule=F("advisory__content_hash"),
            component__missing_since__isnull=True,
            component__device__enabled=True,
            component__device__distro_requested=False,
            component__device__expires_at__gt=timezone.now(),
            advisory__feed__enabled=True,
            advisory__feed__generation__isnull=False,
            advisory__feed__summary__compiler_version=distro_oval.COMPILER_VERSION,
            advisory__feed__last_success__gte=timezone.now() - timedelta(hours=12),
        )
        .filter(feed_keys)
        .exclude(component__device__distro_summary__state__in=["error", "pending", "stale", "unsupported"])
        .filter(
            Q(queue_proof__ubuntu_missing=True)
            | Q(
                ubuntu_status_id=F("saved_ubuntu_cve"),
                ubuntu_status__content_hash=F("saved_ubuntu_hash"),
                ubuntu_status__last_success__gte=timezone.now() - timedelta(hours=12),
            )
        )
    )


def scoped_package_proofs(*, organizations=None, assets=None):
    """Current verdicts for a bounded inventory scope, joined to their exact finding."""
    proofs = current_package_proofs().filter(
        component__device__organization_id=F("finding__organization_id"),
        component__device__asset_id=F("finding__installation__asset_id"),
        component__device__source_id=F("finding__installation__asset__source_id"),
        component__installation_id=F("finding__installation_id"),
    )
    if organizations is not None:
        proofs = proofs.filter(finding__organization_id__in=organizations)
    if assets is not None:
        proofs = proofs.filter(component__device__asset_id__in=assets)
    return proofs


MAX_LOADED_PROOFS = 20000


class CurrentProofMembership(Func):
    """Use one PostgreSQL array parameter, with no SQL text per finding."""

    arity = 2
    arg_joiner = " = ANY("
    template = "(%(expressions)s))"
    output_field = BooleanField()


def _scoped_current_expression(proofs, organizations, assets):
    # A repeatable-read snapshot keeps loaded proof IDs and the later readers
    # coherent while another transaction publishes a newly evaluated report.
    cache = SNAPSHOT_PROOF_IDS.get()
    if connection.vendor == "postgresql" and cache is not None:
        concrete = all(scope is None or isinstance(scope, (list, tuple)) for scope in (organizations, assets))
        key = (
            (
                tuple(organizations) if organizations is not None else None,
                tuple(assets) if assets is not None else None,
            )
            if concrete
            else None
        )
        if key is not None and key in cache:
            ids = cache[key]
        else:
            ids = list(proofs.order_by().values_list("finding_id", flat=True)[: MAX_LOADED_PROOFS + 1])
            if key is not None:
                cache[key] = ids
        if not ids:
            return Value(False, output_field=BooleanField())
        if len(ids) <= MAX_LOADED_PROOFS:
            return CurrentProofMembership(F("pk"), Value(ids, output_field=ArrayField(BigIntegerField())))
    return ExpressionWrapper(Q(pk__in=proofs.order_by().values("finding_id")), output_field=BooleanField())


def classified(reviews, *, organizations=None, assets=None, package_evidence=True):
    if "package_current" in reviews.query.annotations:
        return reviews
    if not package_evidence:
        return reviews.annotate(package_current=Value(False)).annotate(queue_bucket=bucket_expression())
    if organizations is not None or assets is not None:
        current = scoped_package_proofs(organizations=organizations, assets=assets)
        predicate = _scoped_current_expression(current, organizations, assets)
        return reviews.annotate(package_current=predicate).annotate(queue_bucket=bucket_expression())
    # Correlate the exact match and visible inventory/source, reusing the
    # same proof contract as the host overview's set-based query.
    current = current_package_proofs().filter(
        pk=OuterRef("distro_match__pk"),
        component__device__organization_id=OuterRef("organization_id"),
        component__device__asset_id=OuterRef("installation__asset_id"),
        component__device__source_id=OuterRef("installation__asset__source_id"),
        component__installation_id=OuterRef("installation_id"),
    )
    return reviews.annotate(package_current=Exists(current)).annotate(queue_bucket=bucket_expression())


CLEARED_VERDICTS = ("fixed", "not_matched")
UBUNTU_UNRESOLVED_EVIDENCE = Q(
    distro_match__queue_proof__verdict="unresolved",
    distro_match__queue_proof__feed__startswith="ubuntu:",
    distro_match__queue_proof__ubuntu_missing=False,
)
NO_FIX_EVIDENCE = UBUNTU_UNRESOLVED_EVIDENCE & Q(
    distro_match__queue_proof__uncertainty_reason__in=tuple(NO_FIX_REASON_LABELS)
)
VENDOR_TRIAGE_EVIDENCE = UBUNTU_UNRESOLVED_EVIDENCE & Q(
    distro_match__queue_proof__uncertainty_reason=TRIAGE_REASON
)
VENDOR_MONITORING_BUCKETS = ("vendor_no_fix", "vendor_triage")
NON_ACTION_BUCKETS = ("cleared", *VENDOR_MONITORING_BUCKETS)
MISP_CATALOGUE_GAP = Q(
    rule=DISCOVERY_RULE,
    status="new",
    analyst_applicability__in=("unknown", "unassessed"),
    distro_match__isnull=True,
    discovery__result="unknown",
    discovery__watch__vendor__iexact="misp",
    discovery__watch__product_key__iexact="misp",
)
CURRENT_AFFECTED = Q(package_current=True, distro_match__queue_proof__verdict="affected")
SAVED_AFFECTED = Q(status__in=[*ACTIVE_REVIEWS, "accepted_risk"], analyst_applicability="affected")


def current_misp_proof(result):
    """A version verdict belongs to the exact evaluated installation and advisory."""
    return (
        DiscoveryRevision.objects.filter(
            match__finding_id=OuterRef("pk"),
            match__result=result,
            match__watch__vendor__iexact="misp",
            match__watch__product_key__iexact="misp",
            match__watch__product_id=OuterRef("installation__product_id"),
            match__evidence_revision__record_id=OuterRef("record_id"),
            fingerprint=F("match__input_hash"),
            snapshot__evaluation_rule__in=COMPATIBLE_PROOFS,
            snapshot__result=result,
        )
        .alias(
            version_text=KT("snapshot__version"),
            edition_text=KT("snapshot__edition"),
            build_text=KT("snapshot__build"),
            product_text=KT("snapshot__product_identifier"),
            evaluated_payload=ComparableJSON("match__evidence_revision__payload"),
        )
        .filter(
            version_text=OuterRef("installation__version"),
            edition_text=OuterRef("installation__edition"),
            build_text=OuterRef("installation__build"),
            product_text=OuterRef("installation__product__identifier"),
            evaluated_payload=ComparableJSON(OuterRef("record__payload")),
        )
    )


def current_discovery_match():
    # Older snapshots also tagged generic discovery fallbacks with the MISP
    # rule. Only the specialist evaluator's own range decision is positive proof.
    proof = current_misp_proof("potential").filter(snapshot__explanation__endswith=MATCHED_RANGE)
    return Q(distro_match__isnull=True) & Q(Exists(proof))


def current_affected():
    return CURRENT_AFFECTED | current_discovery_match()


def discovery_version_status():
    return Case(
        When(current_discovery_match(), then=Value("affected")),
        When(current_discovery_exclusion(), then=Value("not_affected")),
        default=Value(""),
        output_field=CharField(),
    )


def current_discovery_exclusion():
    return Q(Exists(current_misp_proof("not_affected")))


def current_version_exclusion():
    """A current version exclusion prevents automatic remediation/outreach."""
    return (
        Q(package_current=True, distro_match__queue_proof__verdict__in=CLEARED_VERDICTS)
        | Q(distro_match__isnull=True) & current_discovery_exclusion()
    )


def outreach_exclusion():
    return current_version_exclusion() | MISP_CATALOGUE_GAP | Q(queue_bucket__in=VENDOR_MONITORING_BUCKETS)


def bucket_expression(*, human="action", affected="action", manual="action"):
    """Use the same evidence precedence for both the queue and grouped cases."""
    discovery_match = [When(current_discovery_match(), then=Value(affected))] if affected != manual else []
    return Case(
        When(analyst_applicability="affected", then=Value(human)),
        When(analyst_applicability="not_affected", then=Value("cleared")),
        When(Q(distro_match__isnull=True) & current_discovery_exclusion(), then=Value("cleared")),
        *discovery_match,
        When(MISP_CATALOGUE_GAP, then=Value("unresolved")),
        When(distro_match__isnull=True, then=Value(manual)),
        When(package_current=False, then=Value("pending")),
        When(distro_match__queue_proof__verdict="affected", then=Value(affected)),
        When(distro_match__queue_proof__verdict__in=CLEARED_VERDICTS, then=Value("cleared")),
        When(NO_FIX_EVIDENCE, then=Value("vendor_no_fix")),
        When(VENDOR_TRIAGE_EVIDENCE, then=Value("vendor_triage")),
        default=Value("unresolved"),
        output_field=CharField(),
    )
