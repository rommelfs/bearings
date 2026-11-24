"""Comparable machine cohorts and bounded software-family cases over visible evidence.

No risk score, product-name affectedness inference, historical interpolation or
cross-company merging. Package/CVE multiplicity never multiplies machine counts.
"""

from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.core import signing
from django.db.models import Case, CharField, Count, Exists, F, Min, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Concat, Lower, Substr
from django.urls import reverse
from django.utils import timezone
from .access import organizations_for
from .models import AgentDevice, Asset, DistroFeed
from .query_integrity import consistent
from . import distro_cves, distro_results, distro_sources
from .review_queue import classified

MACHINE_KINDS = ["server", "desktop", "laptop", "appliance", "vm"]
CASE_FIELDS = ("organization_id", "family", "platform", "manager", "case_kind")
CASE_LABELS = {
    "version": (
        "Check vendor fixes for this software family",
        "Current distribution version evidence; inspect the individual fix boundaries and update channels before applying changes.",
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


def posture(user, org_ids=None, *, shared_only=False, include_totals=True):
    """One mutually exclusive priority per evaluated machine; explicit unknown coverage."""
    from .circl import findings_for

    orgs = organizations_for(user)
    if org_ids is not None:
        orgs = orgs.filter(pk__in=org_ids)
    machines = Asset.objects.filter(organization__in=orgs, lifecycle="active", kind__in=MACHINE_KINDS).filter(
        consistent(source__organization_id=F("organization_id"))
    )
    reviews = classified(findings_for(user)).filter(installation__asset_id=OuterRef("pk"))
    if shared_only:
        reviews = reviews.filter(record__shareable=True)
    automatic = reviews.filter(package_current=True, distro_match__queue_proof__verdict="affected")
    devices = AgentDevice.objects.filter(
        asset_id=OuterRef("pk"),
        source_id=OuterRef("source_id"),
        organization_id=OuterRef("organization_id"),
        enabled=True,
        expires_at__gt=timezone.now(),
        last_observed_at__gte=timezone.now() - timedelta(hours=12),
        last_sequence=F("applied_sequence"),
        distro_requested=False,
        distro_checked_at__gte=F("last_observed_at"),
        distro_summary__state__in=["ready", "partial"],
        distro_summary__evaluator_version=distro_results.VERSION,
    )
    feed_scope = Q(pk__in=[])
    for feed in DistroFeed.objects.filter(enabled=True, key__in=distro_sources.supported_keys()):
        if distro_cves.feed_state(feed) != "ready":
            continue
        distro, release = feed.key.split(":")
        versions = Q(os__version=release)
        if distro != "ubuntu":
            versions |= Q(os__version__startswith=release + ".")
        feed_scope |= (
            Q(os__id=distro, distro_summary__feed=feed.key, distro_summary__generation=str(feed.generation))
            & versions
        )
    devices = devices.filter(feed_scope) if settings.DISTRO_CVE_ENABLED else devices.none()
    from .presentation import SEVERITY_ORDER

    priority = (
        automatic.annotate(
            rank=Case(
                *[When(record__source_severity=key, then=Value(i)) for i, key in enumerate(SEVERITY_ORDER)],
                default=Value(len(SEVERITY_ORDER)),
            )
        )
        .order_by("rank")
        .values("rank")[:1]
    )
    machines = machines.annotate(
        source_priority=Case(When(Exists(devices), then=Subquery(priority)), default=Value(None)),
        evaluated=Exists(devices),
        partial=Exists(devices.filter(distro_summary__package_state="partial")),
        version_match=Exists(automatic),
        critical=Exists(automatic.filter(record__source_severity="critical")),
        high=Exists(automatic.filter(record__source_severity="high")),
        manual=Exists(
            reviews.filter(
                distro_match__isnull=True, status__in=["new", "under_review", "confirmed", "accepted_risk"]
            ).exclude(analyst_applicability="not_affected")
        ),
    )
    if not include_totals:
        return {"machines": machines}
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
        case_kind=Case(
            When(analyst_applicability="affected", then=Value("human")),
            When(package_current=True, distro_match__queue_proof__verdict="affected", then=Value("version")),
            When(queue_bucket="action", then=Value("manual")),
            default=F("queue_bucket"),
            output_field=CharField(),
        ),
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
