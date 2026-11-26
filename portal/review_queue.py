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
from . import distro_oval, distro_results, distro_sources
from .models import DistroMatch
from .distro_projection import ComparableJSON
from .overview_queries import SNAPSHOT_PROOF_IDS


BUCKETS = (
    ("action", "Version matches & cases to assess"),
    ("unresolved", "Vendor clarification needed"),
    ("pending", "Awaiting current evaluation"),
    ("cleared", "Fixed or not affected"),
    ("all", "All retained open reviews"),
)


def current_package_proofs():
    # Same proof/input contract as DistroMatch.inputs_changed, evaluated in SQL so
    # a page never requires hydrating the entire inventory or counting stale proof.
    feed_keys = Q(pk__in=[])
    for distro, versions in (
        ("ubuntu", distro_sources.UBUNTU),
        ("debian", distro_sources.DEBIAN),
        ("rhel", distro_sources.RHEL),
    ):
        for version in versions:
            version_q = Q(component__device__os__version=version)
            if distro != "ubuntu":
                version_q |= Q(component__device__os__version__startswith=version + ".")
            feed_keys |= (
                Q(component__device__os__id=distro, advisory__feed__key=f"{distro}:{version}") & version_q
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
            queue_proof__evaluator_version=distro_results.VERSION,
            queue_proof__schema="bearings.package-check.v2",
            saved_version=F("component__version"),
            queue_proof__package=ComparableJSON("component__package_identity"),
            queue_proof__source_package=ComparableJSON("component__package_source"),
            queue_proof__os=ComparableJSON("component__device__os"),
            saved_sequence=Cast("component__device__applied_sequence", CharField()),
            saved_feed=F("advisory__feed__key"),
            saved_rule=F("advisory__content_hash"),
            component__observed_at__gte=timezone.now() - timedelta(hours=12),
            component__missing_since__isnull=True,
            component__device__enabled=True,
            component__device__distro_requested=False,
            component__device__last_sequence=F("component__device__applied_sequence"),
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


def review_bucket(assessment, has_package, current, verdict):
    """Bucket for already classified package inputs, such as grouped dashboard counts."""
    if assessment == "affected":
        return "action"
    if assessment == "not_affected":
        return "cleared"
    if not has_package:
        return "action"
    if not current:
        return "pending"
    if verdict == "affected":
        return "action"
    if verdict in CLEARED_VERDICTS:
        return "cleared"
    return "unresolved"


def bucket_expression(*, human="action", affected="action", manual="action"):
    """Use the same evidence precedence for both the queue and grouped cases."""
    return Case(
        When(analyst_applicability="affected", then=Value(human)),
        When(analyst_applicability="not_affected", then=Value("cleared")),
        When(distro_match__isnull=True, then=Value(manual)),
        When(package_current=False, then=Value("pending")),
        When(distro_match__queue_proof__verdict="affected", then=Value(affected)),
        When(distro_match__queue_proof__verdict__in=CLEARED_VERDICTS, then=Value("cleared")),
        default=Value("unresolved"),
        output_field=CharField(),
    )
