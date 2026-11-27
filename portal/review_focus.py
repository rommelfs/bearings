"""Comparable machine cohorts and bounded software-family cases over visible evidence.

No risk score, product-name affectedness inference, historical interpolation or
cross-company merging. Package/CVE multiplicity never multiplies machine counts.
"""

from urllib.parse import urlencode
from django.conf import settings
from django.core import signing
from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    F,
    IntegerField,
    Min,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Concat, Lower, Substr
from django.urls import reverse
from django.utils import timezone
from .agent_freshness import inventory_applied, recent_device
from .access import organizations_for
from .models import AgentDevice, Asset, DistroFeed
from .query_integrity import consistent
from . import distro_cves, distro_results, distro_sources
from .presentation import SEVERITY_ORDER, severity_rank
from .review_queue import CURRENT_AFFECTED, bucket_expression, classified, current_discovery_match

MACHINE_KINDS = ["server", "desktop", "laptop", "appliance", "vm"]
MAX_SCOPED_MATCHED_MACHINES = 250
CASE_FIELDS = ("organization_id", "family", "platform", "manager", "case_kind")
CASE_LABELS = {
    "version": (
        "Check vendor fixes for this software family",
        "Current vendor version evidence; inspect the advisory and any listed fix before applying changes.",
    ),
    "manual": (
        "Check version applicability",
        "A product/advisory association is not an affected-version decision. Verify the installed version against the original advisory.",
    ),
    "human": (
        "Follow up the saved affected assessment",
        "Review the analyst decision, local exposure and recorded remediation. It is separate from automatic package proof.",
    ),
    "unresolved": (
        "Monitor vendor clarification",
        "Grouped unresolved package decisions; monitor vendor changes and inspect common missing facts. These are not individual repair tasks.",
    ),
    "vendor_triage": (
        "Awaiting Ubuntu evaluation",
        "Canonical is still evaluating this release and source package.",
    ),
    "vendor_no_fix": (
        "Monitor Ubuntu fix availability",
        "Ubuntu has not published a fix for the recorded release and source package. Keep the vendor evidence for monitoring.",
    ),
    "pending": (
        "Restore current evaluation",
        "Inspect inventory freshness, vendor coverage and evaluator diagnostics. Retained evidence is not a current result.",
    ),
    "cleared": (
        "Reconcile retained reviews",
        "The current classification is fixed/not affected or assessed. Preserve human decisions and reconcile the evidence before closing work.",
    ),
}


def ratio(numerator, denominator):
    return {
        "count": numerator,
        "total": denominator,
        "percent": round(100 * numerator / denominator, 1) if denominator else None,
    }


def _machine_assets(user, org_ids):
    orgs = organizations_for(user)
    if org_ids is not None:
        orgs = orgs.filter(pk__in=org_ids)
    return Asset.objects.filter(organization__in=orgs, lifecycle="active", kind__in=MACHINE_KINDS).filter(
        consistent(source__organization_id=F("organization_id"))
    )


def machine_coverage(user, org_ids):
    """Current device coverage independently of package findings."""
    machines = _machine_assets(user, org_ids)
    feed_scope = _ready_feed_scope()
    if feed_scope:
        devices = _evaluated_devices(feed_scope)
        machines = machines.annotate(
            evaluated=Exists(devices),
            partial=Exists(devices.filter(distro_summary__package_state="partial")),
        )
    else:
        machines = machines.annotate(evaluated=Value(False), partial=Value(False))
    return machines, bool(feed_scope)


def posture(user, org_ids=None, *, shared_only=False, include_totals=True, scoped_evidence=False):
    """One mutually exclusive priority per evaluated machine; explicit unknown coverage."""
    from .circl import findings_for

    machines = _machine_assets(user, org_ids)
    scope = findings_for(user)
    if shared_only:
        scope = scope.filter(record__shareable=True)
    reviews = scope.filter(installation__asset_id=OuterRef("pk"))
    manual = Exists(
        classified(
            reviews.filter(
                distro_match__isnull=True, status__in=["new", "under_review", "confirmed", "accepted_risk"]
            ),
            package_evidence=False,
        ).exclude(Q(queue_bucket="cleared") | current_discovery_match())
    )
    feed_scope = _ready_feed_scope()
    if feed_scope:
        matches = (
            _scoped_automatic_status(scope.filter(installation__asset_id__in=machines.values("pk")), org_ids)
            if scoped_evidence and org_ids is not None
            else None
        )
        machines = machines.annotate(manual=manual, **_evaluated_machine_status(reviews, feed_scope, matches))
    else:
        machines = machines.annotate(
            manual=manual,
            source_priority=Value(None, output_field=IntegerField()),
            evaluated=Value(False),
            partial=Value(False),
            version_match=Value(False),
            critical=Value(False),
            high=Value(False),
        )
    if not include_totals:
        return {"machines": machines, "evaluation_available": bool(feed_scope)}
    result = {}
    for row in (
        machines.order_by()
        .values("organization_id")
        .annotate(
            total=Count("pk"),
            evaluated_count=Count("pk", filter=Q(evaluated=True)),
            partial_count=Count("pk", filter=Q(evaluated=True, partial=True)),
            matched=Count("pk", filter=Q(evaluated=True, version_match=True)),
            critical_count=Count("pk", filter=Q(evaluated=True, critical=True)),
            high_count=Count("pk", filter=Q(evaluated=True, critical=False, high=True)),
            other_count=Count("pk", filter=Q(evaluated=True, critical=False, high=False, version_match=True)),
            manual_count=Count("pk", filter=Q(manual=True)),
        )
    ):
        result[row.pop("organization_id")] = row

    def present(counts):
        return {
            **counts,
            "coverage": ratio(counts["evaluated_count"], counts["total"]),
            "affected": ratio(counts["matched"], counts["evaluated_count"]),
            "missing": counts["total"] - counts["evaluated_count"],
            "critical_rate": ratio(counts["critical_count"], counts["evaluated_count"]),
            "high_rate": ratio(counts["high_count"], counts["evaluated_count"]),
            "other_rate": ratio(counts["other_count"], counts["evaluated_count"]),
        }

    keys = (
        "total",
        "evaluated_count",
        "partial_count",
        "matched",
        "critical_count",
        "high_count",
        "other_count",
        "manual_count",
    )
    total = {key: sum(row[key] for row in result.values()) for key in keys}
    return {
        "national": present(total),
        "organizations": {pk: present(row) for pk, row in result.items()},
        "machines": machines,
    }


def _ready_feed_scope():
    scope = Q()
    if not settings.DISTRO_CVE_ENABLED:
        return scope
    for feed in DistroFeed.objects.filter(enabled=True, key__in=distro_sources.supported_keys()):
        if distro_cves.feed_state(feed) != "ready":
            continue
        scope |= Q(
            distro_summary__feed=feed.key, distro_summary__generation=str(feed.generation)
        ) & distro_sources.host_release_filter(feed.key, os_path="os")
    return scope


def _automatic_matches(reviews):
    return classified(reviews).filter(CURRENT_AFFECTED)


def _scoped_automatic_status(reviews, organizations):
    """Validate each proof once and retain only a bounded list of machine IDs by severity."""
    rows = list(
        _automatic_matches(classified(reviews, organizations=organizations))
        .order_by()
        .values("installation__asset_id")
        .annotate(
            rank=Min(severity_rank("record__source_severity")),
            high_count=Count("pk", filter=Q(record__source_severity="high")),
        )[: MAX_SCOPED_MATCHED_MACHINES + 1]
    )
    if len(rows) > MAX_SCOPED_MATCHED_MACHINES:
        return None
    ids_by_rank = {}
    for row in rows:
        ids_by_rank.setdefault(row["rank"], []).append(row["installation__asset_id"])
    return {
        "priority": Case(
            *(When(pk__in=ids, then=Value(rank)) for rank, ids in ids_by_rank.items()),
            default=Cast(Value(None), IntegerField()),
            output_field=IntegerField(),
        ),
        "version_match": Q(pk__in=[row["installation__asset_id"] for row in rows]),
        "critical": Q(pk__in=ids_by_rank.get(SEVERITY_ORDER.index("critical"), [])),
        "high": Q(pk__in=[row["installation__asset_id"] for row in rows if row["high_count"]]),
    }


def _evaluated_devices(feed_scope):
    return AgentDevice.objects.filter(
        feed_scope,
        recent_device(),
        inventory_applied(),
        asset_id=OuterRef("pk"),
        source_id=OuterRef("source_id"),
        organization_id=OuterRef("organization_id"),
        enabled=True,
        expires_at__gt=timezone.now(),
        distro_requested=False,
        distro_checked_at__gte=F("last_observed_at"),
        distro_summary__state__in=["ready", "partial"],
        distro_summary__evaluator_version=distro_results.VERSION,
    )


def _evaluated_machine_status(reviews, feed_scope, matches):
    devices = _evaluated_devices(feed_scope)
    if matches is None:
        automatic = _automatic_matches(reviews)
        matches = {
            "priority": Subquery(
                automatic.annotate(rank=severity_rank("record__source_severity"))
                .order_by("rank")
                .values("rank")[:1]
            ),
            "version_match": Exists(automatic),
            "critical": Exists(automatic.filter(record__source_severity="critical")),
            "high": Exists(automatic.filter(record__source_severity="high")),
        }
    return {
        "source_priority": Case(
            When(Exists(devices), then=matches["priority"]), default=Cast(Value(None), IntegerField())
        ),
        "evaluated": Exists(devices),
        "partial": Exists(devices.filter(distro_summary__package_state="partial")),
        "version_match": matches["version_match"],
        "critical": matches["critical"],
        "high": matches["high"],
    }


def case_scope(reviews):
    """Identity uses explicit source-package metadata, otherwise exact product identity."""
    return classified(reviews).annotate(
        family=Case(
            When(
                Q(distro_match__component__package_source__name__isnull=False)
                & ~Q(distro_match__component__package_source__name=""),
                then=Concat(
                    Value("source:"),
                    KeyTextTransform("name", "distro_match__component__package_source"),
                    output_field=CharField(),
                ),
            ),
            When(
                ~Q(installation__product__identifier=""),
                then=Concat(Value("product:"), Lower("installation__product__identifier")),
            ),
            default=Concat(Value("local-product:"), Cast("installation__product_id", CharField())),
            output_field=CharField(),
        ),
        platform=Case(
            When(distro_match__isnull=True, then=Value("application")),
            default=Concat(
                KeyTextTransform("id", "distro_match__component__device__os"),
                Value(":"),
                KeyTextTransform("version", "distro_match__component__device__os"),
                output_field=CharField(),
            ),
            output_field=CharField(),
        ),
        manager=Coalesce("distro_match__component__manager", Value("application")),
        case_kind=bucket_expression(human="human", affected="version", manual="manual"),
    )


def cases(reviews, number, *, filters=None, base_url=None, ordering=None):
    from django.core.paginator import Paginator
    from .presentation import SEVERITY_ORDER

    grouped = (
        case_scope(reviews)
        .order_by()
        .values(*CASE_FIELDS)
        .annotate(
            name=Min("installation__product__name"),
            company=Min("organization__name"),
            slug=Min("organization__slug"),
            machines=Count("installation__asset_id", distinct=True),
            identifiers=Count("record__external_id", distinct=True),
            records=Count("pk"),
            priority=Min(
                Case(
                    *[
                        When(record__source_severity=key, then=Value(value))
                        for value, key in enumerate(SEVERITY_ORDER)
                    ],
                    default=Value(99),
                )
            ),
        )
        .annotate(
            family_sort=Case(
                When(family__startswith="source:", then=Substr("family", 8)),
                default=F("name"),
                output_field=CharField(),
            )
        )
        .order_by(*([ordering] if ordering is not None else ["priority"]), *CASE_FIELDS)
    )
    page = Paginator(grouped, 25).get_page(number)
    for row in page:
        row["priority_label"] = (
            SEVERITY_ORDER[row["priority"]].title() if row["priority"] < len(SEVERITY_ORDER) else "Unknown"
        )
        row["heading"], row["guidance"] = CASE_LABELS[row["case_kind"]]
        row["family_name"] = (
            row["family"].removeprefix("source:") if row["family"].startswith("source:") else row["name"]
        )
        row["url"] = (
            (base_url or reverse("circl-findings"))
            + "?"
            + urlencode(
                {
                    **(filters or {}),
                    "view": "records",
                    "case": signing.dumps(
                        {k: row[k] for k in CASE_FIELDS}, salt="review-family-v1", compress=True
                    ),
                }
            )
        )
    return page


def select_case(reviews, token):
    data = signing.loads(token, salt="review-family-v1")
    if not isinstance(data, dict) or set(data) != set(CASE_FIELDS):
        raise signing.BadSignature("Invalid case identity")
    return case_scope(reviews).filter(**data)
