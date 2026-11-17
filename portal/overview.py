"""Current scoped infrastructure state; missing evidence is never a clean bill of health."""

from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from .access import visible_findings_for
from .issues import visible_issues, active_filter
from .models import Asset, BusinessRiskRevision, Installation, Product, ProductWatch
from .notifications import contact_policy
from .presentation import ACTIVE_REVIEWS


def reviews_for(user):
    return (
        visible_findings_for(user)
        .filter(status__in=ACTIVE_REVIEWS, installation__asset__lifecycle="active")
        .exclude(analyst_applicability="not_affected")
    )


def company_state(user, org):
    assets = Asset.objects.filter(organization=org, source__organization=org, lifecycle="active")
    installations = Installation.objects.filter(asset__in=assets, product__organization=org)
    products = Product.objects.filter(installation__in=installations).distinct()
    watches = list(ProductWatch.objects.filter(product__in=products))
    reviews = reviews_for(user).filter(organization=org)
    issues = (
        visible_issues(user)
        .filter(organization=org, asset__in=assets)
        .filter(active_filter())
        .exclude(finding__analyst_applicability="not_affected")
    )
    latest = (
        BusinessRiskRevision.objects.filter(issue_id=OuterRef("issue_id")).values("pk").order_by("-pk")[:1]
    )
    risks = BusinessRiskRevision.objects.filter(
        issue__in=visible_issues(user).filter(organization=org), pk=Subquery(latest)
    )
    source = getattr(org, "inventory_source", None)
    source_stale = (
        source is None
        or source.mode != "development"
        and (not source.instance_id or not source.instance.enabled or source.import_stale)
    )
    state = {
        "org": org,
        "assets": assets.count(),
        "without_software": assets.filter(installations__isnull=True).count(),
        "missing_assets": assets.filter(missing_since__isnull=False).count(),
        "installations": installations.count(),
        "unknown_versions": installations.filter(version="").count(),
        "products": products.count(),
        "configured": len(watches),
        "fresh": sum(w.enabled and not w.stale for w in watches),
        "paused": sum(not w.enabled for w in watches),
        "queued": sum(w.enabled and w.requested for w in watches),
        "watch_errors": sum(bool(w.error) for w in watches),
        "stale_watches": sum(w.enabled and w.stale for w in watches),
        "reviews": reviews.count(),
        "affected": reviews.filter(analyst_applicability="affected").count(),
        "critical": reviews.filter(record__source_severity="critical").count(),
        "high": reviews.filter(record__source_severity="high").count(),
        "unknown_severity": reviews.filter(record__source_severity="unknown").count(),
        "overdue": issues.filter(action_due__lt=timezone.localdate()).count(),
        "issues": issues.count(),
        "risk_assessments": risks.count(),
        "expired_acceptance": risks.filter(
            snapshot__decision="accept", snapshot__acceptance_until__lt=timezone.localdate().isoformat()
        ).count(),
        "response_contacts": org.contacts.filter(**contact_policy()).exclude(function="dpo").count(),
        "source_stale": source_stale,
        "synthetic": source is not None and source.mode == "development",
        "inventory_success": source.last_import_success if source else None,
        "last_cve_success": min(
            (w.last_success for w in watches if w.enabled and w.last_success), default=None
        ),
    }
    state["unmapped"] = state["products"] - state["configured"]
    state["coverage_gaps"] = bool(
        source_stale
        or not state["assets"]
        or state["unknown_versions"]
        or state["without_software"]
        or state["missing_assets"]
        or state["unmapped"]
        or state["paused"]
        or state["stale_watches"]
        or not state["response_contacts"]
    )
    if state["affected"] or state["overdue"] or state["expired_acceptance"]:
        state.update(status="Action required", tone="action")
    elif state["reviews"] or state["issues"]:
        state.update(status="Review required", tone="review")
    elif state["coverage_gaps"]:
        state.update(status="Coverage incomplete", tone="incomplete")
    else:
        state.update(status="No open items recorded", tone="recorded")
    return state


def priority_assets(user, orgs):
    reviews = reviews_for(user).filter(organization__in=orgs)
    rows = list(
        reviews.values("installation__asset_id")
        .annotate(
            affected=Count("pk", filter=Q(analyst_applicability="affected")),
            critical=Count("pk", filter=Q(record__source_severity="critical")),
            reviews=Count("pk"),
        )
        .order_by("-affected", "-critical", "-reviews", "installation__asset_id")[:12]
    )
    by_asset = {
        row["installation__asset_id"]: {
            "affected": row["affected"],
            "critical": row["critical"],
            "reviews": row["reviews"],
            "overdue": 0,
            "lifecycle": 0,
        }
        for row in rows
    }
    issues = (
        visible_issues(user)
        .filter(organization__in=orgs, asset__lifecycle="active")
        .filter(active_filter())
        .exclude(finding__analyst_applicability="not_affected")
    )
    for row in (
        issues.filter(action_due__lt=timezone.localdate())
        .values("asset_id")
        .annotate(overdue=Count("pk"))
        .order_by("-overdue", "asset_id")[:12]
    ):
        values = by_asset.setdefault(
            row["asset_id"], {"affected": 0, "critical": 0, "reviews": 0, "overdue": 0, "lifecycle": 0}
        )
        values["overdue"] = row["overdue"]
    for row in (
        issues.filter(finding__isnull=True, priority__in=["critical", "high"])
        .values("asset_id")
        .annotate(total=Count("pk"))
        .order_by("-total", "asset_id")[:12]
    ):
        values = by_asset.setdefault(
            row["asset_id"], {"affected": 0, "critical": 0, "reviews": 0, "overdue": 0, "lifecycle": 0}
        )
        values["lifecycle"] = row["total"]
    # Candidate selection is bounded, but every displayed badge uses the full scoped asset set.
    for counts in (
        reviews.filter(installation__asset_id__in=by_asset)
        .values("installation__asset_id")
        .annotate(
            reviews=Count("pk"),
            affected=Count("pk", filter=Q(analyst_applicability="affected")),
            critical=Count("pk", filter=Q(record__source_severity="critical")),
        )
    ):
        by_asset[counts.pop("installation__asset_id")].update(counts)
    for counts in (
        issues.filter(asset_id__in=by_asset)
        .values("asset_id")
        .annotate(
            overdue=Count("pk", filter=Q(action_due__lt=timezone.localdate())),
            lifecycle=Count("pk", filter=Q(finding__isnull=True, priority__in=["critical", "high"])),
        )
    ):
        by_asset[counts.pop("asset_id")].update(counts)
    assets = Asset.objects.filter(
        pk__in=by_asset, organization__in=orgs, source__organization_id=F("organization_id")
    ).select_related("organization", "responsible_contact")
    result = []
    for asset in assets:
        from .asset_context import asset_context

        row = {**by_asset[asset.pk], "asset": asset}
        row["context"] = asset_context(asset)

        def problem_list_url(attention):
            return (
                reverse("issues")
                + "?"
                + urlencode(
                    {"organization": asset.organization.slug, "asset": str(asset.pk), "attention": attention}
                )
            )

        row["links"] = {
            key: problem_list_url(key) for key in ["all", "overdue", "affected", "critical", "lifecycle"]
        }
        for attention in ["reviews", "affected", "critical"]:
            row["links"][attention] = (
                reverse("intelligence", args=[asset.organization.slug])
                + "?"
                + urlencode({"asset": str(asset.pk), "attention": attention})
            )
        asset_issues = issues.filter(asset=asset)
        shown = list(
            asset_issues.annotate(
                urgent_order=Case(
                    When(action_due__lt=timezone.localdate(), then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("urgent_order", F("action_due").asc(nulls_last=True), "pk")[:4]
        )
        from .scenario_suggestions import draft_scenario

        row["problems"] = [
            {
                "title": issue.title,
                "kind": issue.get_kind_display(),
                "url": reverse("issue", args=[asset.organization.slug, issue.pk]),
                "due": issue.action_due,
                "next_action": issue.next_action,
                "scenario": draft_scenario(issue),
                "scenario_url": reverse("automatic-scenario", args=[asset.organization.slug, issue.pk]),
            }
            for issue in shown
        ]
        # Old findings may predate the common issue model; keep an exact CVE deep link.
        for finding in (
            reviews.filter(installation__asset=asset)
            .exclude(pk__in=asset_issues.values("finding_id").filter(finding_id__isnull=False))
            .order_by("pk")[: max(0, 4 - len(shown))]
        ):
            row["problems"].append(
                {
                    "title": finding.record.external_id,
                    "kind": "Vulnerability",
                    "url": reverse("intelligence", args=[asset.organization.slug])
                    + f"?finding={finding.pk}#finding-{finding.pk}",
                    "next_action": "Review applicability and vendor fixes",
                }
            )
        row["problem_count"] = asset_issues.count()
        row["actions"] = [problem["next_action"] for problem in row["problems"] if problem.get("next_action")]
        result.append(row)
    return sorted(
        result,
        key=lambda row: (
            -row["overdue"],
            -row["affected"],
            -row["lifecycle"],
            -row["critical"],
            -row["reviews"],
            row["asset"].name,
        ),
    )[:12]
