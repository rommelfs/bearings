"""Retained events under current read policy, never reconstructed historical inventory."""

from datetime import datetime, time, timedelta
from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from .models import AgentReport, FindingHistory


def window():
    now = timezone.now()
    first = timezone.localdate(now) - timedelta(days=29)
    return first, timezone.make_aware(datetime.combine(first, time.min)), now


def series(title, description, labels, daily):
    first, _, _ = window()
    rows = []
    for i in range(30):
        day = first + timedelta(days=i)
        rows.append({"date": day.isoformat(), "counts": [daily.get(day, {}).get(key, 0) for key in labels]})
    return {
        "title": title,
        "description": description,
        "labels": list(labels.values()),
        "rows": rows,
        "start": rows[0]["date"],
        "end": rows[-1]["date"],
        "timezone": timezone.get_current_timezone_name(),
        "total": sum(sum(row["counts"]) for row in rows),
        "chart": {
            "labels": [r["date"] for r in rows],
            "series": [
                {"name": name, "data": [r["counts"][i] for r in rows]}
                for i, name in enumerate(labels.values())
            ],
        },
    }


def review_decisions(findings):
    findings = findings.filter(
        installation__asset__organization_id=F("organization_id"),
        installation__asset__source__organization_id=F("organization_id"),
        installation__product__organization_id=F("organization_id"),
        record__organization_id=F("organization_id"),
    )
    _, start, now = window()
    rows = (
        FindingHistory.objects.filter(finding__in=findings, created_at__gte=start, created_at__lte=now)
        .exclude(previous_status=F("status"))
        .order_by()
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            confirmed=Count("pk", filter=Q(status="confirmed")),
            resolved=Count("pk", filter=Q(status="resolved")),
            reopened=Count(
                "pk", filter=Q(previous_status="resolved", status__in=["new", "under_review", "confirmed"])
            ),
        )
    )
    return series(
        "Review decisions · last 30 days",
        "Recorded status transitions for currently visible reviews matching the selected filters, across all pages. Confirmed means a workflow decision; resolved does not prove patch installation. A reopened confirmation can appear in both series. This is not the historical open-CVE count.",
        {
            "confirmed": "Confirmed decisions",
            "resolved": "Resolved decisions",
            "reopened": "Reopened reviews",
        },
        {r["day"]: r for r in rows},
    )


def report_receipts(devices):
    _, start, now = window()
    # Refuse inconsistent device/source/asset lineage, as in inventory projection.
    reports = AgentReport.objects.filter(
        device__in=devices,
        received_at__gte=start,
        received_at__lte=now,
        device__organization_id=F("device__source__organization_id"),
        device__source_id=F("device__asset__source_id"),
    ).filter(device__organization_id=F("device__asset__organization_id"))
    rows = (
        reports.order_by()
        .annotate(day=TruncDate("received_at"))
        .values("day")
        .annotate(
            applied=Count("pk", filter=Q(status="applied")),
            pending=Count("pk", filter=Q(status="pending")),
            rejected=Count("pk", filter=Q(status="rejected")),
            superseded=Count("pk", filter=Q(status="superseded")),
        )
    )
    return series(
        "Client report receipts · last 30 days",
        "Reports grouped by server receipt date and their current processing status. Later processing can change earlier daily status counts. These are reports, not unique servers or proof of inventory completeness; superseded does not mean rejected. Selected device only when one is open, otherwise all company devices.",
        {"applied": "Applied", "pending": "Pending", "rejected": "Rejected", "superseded": "Superseded"},
        {r["day"]: r for r in rows},
    )
