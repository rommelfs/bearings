"""Group the vulnerability review queue without merging its source records."""

from collections import Counter
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Case, CharField, F, Value, When
from django.db.models.functions import Cast, Least, Upper
from .presentation import SEVERITY_ORDER, severity_first, severity_rank
from .review_queue import BUCKETS, classified, discovery_version_status
from .review_update_preview import FIX_FEED, FIX_PROOF, fix_targets
from .ubuntu_status import NO_FIX_REASON_LABELS, TRIAGE_LABEL

CVE_ID = r"^CVE-[0-9]{4}-[0-9]{4,}$"
BUCKET_ORDER = tuple(key for key, _ in BUCKETS if key != "all")
PAGE_SIZE = 25
SOFTWARE_PREVIEW_LIMIT = 6
SMALL_CASE_SCOPE_LIMIT = 250


def case_identity(reviews):
    return reviews.annotate(
        case_identifier=Case(
            When(record__external_id__iregex=CVE_ID, then=Upper("record__external_id")),
            default=Cast("record_id", CharField()),
            output_field=CharField(),
        )
    )


def case_page(reviews, number, bucket, severity, search=None, *, prioritize_assets=True, evidence_scope=None):
    """Compute the histogram and page from one snapshot of authorized narrow rows."""
    evidence = (
        case_identity(classified(evidence_scope if evidence_scope is not None else reviews))
        .annotate(
            source_rank=Least(severity_rank("record__source_severity"), Value(len(SEVERITY_ORDER) - 1)),
            asset_rank=Case(When(installation__asset__criticality="high", then=Value(0)), default=Value(1))
            if prioritize_assets
            else Value(0),
            saved_assessment=F("analyst_applicability"),
            search_match=Case(When(search, then=Value(1)), default=Value(0))
            if search is not None
            else Value(1),
        )
        .order_by()
        .values(
            "case_identifier",
            "queue_bucket",
            "source_rank",
            "asset_rank",
            "saved_assessment",
            "search_match",
            finding_key=F("pk"),
            company_key=F("organization_id"),
            installation_key=F("installation_id"),
            asset_key=F("installation__asset_id"),
            software_name=F("installation__product__name"),
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
    # A group containing actionable evidence keeps its higher-ranked representative.
    ranking = " ".join(f"WHEN %s THEN {rank}" for rank, _ in enumerate(BUCKET_ORDER[:-1]))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH evidence AS ({sql}),
            prioritized AS (
                SELECT evidence.*,
                       CASE queue_bucket {ranking} ELSE {len(BUCKET_ORDER) - 1} END AS bucket_rank
                FROM evidence
            ),
            ranked AS (
                SELECT finding_key AS id, bucket_rank, source_rank, asset_rank, review_time,
                       company_key, asset_key, case_identifier,
                       MAX(search_match) OVER case_group AS matched_search,
                       MIN(installation_key) OVER case_group <> MAX(installation_key) OVER case_group
                           AS multiple_installations,
                       ROW_NUMBER() OVER (
                           case_group ORDER BY bucket_rank, source_rank, review_time DESC, finding_key
                       ) AS representative,
                       COUNT(*) OVER case_group AS evidence_count,
                       MIN(bucket_rank) OVER case_group <> MAX(bucket_rank) OVER case_group AS mixed_buckets,
                       MAX(CASE WHEN saved_assessment = 'affected' THEN 1 ELSE 0 END) OVER case_group
                       + MAX(CASE WHEN saved_assessment = 'not_affected' THEN 1 ELSE 0 END) OVER case_group
                           AS decisive_assessments
                FROM prioritized
                WINDOW case_group AS (PARTITION BY company_key, asset_key, case_identifier)
            ),
            cases AS (
                SELECT * FROM ranked WHERE representative = 1 AND matched_search = 1
            ),
            histogram AS (
                SELECT bucket_rank, source_rank, COUNT(*) AS total
                FROM cases GROUP BY bucket_rank, source_rank
            ),
            selected AS (
                SELECT cases.*,
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
            ),
            page_cases AS (
                SELECT * FROM paged WHERE position > page_start AND position <= page_start + page_size
            ),
            software AS (
                SELECT page_cases.id, MIN(prioritized.bucket_rank) AS software_bucket,
                       prioritized.software_name
                FROM page_cases JOIN prioritized USING (company_key, asset_key, case_identifier)
                WHERE page_cases.multiple_installations
                GROUP BY page_cases.id, prioritized.software_name
            ),
            software_previews AS (
                SELECT software.*,
                       COUNT(*) OVER (PARTITION BY id) AS software_count,
                       ROW_NUMBER() OVER (PARTITION BY id ORDER BY software_bucket, software_name) AS rank
                FROM software
            )
            SELECT 0 AS kind, NULL AS id, bucket_rank, source_rank, total, NULL AS mixed_buckets,
                   NULL AS decisive_assessments, NULL AS multiple_installations,
                   NULL AS software_name, 0 AS position, 0 AS software_rank
            FROM histogram
            UNION ALL
            SELECT 1, id, bucket_rank, source_rank, evidence_count, mixed_buckets, decisive_assessments,
                   multiple_installations, NULL, position, 0
            FROM page_cases
            UNION ALL
            SELECT 2, id, software_bucket, NULL, software_count, NULL, NULL, NULL, software_name, 0, rank
            FROM software_previews WHERE rank <= %s
            ORDER BY kind, position, software_rank
            """,
            (
                *params,
                *BUCKET_ORDER[:-1],
                bucket_rank,
                bucket_rank,
                severity_rank_filter,
                severity_rank_filter,
                requested,
                PAGE_SIZE,
                SOFTWARE_PREVIEW_LIMIT,
            ),
        )
        rows = cursor.fetchall()
    buckets, severities, selected = Counter(), Counter(), {}
    software, software_counts = {}, {}
    for kind, pk, state, rank, count, mixed, decisions, multiple, name, _, preview_rank in rows:
        if kind == 0:
            buckets[BUCKET_ORDER[state]] += count
            if bucket == "all" or bucket == BUCKET_ORDER[state]:
                severities[SEVERITY_ORDER[rank]] += count
        elif kind == 1:
            selected[pk] = (count, mixed, decisions == 2, multiple)
        else:
            software.setdefault(pk, []).append((name, BUCKET_ORDER[state]))
            if preview_rank == 1:
                software_counts[pk] = count

    total = sum(severities.values())
    paginator = Paginator([], PAGE_SIZE)
    paginator.count = severities[severity] if severity else total
    page = paginator.get_page(number)
    findings = {
        finding.pk: finding
        for finding in classified(reviews.filter(pk__in=selected).order_by())
        .annotate(discovery_version=discovery_version_status())
        .select_related("distro_match__component__device", "distro_match__advisory__feed")
    }
    page.object_list = [findings[pk] for pk in selected if pk in findings]
    for finding in page:
        (
            finding.evidence_count,
            finding.mixed_buckets,
            finding.conflicting_assessments,
            finding.multiple_installations,
        ) = selected[finding.pk]
        finding.software_preview = software.get(finding.pk, [])
        finding.more_software = software_counts.get(finding.pk, 0) - len(finding.software_preview)
        finding.case_category = dict(BUCKETS)[finding.queue_bucket]
    states = [
        {"key": key, "label": label, "count": sum(buckets.values()) if key == "all" else buckets[key]}
        for key, label in BUCKETS
    ]
    counts = [{"key": key, "label": key.title(), "count": severities[key]} for key in SEVERITY_ORDER]
    return page, states, counts, total


def evidence_page(visible, finding, number):
    evidence = (
        severity_first(
            classified(
                visible.filter(
                    organization_id=finding.organization_id,
                    installation__asset_id=finding.installation.asset_id,
                    case_identifier=finding.case_identifier,
                )
            )
        )
        .annotate(discovery_version=discovery_version_status())
        .values(
            "pk",
            "record__source",
            "discovery_version",
            "record__source_severity",
            "installation__product__name",
            "installation__version",
            "installation__edition",
            "installation__build",
            "rule",
            "queue_bucket",
            "package_current",
            "distro_match__pk",
            "distro_match__queue_proof__verdict",
            "distro_match__queue_proof__uncertainty_reason",
            "analyst_applicability",
            "status",
            FIX_PROOF,
            FIX_FEED,
        )
    )
    page = Paginator(evidence, 25).get_page(number)
    labels = dict(BUCKETS)
    verdicts = {
        "affected": "Affected version",
        "fixed": "Includes vendor fix",
        "not_matched": "Vendor rule does not match",
    }
    rows = list(page)
    for row in rows:
        row["category"] = labels[row["queue_bucket"]]
        if row["package_current"]:
            row["result"] = verdicts.get(
                row["distro_match__queue_proof__verdict"], "Vendor clarification needed"
            )
            if row["queue_bucket"] == "vendor_no_fix":
                row["result"] = NO_FIX_REASON_LABELS[row["distro_match__queue_proof__uncertainty_reason"]]
            elif row["queue_bucket"] == "vendor_triage":
                row["result"] = TRIAGE_LABEL
            if row["distro_match__queue_proof__verdict"] == "affected":
                row["update_targets"] = fix_targets(row)
        elif row["distro_match__pk"]:
            row["result"] = "Current package evaluation pending"
        elif row["discovery_version"] == "affected":
            row["result"] = "Installed version in the published affected range"
        elif row["discovery_version"] == "not_affected":
            row["result"] = "Installed version outside the published affected range"
        elif row["queue_bucket"] == "cleared":
            row["result"] = "Cleared by current version evidence or a saved assessment"
        else:
            row["result"] = "—"
    page.object_list = rows
    return page
