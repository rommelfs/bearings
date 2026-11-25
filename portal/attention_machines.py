"""One compact attention card per machine, with at most three product teasers."""

from collections import defaultdict
from django.core.paginator import Paginator
from django.db.models import Case, Exists, F, IntegerField, Min, OuterRef, Q, Value, When, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from .review_focus import posture
from .review_queue import classified
from .circl import findings_for
from .issues import visible_issues, active_filter
from .presentation import SEVERITY_ORDER


def page_for(user, org_ids, number):
    machines = posture(user, org_ids, include_totals=False)["machines"]
    reviews = findings_for(user).filter(installation__asset_id=OuterRef("pk"))
    operational = (
        visible_issues(user)
        .filter(active_filter(), asset_id=OuterRef("pk"))
        .filter(~Q(kind="vulnerability") | Q(action_due__isnull=False) | ~Q(next_action=""))
    )
    machines = machines.annotate(
        human=Exists(
            reviews.filter(
                analyst_applicability="affected",
                status__in=["new", "under_review", "confirmed", "accepted_risk"],
            )
        ),
        operational=Exists(operational),
        overdue=Exists(operational.filter(action_due__lt=timezone.localdate())),
        operational_critical=Exists(operational.filter(priority="critical")),
        operational_high=Exists(operational.filter(priority="high")),
    ).filter(
        Q(evaluated=True, version_match=True)
        | Q(human=True)
        | Q(manual=True)
        | Q(operational=True)
        | Q(evaluated=False)
    )
    machines = machines.annotate(
        rank=Case(
            When(overdue=True, then=Value(0)),
            When(Q(evaluated=True, critical=True) | Q(operational_critical=True), then=Value(1)),
            When(human=True, then=Value(2)),
            When(evaluated=True, high=True, then=Value(3)),
            When(evaluated=True, version_match=True, then=Value(4)),
            When(operational=True, then=Value(5)),
            When(evaluated=False, then=Value(6)),
            default=Value(7),
            output_field=IntegerField(),
        )
    )
    page = Paginator(
        machines.select_related("organization")
        .defer("upstream_data")
        .order_by("rank", "organization__name", "name", "pk"),
        25,
    ).get_page(number)
    page.object_list = list(page.object_list)
    ids = [a.pk for a in page]
    teasers = defaultdict(list)
    rows = (
        classified(findings_for(user).filter(installation__asset_id__in=ids))
        .exclude(queue_bucket="cleared")
        .order_by()
        .values("installation__asset_id", "installation__product__name")
        .annotate(
            kind=Min(
                Case(
                    When(analyst_applicability="affected", then=Value(0)),
                    When(package_current=True, distro_match__queue_proof__verdict="affected", then=Value(1)),
                    When(distro_match__isnull=True, then=Value(2)),
                    default=Value(3),
                )
            ),
            severity=Min(
                Case(
                    *[When(record__source_severity=k, then=Value(i)) for i, k in enumerate(SEVERITY_ORDER)],
                    default=Value(5),
                )
            ),
        )
        .annotate(
            position=Window(
                RowNumber(),
                partition_by=[F("installation__asset_id")],
                order_by=[F("kind"), F("severity"), F("installation__product__name")],
            )
        )
        .filter(position__lte=3)
    )
    for row in rows:
        teasers[row["installation__asset_id"]].append(
            {
                "name": row["installation__product__name"],
                "label": (
                    "Saved affected assessment",
                    "Version match",
                    "Applicability to verify",
                    "Vendor clarification / evaluation pending",
                )[row["kind"]],
                "priority": SEVERITY_ORDER[row["severity"]].title(),
            }
        )
    operational_teasers = defaultdict(list)
    issue_rows = (
        visible_issues(user)
        .filter(active_filter(), asset_id__in=ids)
        .filter(~Q(kind="vulnerability") | Q(action_due__isnull=False) | ~Q(next_action=""))
        .order_by()
        .values("asset_id", "title", "installation__product__name")
        .annotate(
            rank=Min(
                Case(
                    When(priority="critical", then=Value(0)),
                    When(priority="high", then=Value(1)),
                    default=Value(2),
                )
            )
        )
    )
    issue_rows = issue_rows.annotate(
        position=Window(
            RowNumber(),
            partition_by=[F("asset_id")],
            order_by=[F("rank"), F("title"), F("installation__product__name")],
        )
    ).filter(position__lte=2)
    for row in issue_rows:
        operational_teasers[row["asset_id"]].append(row["installation__product__name"] or row["title"])
    for machine in page:
        machine.teasers = teasers[machine.pk]
        machine.operational_teasers = operational_teasers[machine.pk]
    return page
