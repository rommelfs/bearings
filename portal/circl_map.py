"""Current scoped company locations and bounded problem markers, without external geography calls."""

import heapq
from bisect import insort
from urllib.parse import quote, urlencode
from django.db.models import Case, Count, IntegerField, Max, Value, When
from django.urls import reverse
from .access import organizations_for, visible_findings_for
from .circl import OPEN
from .geography import address_digest, local_location
from .issues import visible_issues
from .review_queue import classified
from .review_work import scoped_work

LEVELS = ["no_open", "unrated", "low", "medium", "high", "critical"]
MAX_POINTS = 2000


def company_location(org):
    point = getattr(org, "map_location", None)
    if point and point.address_digest == address_digest(org.postal_address):
        return {
            "lat": float(point.latitude),
            "lon": float(point.longitude),
            "method": "manual",
            "label": "Manually positioned · not independently verified",
        }
    return local_location(org.postal_address)


def grouped(qs, field, levels, *, identity):
    rank = Case(
        *[When(**{field: key}, then=Value(value)) for key, value in levels.items()],
        default=Value(1),
        output_field=IntegerField(),
    )
    return {
        r["organization_id"]: r
        for r in qs.order_by()
        .values("organization_id")
        .annotate(total=Count(identity, distinct=True), rank=Max(rank))
    }


def map_data(user):
    organizations = organizations_for(user)
    current = classified(visible_findings_for(user), organizations=organizations.values("pk"))
    affected = grouped(
        scoped_work(current, "affected"),
        "record__source_severity",
        {"critical": 5, "high": 4, "medium": 3, "low": 2},
        identity="installation__asset_id",
    )
    other = grouped(
        visible_issues(user, standalone=True).filter(
            finding__isnull=True, asset__lifecycle="active", status__in=OPEN
        ),
        "priority",
        {"critical": 5, "high": 4, "review": 3, "low": 2},
        identity="pk",
    )
    summary = {
        "companies": 0,
        "located": 0,
        "unlocated": 0,
        "missing_address": 0,
        "stale_manual": 0,
        "unlocated_with_problems": 0,
    }
    unlocated = []

    def priority(item):
        return -item["rank"], -item["affected_assets"] - item["issues"], item["name"].casefold(), item["id"]

    def markers():
        for org in (
            organizations.select_related("map_location")
            .only(
                "name",
                "slug",
                "postal_address",
                "operator_visibility",
                "map_location__latitude",
                "map_location__longitude",
                "map_location__address_digest",
            )
            .order_by("pk")
            .iterator(chunk_size=500)
        ):
            summary["companies"] += 1
            location = company_location(org)
            impact = affected.get(org.pk, {})
            issue = other.get(org.pk, {})
            rank = max(impact.get("rank", 0), issue.get("rank", 0))
            item = {
                "id": org.pk,
                "name": org.name,
                "slug": org.slug,
                "level": LEVELS[rank],
                "rank": rank,
                "affected_assets": impact.get("total", 0),
                "issues": issue.get("total", 0),
                "location_editable": user.is_superuser or org.operator_visibility,
            }
            point = getattr(org, "map_location", None)
            if point and point.address_digest != address_digest(org.postal_address):
                summary["stale_manual"] += 1
            if location:
                summary["located"] += 1
                yield {**item, **location}
            else:
                summary["unlocated"] += 1
                summary["missing_address"] += int(not org.postal_address.strip())
                summary["unlocated_with_problems"] += int(rank > 0)
                insort(unlocated, item, key=priority)
                if len(unlocated) > 50:
                    unlocated.pop()

    points = heapq.nsmallest(MAX_POINTS, markers(), key=priority)
    # Resolve constant route shapes once per response, including any script prefix.
    slug_slot = "__bearings_map_company__"
    company_prefix, _, company_suffix = reverse("organization", args=[slug_slot]).rpartition(slug_slot)
    location_prefix, _, location_suffix = reverse("circl-map-location", args=[slug_slot]).rpartition(
        slug_slot
    )
    evidence_prefix, _, evidence_suffix = reverse("intelligence", args=[slug_slot]).rpartition(slug_slot)
    affected_query = urlencode({"view": "machine", "state": "affected"})
    issue_route = reverse("issues")
    for item in [*points, *unlocated]:
        slug = quote(item["slug"], safe="")
        item.update(
            company_url=f"{company_prefix}{slug}{company_suffix}",
            affected_url=f"{evidence_prefix}{slug}{evidence_suffix}?{affected_query}",
            issues_url=f"{issue_route}?" + urlencode({"organization": item["slug"], "state": "map-open"}),
            location_url=f"{location_prefix}{slug}{location_suffix}" if item.pop("location_editable") else "",
        )
    summary["shown"] = len(points)
    summary["omitted"] = summary["located"] - len(points)
    return {"summary": summary, "points": points, "unlocated": unlocated, "limit": MAX_POINTS}
