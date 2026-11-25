"""Group the vulnerability review queue without merging its source records."""

from collections import Counter
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Case, CharField, F, Value, When
from django.db.models.functions import Cast, Least, Upper
from .presentation import SEVERITY_ORDER, severity_rank
from .review_queue import BUCKETS, classified

CVE_ID = r"^CVE-[0-9]{4}-[0-9]{4,}$"
BUCKET_ORDER = ("action", "unresolved", "pending", "cleared")
PAGE_SIZE = 25


def case_identity(reviews):
    return reviews.annotate(
        case_identifier=Case(
            When(record__external_id__iregex=CVE_ID, then=Upper("record__external_id")),
            default=Cast("record_id", CharField()),
            output_field=CharField(),
        )
    )


def case_page(reviews, number, bucket, severity):
    """Compute the histogram and page from one snapshot of authorized narrow rows."""
    evidence = (
        case_identity(classified(reviews))
        .annotate(
            source_rank=Least(severity_rank("record__source_severity"), Value(len(SEVERITY_ORDER) - 1)),
            asset_rank=Case(When(installation__asset__criticality="high", then=Value(0)), default=Value(1)),
            saved_assessment=F("analyst_applicability"),
        )
        .order_by()
        .values(
            "case_identifier",
            "queue_bucket",
            "source_rank",
            "asset_rank",
            "saved_assessment",
            finding_key=F("pk"),
            company_key=F("organization_id"),
            installation_key=F("installation_id"),
            review_time=F("evaluated_at"),
        )
    )
    sql, params = evidence.query.sql_with_params()
    bucket_rank = BUCKET_ORDER.index(bucket) if bucket != "all" else -1
    severity_rank_filter = SEVERITY_ORDER.index(severity) if severity else -1
    try:
        requested = int(number)
    except (TypeError, ValueError):
        requested = 1
    # The bounded numeric input keeps even malformed/out-of-range page links portable.
    requested = min(max(requested, 0), 2**31 - 1)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH evidence AS ({sql}),
            prioritized AS (
                SELECT evidence.*,
                       CASE queue_bucket WHEN %s THEN 0 WHEN %s THEN 1 WHEN %s THEN 2
                            ELSE 3 END AS bucket_rank
                FROM evidence
            ),
            ranked AS (
                SELECT finding_key AS id, bucket_rank, source_rank, asset_rank, review_time,
                       ROW_NUMBER() OVER (
                           case_group ORDER BY bucket_rank, source_rank, review_time DESC, finding_key
                       ) AS representative,
                       COUNT(*) OVER case_group AS evidence_count,
                       MIN(bucket_rank) OVER case_group <> MAX(bucket_rank) OVER case_group AS mixed_buckets,
                       MAX(CASE WHEN saved_assessment = 'affected' THEN 1 ELSE 0 END) OVER case_group
                       + MAX(CASE WHEN saved_assessment = 'not_affected' THEN 1 ELSE 0 END) OVER case_group
                           AS decisive_assessments
                FROM prioritized
                WINDOW case_group AS (PARTITION BY company_key, installation_key, case_identifier)
            ),
            cases AS (
                SELECT * FROM ranked WHERE representative = 1
            ),
            histogram AS (
                SELECT bucket_rank, source_rank, COUNT(*) AS total
                FROM cases GROUP BY bucket_rank, source_rank
            ),
            selected AS (
                SELECT id, bucket_rank, source_rank, evidence_count, mixed_buckets, decisive_assessments,
                       ROW_NUMBER() OVER (ORDER BY source_rank, asset_rank, review_time DESC, id) AS position,
                       COUNT(*) OVER () AS total
                FROM cases
                WHERE (%s = -1 OR bucket_rank = %s) AND (%s = -1 OR source_rank = %s)
            ),
            page_request AS (
                SELECT CAST(%s AS bigint) AS page_number, CAST(%s AS bigint) AS page_size
            ),
            paged AS (
                SELECT selected.*,
                       CASE WHEN page_number BETWEEN 1 AND (total + page_size - 1) / page_size
                            THEN (page_number - 1) * page_size
                            ELSE ((total - 1) / page_size) * page_size END AS page_start,
                       page_size
                FROM selected CROSS JOIN page_request
            )
            SELECT NULL AS id, bucket_rank, source_rank, total, NULL AS mixed_buckets,
                   NULL AS decisive_assessments, 0 AS position
            FROM histogram
            UNION ALL
            SELECT id, bucket_rank, source_rank, evidence_count, mixed_buckets, decisive_assessments, position
            FROM paged
            WHERE position > page_start AND position <= page_start + page_size
            ORDER BY position
            """,
            (
                *params,
                *BUCKET_ORDER[:3],
                bucket_rank,
                bucket_rank,
                severity_rank_filter,
                severity_rank_filter,
                requested,
                PAGE_SIZE,
            ),
        )
        rows = cursor.fetchall()
    buckets, severities, selected = Counter(), Counter(), {}
    for pk, state, rank, count, mixed, decisions, _ in rows:
        if pk is None:
            buckets[BUCKET_ORDER[state]] += count
            if bucket == "all" or bucket == BUCKET_ORDER[state]:
                severities[SEVERITY_ORDER[rank]] += count
        else:
            selected[pk] = (count, mixed, decisions == 2)

    total = sum(severities.values())
    paginator = Paginator([], PAGE_SIZE)
    paginator.count = severities[severity] if severity else total
    page = paginator.get_page(number)
    findings = {
        finding.pk: finding
        for finding in classified(reviews.filter(pk__in=selected).order_by()).select_related(
            "distro_match__component__device", "distro_match__advisory__feed"
        )
    }
    page.object_list = [findings[pk] for pk in selected if pk in findings]
    for finding in page:
        finding.evidence_count, finding.mixed_buckets, finding.conflicting_assessments = selected[finding.pk]
    states = [
        {"key": key, "label": label, "count": sum(buckets.values()) if key == "all" else buckets[key]}
        for key, label in BUCKETS
    ]
    counts = [{"key": key, "label": key.title(), "count": severities[key]} for key in SEVERITY_ORDER]
    return page, states, counts, total
