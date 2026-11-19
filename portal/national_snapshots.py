"""Incremental per-company national read models; current scope and dirty-state checks on every read."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Case, Count, F, IntegerField, Min, Q, Sum, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Lower, TruncDate
from django.utils import timezone
from .access import organizations_for
from .models import (
    Asset,
    DiscoveryMatch,
    FindingHistory,
    NationalState,
    NationalVersion,
    NationalProblem,
    NationalActivity,
    NationalProductVersion,
)
from .overview_queries import overview_queries, READ_SNAPSHOT
from .query_integrity import consistent


class PendingSnapshot(Exception):
    pass


class InternalReader:
    """Not a login identity: permits aggregation only, never a rendered/audited user."""

    is_authenticated = is_active = is_superuser = True


def refresh_pending(*, limit=500, batch_size=500):
    if connection.vendor != "postgresql":
        return 0
    # Derived state can be reconstructed after a deliberate cache reset.
    with connection.cursor() as cursor:
        cursor.execute("""INSERT INTO portal_nationalstate (organization_id,dirty,operator_counts,shared_counts,inventory_assets,installations,unknown_versions)
            SELECT o.id,true,'{}'::jsonb,'{}'::jsonb,0,0,0 FROM portal_organization o
            WHERE o.merged_into_id IS NULL AND NOT EXISTS(SELECT 1 FROM portal_nationalstate s WHERE s.organization_id=o.id)
            ON CONFLICT DO NOTHING""")
    total = 0
    while total < limit:
        with transaction.atomic():
            ids = list(
                NationalState.objects.select_for_update(skip_locked=True)
                .filter(Q(dirty=True) | Q(projection_version__isnull=True) | Q(projection_version__lt=2))
                .order_by("organization_id")
                .values_list("organization_id", flat=True)[: min(batch_size, limit - total)]
            )
            if not ids:
                break
            with overview_queries(query_timeout_ms=30000, planning_limit=4):
                _refresh(ids)
            total += len(ids)
    return total


def _refresh(ids):
    from .circl import findings_for, installations_for, outstanding, SEVERITIES

    actor = InternalReader()
    all_findings = findings_for(actor).filter(
        organization_id__in=ids,
        installation__asset__organization_id__in=ids,
        installation__asset__source__organization_id__in=ids,
        installation__product__organization_id__in=ids,
        record__organization_id__in=ids,
    )
    installed = installations_for(actor).filter(
        asset__organization_id__in=ids,
        asset__source__organization_id__in=ids,
        product__organization_id__in=ids,
    )
    assets = Asset.objects.filter(organization_id__in=ids, lifecycle="active").filter(
        consistent(source__organization_id=F("organization_id"))
    )
    asset_counts = dict(
        assets.values("organization_id").annotate(n=Count("pk")).values_list("organization_id", "n")
    )
    installed_counts = {
        r["asset__organization_id"]: r
        for r in installed.order_by()
        .values("asset__organization_id")
        .annotate(total=Count("pk"), unknown=Count("pk", filter=Q(version="")))
    }
    versions = [
        NationalVersion(organization_id=r.pop("asset__organization_id"), **r)
        for r in installed.order_by()
        .annotate(product_name=Lower("product__name"), identity=Lower("product__identifier"))
        .values("asset__organization_id", "product_name", "identity", "version")
        .annotate(name=Min("product__name"), assets=Count("asset_id", distinct=True), total=Count("pk"))
    ]
    product_versions = [
        NationalProductVersion(organization_id=r.pop("asset__organization_id"), **r)
        for r in installed.order_by()
        .values("asset__organization_id", "product_id", "version")
        .annotate(total=Count("pk"))
    ]
    problems, activity = [], []
    counters = {False: {}, True: {}}
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today - timedelta(days=29), time.min))
    rank = Case(
        *[When(record__source_severity=s, then=Value(i)) for i, s in enumerate(SEVERITIES)],
        default=Value(5),
        output_field=IntegerField(),
    )
    for shared in (False, True):
        findings = all_findings.filter(record__shareable=True) if shared else all_findings
        reviews = outstanding(findings)
        for row in (
            reviews.order_by()
            .values("organization_id")
            .annotate(
                reviews=Count("pk"),
                assets=Count("installation__asset_id", distinct=True),
                affected=Count("pk", filter=Q(analyst_applicability="affected")),
                critical=Count("pk", filter=Q(record__source_severity="critical")),
                accepted=Count("pk", filter=Q(status="accepted_risk")),
            )
        ):
            counters[shared][row.pop("organization_id")] = row
        for row in (
            reviews.order_by()
            .values("organization_id", "record__external_id")
            .annotate(
                reviews=Count("pk"),
                assets=Count("installation__asset_id", distinct=True),
                affected=Count("pk", filter=Q(analyst_applicability="affected")),
                accepted=Count("pk", filter=Q(status="accepted_risk")),
                severity_rank=Min(rank),
            )
        ):
            problems.append(
                NationalProblem(
                    organization_id=row.pop("organization_id"),
                    shared=shared,
                    external_id=row.pop("record__external_id"),
                    **row,
                )
            )
        discovered = (
            DiscoveryMatch.objects.filter(finding__in=findings, finding__organization_id__in=ids)
            .filter(
                consistent(
                    watch__product_id=F("finding__installation__product_id"),
                    evidence_revision__record_id=F("finding__record_id"),
                )
            )
            .order_by()
            .values("pk", "finding__organization_id")
            .annotate(first_at=Min("history__created_at"))
            .filter(first_at__gte=start)
        )
        closed = (
            FindingHistory.objects.filter(finding__in=findings, status="resolved", created_at__gte=start)
            .exclude(previous_status="resolved")
            .order_by()
            .annotate(day=TruncDate("created_at"))
            .values("finding__organization_id", "day")
            .annotate(n=Count("pk"))
        )
        days = defaultdict(lambda: {"new": 0, "closed": 0})
        for row in discovered.iterator(chunk_size=1000):
            day = timezone.localtime(row["first_at"]).date()
            days[(row["finding__organization_id"], day)]["new"] += 1
        for row in closed:
            days[(row["finding__organization_id"], row["day"])]["closed"] = row["n"]
        activity.extend(
            NationalActivity(organization_id=org, shared=shared, day=day, **counts)
            for (org, day), counts in days.items()
        )
    for model, rows in [
        (NationalVersion, versions),
        (NationalProductVersion, product_versions),
        (NationalProblem, problems),
        (NationalActivity, activity),
    ]:
        model.objects.filter(organization_id__in=ids).delete()
        model.objects.bulk_create(rows, batch_size=1000)
    now = timezone.now()
    states = [
        NationalState(
            organization_id=org,
            dirty=False,
            projection_version=2,
            refreshed_at=now,
            operator_counts=counters[False].get(org, {}),
            shared_counts=counters[True].get(org, {}),
            inventory_assets=asset_counts.get(org, 0),
            installations=installed_counts.get(org, {}).get("total", 0),
            unknown_versions=installed_counts.get(org, {}).get("unknown", 0),
        )
        for org in ids
    ]
    NationalState.objects.bulk_update(
        states,
        [
            "dirty",
            "projection_version",
            "refreshed_at",
            "operator_counts",
            "shared_counts",
            "inventory_assets",
            "installations",
            "unknown_versions",
        ],
        batch_size=200,
    )


def snapshot_scope(user):
    if connection.vendor != "postgresql":
        return None
    orgs = organizations_for(user)
    total = orgs.count()
    if total <= getattr(settings, "NATIONAL_SNAPSHOT_THRESHOLD", 100):
        return None
    states = NationalState.objects.filter(organization__in=orgs, dirty=False)
    coverage = states.aggregate(companies=Count("pk"), refreshed_at=Min("refreshed_at"))
    coverage["pending"] = total - coverage["companies"]
    coverage["total"] = total
    if not coverage["companies"]:
        raise PendingSnapshot("National summaries are being prepared; retry shortly.")
    return states, coverage


def audience(user):
    return (
        Q(shared=False)
        if user.is_superuser
        else Q(organization__operator_visibility=True, shared=False)
        | Q(organization__operator_visibility=False, shared=True)
    )


def snapshot_panel(user, section):
    scoped = snapshot_scope(user)
    if scoped is None:
        return None
    states, coverage = scoped
    result = {"coverage": coverage}
    # Join freshness once alongside the live organization policy instead of
    # nesting a second organization/state scan below a semi-join.
    selected = Q(organization__in=organizations_for(user), organization__national_state__dirty=False)
    if section in {"all", "summary"}:
        chosen = (
            F("operator_counts")
            if user.is_superuser
            else Case(
                When(organization__operator_visibility=True, then=F("operator_counts")),
                default=F("shared_counts"),
            )
        )
        aggregates = {
            key: Coalesce(Sum(Cast(KeyTextTransform(key, chosen), IntegerField())), 0)
            for key in ["reviews", "assets", "affected", "critical", "accepted"]
        }
        counts = states.aggregate(
            **aggregates,
            companies=Count(
                "pk",
                filter=Q(operator_counts__reviews__gt=0)
                if user.is_superuser
                else Q(organization__operator_visibility=True, operator_counts__reviews__gt=0)
                | Q(organization__operator_visibility=False, shared_counts__reviews__gt=0),
            ),
            inventory_assets=Coalesce(Sum("inventory_assets"), 0),
            installations=Coalesce(Sum("installations"), 0),
            unknown=Coalesce(Sum("unknown_versions"), 0),
        )
        counts["organizations"] = coverage["total"]
        result["counts"] = counts
    if section in {"all", "versions"}:
        result["versions"] = list(
            NationalVersion.objects.filter(selected)
            .order_by()
            .values("product_name", "identity", "version")
            .annotate(
                name=Min("name"), companies=Count("organization_id"), assets=Sum("assets"), total=Sum("total")
            )
            .order_by("-companies", "-total", "product_name", "identity", "version")[:12]
        )
    if section in {"all", "problems"}:
        from .circl import SEVERITIES

        rows = list(
            NationalProblem.objects.filter(selected)
            .filter(audience(user))
            .order_by()
            .values("external_id")
            .annotate(
                reviews=Sum("reviews"),
                assets=Sum("assets"),
                affected=Sum("affected"),
                accepted=Sum("accepted"),
                companies=Count("organization_id"),
                severity_rank=Min("severity_rank"),
            )
            .order_by("severity_rank", "-affected", "-companies", "external_id")[:12]
        )
        for row in rows:
            row["record__external_id"] = row.pop("external_id")
            row["severity"] = SEVERITIES[row["severity_rank"]]
        result["vulnerabilities"] = rows
    if section in {"all", "activity"}:
        from .circl import trend_result

        today = timezone.localdate()
        rows = (
            NationalActivity.objects.filter(selected)
            .filter(audience(user))
            .filter(day__gte=today - timedelta(days=29), day__lte=today)
            .order_by()
            .values("day")
            .annotate(new_total=Sum("new"), closed_total=Sum("closed"))
        )
        daily = list(rows)
        result["trend"] = trend_result(
            {r["day"]: r["new_total"] for r in daily}, {r["day"]: r["closed_total"] for r in daily}
        )
    return result


def snapshot_map_reviews(user):
    """Only substitute a complete currently clean audience; otherwise use live map evidence."""
    from django.db.models.functions import Greatest

    try:
        scoped = snapshot_scope(user)
    except PendingSnapshot:
        return None
    if scoped is None:
        return None
    states, coverage = scoped
    pending = []
    stable = READ_SNAPSHOT.get()
    if coverage["pending"]:
        if not stable:
            return None
        pending = list(
            organizations_for(user)
            .exclude(pk__in=states.values("organization_id"))
            .values_list("pk", flat=True)[:1001]
        )
        if len(pending) > 1000:
            return None
    rows = (
        NationalProblem.objects.filter(organization__in=states.values("organization_id"))
        .filter(audience(user))
        .order_by()
        .values("organization_id")
        .annotate(total=Sum("reviews"), rank=Greatest(Value(1), Value(5) - Min("severity_rank")))
    )
    result = {row["organization_id"]: row for row in rows}
    # Recheck freshness after aggregation; don't turn a newly dirty company into green.
    if pending:
        from .circl_map import grouped
        from .circl import findings_for, outstanding

        live = outstanding(findings_for(user)).filter(
            organization_id__in=pending,
            installation__asset__organization_id__in=pending,
            record__organization_id__in=pending,
        )
        result.update(
            grouped(live, "record__source_severity", {"critical": 5, "high": 4, "medium": 3, "low": 2})
        )
    if not stable and states.count() != coverage["total"]:
        return None
    return result


def research_projection(user, data):
    try:
        scoped = snapshot_scope(user)
    except PendingSnapshot:
        return None
    if scoped is None:
        return None
    states, coverage = scoped
    states = states.filter(projection_version=2)
    pending = None
    stable = READ_SNAPSHOT.get()
    if stable:
        pending = list(
            organizations_for(user)
            .exclude(pk__in=states.values("organization_id"))
            .values_list("pk", flat=True)[:1001]
        )
        if len(pending) > 1000:
            return None
    elif coverage["pending"] or states.count() != coverage["total"]:
        return None
    lookup = "iexact" if data["product_match"] == "exact" else "icontains"
    qs = NationalProductVersion.objects.filter(organization__in=states.values("organization_id")).filter(
        Q(**{f"product__name__{lookup}": data["product"]})
        | Q(**{f"product__identifier__{lookup}": data["product"]})
    )
    return qs, states, coverage["total"], pending, stable


DERIVED_MODELS = {
    "NationalState",
    "NationalVersion",
    "NationalProductVersion",
    "NationalProblem",
    "NationalActivity",
}
