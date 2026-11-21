"""Current scoped company locations and bounded problem markers, without external geography calls."""

import heapq
from django.db.models import Case, Count, IntegerField, Max, Value, When
from django.urls import reverse
from .access import organizations_for
from .circl import OPEN, findings_for, outstanding
from .geography import address_digest, local_location
from .issues import visible_issues

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


def grouped(qs, field, levels):
    rank = Case(
        *[When(**{field: key}, then=Value(value)) for key, value in levels.items()],
        default=Value(1),
        output_field=IntegerField(),
    )
    return {
        r["organization_id"]: r
        for r in qs.order_by().values("organization_id").annotate(total=Count("pk"), rank=Max(rank))
    }


def map_data(user):
    from .national_snapshots import snapshot_map_reviews

    reviews = snapshot_map_reviews(user)
    if reviews is None:
        reviews = grouped(
            outstanding(findings_for(user)),
            "record__source_severity",
            {"critical": 5, "high": 4, "medium": 3, "low": 2},
        )
    other = grouped(
        visible_issues(user, standalone=True).filter(
            finding__isnull=True, asset__lifecycle="active", status__in=OPEN
        ),
        "priority",
        {"critical": 5, "high": 4, "review": 3, "low": 2},
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

    def markers():
        for org in (
            organizations_for(user).select_related("map_location").order_by("pk").iterator(chunk_size=500)
        ):
            summary["companies"] += 1
            location = company_location(org)
            review = reviews.get(org.pk, {})
            issue = other.get(org.pk, {})
            rank = max(review.get("rank", 0), issue.get("rank", 0))
            item = {
                "id": org.pk,
                "name": org.name,
                "slug": org.slug,
                "level": LEVELS[rank],
                "rank": rank,
                "reviews": review.get("total", 0),
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
                unlocated.append(item)
                unlocated.sort(
                    key=lambda p: (-p["rank"], -p["reviews"] - p["issues"], p["name"].casefold(), p["id"])
                )
                del unlocated[50:]

    points = heapq.nsmallest(
        MAX_POINTS,
        markers(),
        key=lambda p: (-p["rank"], -p["reviews"] - p["issues"], p["name"].casefold(), p["id"]),
    )
    for item in [*points, *unlocated]:
        item.update(
            company_url=reverse("organization", args=[item["slug"]]),
            reviews_url=reverse("circl-findings") + "?organization=" + item["slug"],
            issues_url=reverse("issues") + "?organization=" + item["slug"] + "&state=map-open",
            location_url=reverse("circl-map-location", args=[item["slug"]])
            if item.pop("location_editable")
            else "",
        )
    summary["shown"] = len(points)
    summary["omitted"] = summary["located"] - len(points)
    return {"summary": summary, "points": points, "unlocated": unlocated, "limit": MAX_POINTS}
