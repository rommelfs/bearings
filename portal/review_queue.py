"""Classify scoped review rows before counting/paging; never mutate human workflow."""

from datetime import timedelta
from django.db.models import Case, CharField, Exists, F, OuterRef, Q, Value, When
from django.utils import timezone
from django.db.models.fields.json import KT
from django.db.models.functions import Cast
from . import distro_oval, distro_results, distro_sources
from .models import DistroMatch
from .distro_projection import ComparableJSON


BUCKETS = (
    ("action", "Affected versions & manual reviews"),
    ("unresolved", "Vendor clarification needed"),
    ("pending", "Awaiting current evaluation"),
    ("cleared", "Fixed / not affected / assessed"),
    ("all", "All retained open reviews"),
)


def classified(reviews):
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
    current = (
        DistroMatch.objects.annotate(
            saved_version=KT("queue_proof__version"),
            saved_feed=KT("queue_proof__feed"),
            saved_rule=KT("queue_proof__rule_sha256"),
            saved_sequence=Cast(KT("queue_proof__inventory_sequence"), CharField()),
            saved_ubuntu_hash=KT("queue_proof__ubuntu_hash"),
            saved_ubuntu_cve=KT("queue_proof__ubuntu_cve"),
        )
        .filter(
            finding_id=OuterRef("pk"),
            component__device__organization_id=F("finding__organization_id"),
            component__device__asset_id=F("finding__installation__asset_id"),
            component__device__source_id=F("finding__installation__asset__source_id"),
            component__installation_id=F("finding__installation_id"),
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
    return reviews.annotate(package_current=Exists(current)).annotate(
        queue_bucket=Case(
            When(analyst_applicability="affected", then=Value("action")),
            When(analyst_applicability="not_affected", then=Value("cleared")),
            When(distro_match__isnull=True, then=Value("action")),
            When(package_current=False, then=Value("pending")),
            When(distro_match__queue_proof__verdict="affected", then=Value("action")),
            When(
                distro_match__queue_proof__verdict__in=["fixed", "not_matched"],
                then=Value("cleared"),
            ),
            default=Value("unresolved"),
            output_field=CharField(),
        )
    )
