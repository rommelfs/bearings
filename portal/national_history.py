"""Forward-only daily stock observations, separate from rebuildable national projections."""

from datetime import timedelta
from django.db import connection, transaction
from django.db.models import Case, Count, Exists, F, IntegerField, Min, Max, OuterRef, Q, Sum, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from .access import organizations_for
from .models import NationalState, NationalHistoryPolicy, NationalDailySnapshot, InventorySource, Contact
from .notifications import contact_policy
from .timelines import series, window

REVIEW_KEYS = ["reviews", "assets", "affected", "critical", "accepted"]
COVERAGE_KEYS = [
    "inventory_assets",
    "installations",
    "unknown",
    "no_contact",
    "stale",
    "missing",
    "errors",
    "synthetic",
]


def capture_daily(*, limit=500):
    """Latest successful capture per local day, normally hourly; never capture dirty state."""
    if connection.vendor != "postgresql":
        return 0  # Bulk policy guards and row-lock serialization require PostgreSQL.
    if not 1 <= limit <= 1000:
        raise ValueError("Use a bounded history batch of 1–1000 companies")
    now = timezone.now()
    day, zone = timezone.localdate(now), timezone.get_current_timezone_name()
    fresh = NationalDailySnapshot.objects.filter(
        organization_id=OuterRef("organization_id"),
        day=day,
        timezone=zone,
        captured_at__gt=now - timedelta(hours=1),
        policy_generation=F("organization__history_policy__generation"),
    )
    with transaction.atomic():
        states = list(
            NationalState.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(dirty=False, projection_version=2, organization__merged_into__isnull=True)
            .filter(~Exists(fresh))
            .order_by("organization_id")[:limit]
        )
        ids = [s.organization_id for s in states]
        if not ids:
            return 0
        NationalHistoryPolicy.objects.bulk_create(
            [NationalHistoryPolicy(organization_id=i) for i in ids], ignore_conflicts=True
        )
        policies = dict(
            NationalHistoryPolicy.objects.select_for_update()
            .filter(organization_id__in=ids)
            .order_by("organization_id")
            .values_list("organization_id", "generation")
        )
        sources = {
            s.organization_id: s
            for s in InventorySource.objects.filter(organization_id__in=ids).select_related(
                "instance", "organization__inventory_review_policy"
            )
        }
        reachable = set(
            Contact.objects.filter(organization_id__in=ids, **contact_policy())
            .exclude(function="dpo")
            .values_list("organization_id", flat=True)
        )
        rows = []
        for state in states:
            source = sources.get(state.organization_id)
            stale = False
            if source and source.mode == "manual":
                review = getattr(source.organization, "inventory_review_policy", None)
                stale = not review or not review.last_reviewed_at or review.next_due <= day
            elif source and source.mode != "development":
                stale = (
                    not source.instance_id
                    or not source.instance.enabled
                    or not source.last_import_success
                    or source.last_import_success + timedelta(minutes=source.import_interval_minutes * 2)
                    < now
                )
            coverage = dict(
                inventory_assets=state.inventory_assets,
                installations=state.installations,
                unknown=state.unknown_versions,
                no_contact=int(state.organization_id not in reachable),
                stale=int(bool(stale)),
                missing=int(source is None),
                errors=int(bool(source and source.import_error)),
                synthetic=int(bool(source and source.mode == "development")),
            )
            rows.append(
                NationalDailySnapshot(
                    organization_id=state.organization_id,
                    day=day,
                    timezone=zone,
                    captured_at=now,
                    policy_generation=policies[state.organization_id],
                    operator_counts=state.operator_counts,
                    shared_counts=state.shared_counts,
                    coverage_counts=coverage,
                )
            )
        NationalDailySnapshot.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["organization", "day", "timezone"],
            update_fields=[
                "captured_at",
                "policy_generation",
                "operator_counts",
                "shared_counts",
                "coverage_counts",
            ],
        )
    return len(rows)


def stock_history(user):
    """Require a complete current cohort per date; missing/restricted rows produce gaps."""
    first, _, _ = window()
    orgs = organizations_for(user)
    expected = orgs.count()
    chosen = (
        F("operator_counts")
        if user.is_superuser
        else Case(
            When(organization__operator_visibility=True, then=F("operator_counts")),
            default=F("shared_counts"),
        )
    )
    rows = NationalDailySnapshot.objects.filter(
        organization__in=orgs,
        timezone=timezone.get_current_timezone_name(),
        day__gte=first,
        day__lte=timezone.localdate(),
        captured_at__lte=timezone.now(),
        policy_generation=F("organization__history_policy__generation"),
    ).annotate(selected_counts=chosen)
    sums = {
        key: Coalesce(Sum(Cast(KeyTextTransform(key, "selected_counts"), IntegerField())), 0)
        for key in REVIEW_KEYS
    }
    sums.update(
        {
            key: Coalesce(Sum(Cast(KeyTextTransform(key, "coverage_counts"), IntegerField())), 0)
            for key in COVERAGE_KEYS
        }
    )
    sums["companies"] = Count("pk", filter=Q(selected_counts__reviews__gt=0))
    aggregated = list(
        rows.order_by()
        .values("day")
        .annotate(
            samples=Count("pk"),
            captured_earliest=Min("captured_at"),
            captured_latest=Max("captured_at"),
            **sums,
        )
    )
    daily = {r["day"]: r for r in aggregated if r["samples"] == expected and expected > 0}
    description = "Daily stock observations for the currently permitted companies, using each company's latest successful capture that day. Today is provisional. No backfill or interpolation: missing/incomplete dates and restricted historical scopes are gaps, not zero. Scope changes can change the displayed history; this is not a fixed national population."
    charts = [
        series(title, description, keys, daily, missing=None)
        for title, keys in [
            (
                "Review stock · last 30 days",
                {
                    "reviews": "Outstanding reviews",
                    "affected": "Confirmed affected reviews",
                    "companies": "Companies with open reviews",
                    "critical": "Critical source-severity reviews",
                    "accepted": "Accepted-risk reviews",
                },
            ),
            (
                "Inventory stock · last 30 days",
                {"inventory_assets": "Active inventory assets", "installations": "Recorded installations"},
            ),
            (
                "Coverage gaps · last 30 days",
                {
                    "unknown": "Unknown versions",
                    "no_contact": "Companies without verified response contact",
                    "stale": "Stale/disabled sources",
                    "missing": "Missing sources",
                    "errors": "Import errors",
                    "synthetic": "Synthetic/development sources",
                },
            ),
        ]
    ]
    from datetime import date

    for chart in charts:
        for row in chart["rows"]:
            observation = daily.get(date.fromisoformat(row["date"]))
            row["capture_window"] = (
                (
                    timezone.localtime(observation["captured_earliest"]).strftime("%Y-%m-%d %H:%M")
                    + " – "
                    + timezone.localtime(observation["captured_latest"]).strftime("%H:%M")
                )
                if observation
                else "Not captured / withheld"
            )
    return {
        "charts": charts,
        "complete_days": len(daily),
        "companies": expected,
        "latest_capture": max((r["captured_latest"] for r in daily.values()), default=None),
        "partial_days": sum(1 for r in aggregated if r["samples"] < expected),
    }
