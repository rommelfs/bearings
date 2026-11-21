"""National coordination over permitted reporting inventory, not population-wide surveillance."""

from datetime import datetime, time, timedelta
from time import perf_counter
from django.db.models import (
    Case,
    Count,
    DateTimeField,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Lower, TruncDate, Coalesce
from django.utils import timezone
from .access import organizations_for, visible_findings_for
from .query_integrity import consistent
from .discovery import semver
from .models import (
    Asset,
    Contact,
    DiscoveryMatch,
    DiscoveryRevision,
    FindingHistory,
    Installation,
    InventorySource,
)
from .notifications import contact_policy
from .presentation import ACTIVE_REVIEWS

OPEN = [*ACTIVE_REVIEWS, "accepted_risk"]
SEVERITIES = ["critical", "high", "medium", "low", "none", "unknown"]
MAX_RANGE_VERSIONS = 500


def installations_for(user):
    return Installation.objects.filter(
        asset__organization__in=organizations_for(user),
        asset__lifecycle="active",
    ).filter(
        consistent(
            asset__source__organization_id=F("asset__organization_id"),
            product__organization_id=F("asset__organization_id"),
        )
    )


def findings_for(user):
    return (
        visible_findings_for(user)
        .filter(
            installation__asset__lifecycle="active",
        )
        .filter(
            consistent(
                installation__asset__organization_id=F("organization_id"),
                installation__asset__source__organization_id=F("organization_id"),
                installation__product__organization_id=F("organization_id"),
                record__organization_id=F("organization_id"),
            )
        )
    )


def outstanding(findings):
    return findings.filter(status__in=OPEN).exclude(analyst_applicability="not_affected")


def trend(findings):
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today - timedelta(days=29), time.min))
    # Visit each match once and read its earliest timestamp through a covering
    # index. Refresh history must not multiply the work or count as a discovery.
    first = (
        DiscoveryRevision.objects.filter(match_id=OuterRef("pk"))
        .order_by("created_at", "pk")
        .values("created_at")[:1]
    )
    new = (
        DiscoveryMatch.objects.filter(
            finding__in=findings,
        )
        .filter(
            consistent(
                watch__product_id=F("finding__installation__product_id"),
                evidence_revision__record_id=F("finding__record_id"),
            )
        )
        .annotate(first_at=Subquery(first))
        .filter(first_at__gte=start)
    )
    closed = FindingHistory.objects.filter(
        finding__in=findings, status="resolved", created_at__gte=start
    ).exclude(previous_status="resolved")

    def daily(qs, field="created_at"):
        return {
            row["day"]: row["total"]
            for row in qs.order_by().annotate(day=TruncDate(field)).values("day").annotate(total=Count("pk"))
        }

    return trend_result(daily(new, "first_at"), daily(closed))


def trend_result(discovered, resolved):
    today = timezone.localdate()
    days = [
        {
            "day": today - timedelta(days=29 - i),
            "new": discovered.get(today - timedelta(days=29 - i), 0),
            "closed": resolved.get(today - timedelta(days=29 - i), 0),
        }
        for i in range(30)
    ]
    peak = max([1, *[max(day["new"], day["closed"]) for day in days]])

    def points(key):
        return " ".join(f"{12 + i * 20},{148 - 128 * day[key] / peak:.1f}" for i, day in enumerate(days))

    return {
        "days": days,
        "new_points": points("new"),
        "closed_points": points("closed"),
        "peak": peak,
        "recent": sum(day["new"] for day in days[-7:]),
        "previous": sum(day["new"] for day in days[-14:-7]),
        "closures": sum(day["closed"] for day in days),
        "new": sum(day["new"] for day in days),
    }


def dashboard(user, *, timings=None, section="all"):
    timings = {} if timings is None else timings
    result = {"updated_at": timezone.now()}
    from .national_snapshots import snapshot_panel

    snapshot = snapshot_panel(user, section)
    if snapshot:
        result.update(snapshot)
    findings = findings_for(user) if section in {"all", "summary", "problems", "activity"} else None
    open_reviews = outstanding(findings) if findings is not None else None
    if section in {"all", "summary"}:
        orgs = organizations_for(user)
        assets = Asset.objects.filter(organization__in=orgs, lifecycle="active").filter(
            consistent(source__organization_id=F("organization_id"))
        )
        installed = installations_for(user)
        started = perf_counter()
        if snapshot:
            counts = snapshot["counts"]
        else:
            counts = open_reviews.aggregate(
                reviews=Count("pk"),
                assets=Count("installation__asset_id", distinct=True),
                companies=Count("organization_id", distinct=True),
                affected=Count("pk", filter=Q(analyst_applicability="affected")),
                critical=Count("pk", filter=Q(record__source_severity="critical")),
                accepted=Count("pk", filter=Q(status="accepted_risk")),
            )
            counts.update(
                installed.aggregate(installations=Count("pk"), unknown=Count("pk", filter=Q(version="")))
            )
            counts.update(organizations=orgs.count(), inventory_assets=assets.count())
        sources = InventorySource.objects.filter(organization__in=orgs).annotate(
            deadline=ExpressionWrapper(
                F("last_import_success")
                + ExpressionWrapper(
                    Cast("import_interval_minutes", IntegerField()) * Value(timedelta(minutes=2)),
                    output_field=DurationField(),
                ),
                output_field=DateTimeField(),
            )
        )
        source_counts = sources.aggregate(
            total=Count("pk"),
            synthetic=Count("pk", filter=Q(mode="development")),
            errors=Count("pk", filter=~Q(import_error="")),
            stale=Count(
                "pk",
                filter=(
                    Q(mode="manual")
                    & (
                        Q(organization__inventory_review_policy__isnull=True)
                        | Q(organization__inventory_review_policy__last_reviewed_at__isnull=True)
                        | Q(organization__inventory_review_policy__next_due__lte=timezone.localdate())
                    )
                )
                | ~Q(mode__in=["development", "manual"])
                & (
                    Q(instance__isnull=True)
                    | Q(instance__enabled=False)
                    | Q(last_import_success__isnull=True)
                    | Q(deadline__lt=timezone.now())
                ),
            ),
        )
        source_counts["missing"] = counts["organizations"] - source_counts["total"]
        contacts = Contact.objects.filter(organization_id=OuterRef("pk"), **contact_policy()).exclude(
            function="dpo"
        )
        counts["no_contact"] = orgs.filter(~Exists(contacts)).count()
        timings["nationalcounts"] = (perf_counter() - started) * 1000
        result.update(counts=counts, sources=source_counts)
    if section in {"all", "versions"} and not snapshot:
        started = perf_counter()
        installed = installations_for(user)
        versions = list(
            installed.order_by()
            .annotate(product_name=Lower("product__name"), identity=Lower("product__identifier"))
            .values("product_name", "identity", "version")
            .annotate(
                name=Min("product__name"),
                companies=Count("asset__organization_id", distinct=True),
                assets=Count("asset_id", distinct=True),
                total=Count("pk"),
            )
            .order_by("-companies", "-total", "product_name", "identity", "version")[:12]
        )
        timings["nationalversions"] = (perf_counter() - started) * 1000
        result["versions"] = versions
    if section in {"all", "problems"} and not snapshot:
        started = perf_counter()
        vulnerabilities = list(
            open_reviews.order_by()
            .values("record__external_id")
            .annotate(
                reviews=Count("pk"),
                companies=Count("organization_id", distinct=True),
                assets=Count("installation__asset_id", distinct=True),
                affected=Count("pk", filter=Q(analyst_applicability="affected")),
                accepted=Count("pk", filter=Q(status="accepted_risk")),
                severity_rank=Min(
                    Case(
                        *[When(record__source_severity=s, then=Value(i)) for i, s in enumerate(SEVERITIES)],
                        default=Value(5),
                        output_field=IntegerField(),
                    )
                ),
            )
            .order_by("severity_rank", "-affected", "-companies", "record__external_id")[:12]
        )
        for row in vulnerabilities:
            row["severity"] = SEVERITIES[row["severity_rank"]]
        timings["nationalvulns"] = (perf_counter() - started) * 1000
        result["vulnerabilities"] = vulnerabilities
    if section in {"all", "activity"} and not snapshot:
        started = perf_counter()
        result["trend"] = trend(findings)
        timings["nationaltrend"] = (perf_counter() - started) * 1000
    return result


def research(user, data):
    lookup = "iexact" if data["product_match"] == "exact" else "icontains"
    text = data["product"]
    candidates = installations_for(user).filter(
        Q(**{f"product__name__{lookup}": text}) | Q(**{f"product__identifier__{lookup}": text})
    )
    from .national_snapshots import research_projection

    projection = research_projection(user, data)
    pending_candidates = (
        candidates.filter(
            asset__organization_id__in=projection[3],
            asset__source__organization_id__in=projection[3],
            product__organization_id__in=projection[3],
        )
        if projection and projection[3]
        else None
    )
    known = candidates.exclude(version="")
    unknown = candidates.filter(version="")
    unsupported = candidates.none()
    if data["mode"] == "exact":
        matches = known.filter(version=data["version"])
    elif data["mode"] == "range":
        version_source = projection[0].exclude(version="") if projection else known
        versions = list(
            version_source.order_by("version")
            .values_list("version", flat=True)
            .distinct()[: MAX_RANGE_VERSIONS + 1]
        )
        if pending_candidates is not None:
            pending_versions = list(
                pending_candidates.exclude(version="")
                .order_by("version")
                .values_list("version", flat=True)
                .distinct()[: MAX_RANGE_VERSIONS + 1]
            )
            versions = sorted(set(versions) | set(pending_versions))
        if projection and not projection[4] and projection[1].count() != projection[2]:
            projection = None
            versions = list(
                known.order_by("version")
                .values_list("version", flat=True)
                .distinct()[: MAX_RANGE_VERSIONS + 1]
            )
        if len(versions) > MAX_RANGE_VERSIONS:
            raise ValueError(
                f"More than {MAX_RANGE_VERSIONS} distinct versions match this product query. Refine it; no partial results are shown."
            )
        low, high = semver(data["minimum"]), semver(data["maximum"])
        matched, unparsed = [], []
        for version in versions:
            parsed = semver(version)
            if parsed is None:
                unparsed.append(version)
            elif (low is None or parsed >= low) and (high is None or parsed < high):
                matched.append(version)
        matches = known.filter(version__in=matched)
        unsupported = known.filter(version__in=unparsed)
    else:
        matches = known
    if data["mode"] == "exact":
        matching_rule = ~Q(version="") & Q(version=data["version"])
    elif data["mode"] == "range":
        matching_rule = ~Q(version="") & Q(version__in=matched)
    else:
        matching_rule = ~Q(version="")
    aggregate_source = projection[0] if projection else candidates

    def counted(rule):
        return Coalesce(Sum("total", filter=rule), 0) if projection else Count("pk", filter=rule)

    unsupported_rule = Q(version__in=unparsed) if data["mode"] == "range" else Q(pk__in=[])
    counts = aggregate_source.aggregate(
        matches=counted(matching_rule), unknown=counted(Q(version="")), unsupported=counted(unsupported_rule)
    )
    if pending_candidates is not None:
        added = pending_candidates.aggregate(
            matches=Count("pk", filter=matching_rule),
            unknown=Count("pk", filter=Q(version="")),
            unsupported=Count("pk", filter=unsupported_rule),
        )
        counts = {key: value + added[key] for key, value in counts.items()}
    if projection and not projection[4] and projection[1].count() != projection[2]:
        counts = candidates.aggregate(
            matches=Count("pk", filter=matching_rule),
            unknown=Count("pk", filter=Q(version="")),
            unsupported=Count("pk", filter=unsupported_rule),
        )
    selected = {"matches": matches, "unknown": unknown, "unsupported": unsupported}[data["bucket"]]
    return selected, counts
