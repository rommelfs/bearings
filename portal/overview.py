"""Current scoped infrastructure state; missing evidence is never a clean bill of health."""

from time import perf_counter
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When, Window
from django.db.models.functions import RowNumber
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from .access import visible_findings_for
from .issues import visible_issues, active_filter
from .models import Asset, BusinessRiskRevision, Contact, Installation, ProductWatch
from .notifications import contact_policy
from .presentation import ACTIVE_REVIEWS


def reviews_for(user):
    return (
        visible_findings_for(user)
        .filter(status__in=ACTIVE_REVIEWS, installation__asset__lifecycle="active")
        .exclude(analyst_applicability="not_affected")
    )


def company_states(user, orgs):
    """Aggregate once per visible page, without joining independent count dimensions."""
    ids = [org.pk for org in orgs]
    assets = Asset.objects.filter(
        organization_id__in=ids, source__organization_id=F("organization_id"), lifecycle="active"
    )
    installations = Installation.objects.filter(
        asset__in=assets, product__organization_id=F("asset__organization_id")
    )
    reviews = reviews_for(user).filter(organization_id__in=ids)
    visible = visible_issues(user).filter(organization_id__in=ids)
    issues = (
        visible.filter(asset__in=assets)
        .filter(active_filter())
        .exclude(finding__analyst_applicability="not_affected")
    )
    latest = (
        BusinessRiskRevision.objects.filter(issue_id=OuterRef("issue_id")).order_by("-pk").values("pk")[:1]
    )
    risks = BusinessRiskRevision.objects.filter(issue__in=visible, pk=Subquery(latest))

    def grouped(qs, field="organization_id", **counts):
        return {row.pop(field): row for row in qs.order_by().values(field).annotate(**counts)}

    asset_counts = grouped(
        assets,
        assets=Count("pk", distinct=True),
        without_software=Count("pk", distinct=True, filter=Q(installations__isnull=True)),
        missing_assets=Count("pk", distinct=True, filter=Q(missing_since__isnull=False)),
    )
    installation_counts = grouped(
        installations,
        "asset__organization_id",
        installations=Count("pk"),
        unknown_versions=Count("pk", filter=Q(version="")),
        products=Count("product_id", distinct=True),
    )
    review_counts = grouped(
        reviews,
        reviews=Count("pk"),
        affected=Count("pk", filter=Q(analyst_applicability="affected")),
        critical=Count("pk", filter=Q(record__source_severity="critical")),
        high=Count("pk", filter=Q(record__source_severity="high")),
        unknown_severity=Count("pk", filter=Q(record__source_severity="unknown")),
    )
    issue_counts = grouped(
        issues, issues=Count("pk"), overdue=Count("pk", filter=Q(action_due__lt=timezone.localdate()))
    )
    risk_counts = grouped(
        risks,
        "issue__organization_id",
        risk_assessments=Count("pk"),
        expired_acceptance=Count(
            "pk",
            filter=Q(
                snapshot__decision="accept", snapshot__acceptance_until__lt=timezone.localdate().isoformat()
            ),
        ),
    )
    contact_counts = grouped(
        Contact.objects.filter(organization_id__in=ids, **contact_policy()).exclude(function="dpo"),
        response_contacts=Count("pk"),
    )
    watches = {}
    for watch in ProductWatch.objects.filter(
        product_id__in=installations.values("product_id")
    ).select_related("product"):
        watches.setdefault(watch.product.organization_id, []).append(watch)
    return [
        _company_state(
            org,
            watches.get(org.pk, []),
            [
                counts.get(org.pk, {})
                for counts in [
                    asset_counts,
                    installation_counts,
                    review_counts,
                    issue_counts,
                    risk_counts,
                    contact_counts,
                ]
            ],
        )
        for org in orgs
    ]


def _company_state(org, watches, counts):
    source = getattr(org, "inventory_source", None)
    source_stale = (
        source is None
        or source.mode != "development"
        and (not source.instance_id or not source.instance.enabled or source.import_stale)
    )
    state = {
        "org": org,
        "configured": len(watches),
        "fresh": sum(w.enabled and not w.stale for w in watches),
        "paused": sum(not w.enabled for w in watches),
        "queued": sum(w.enabled and w.requested for w in watches),
        "watch_errors": sum(bool(w.error) for w in watches),
        "stale_watches": sum(w.enabled and w.stale for w in watches),
        "source_stale": source_stale,
        "synthetic": source is not None and source.mode == "development",
        "inventory_success": source.last_import_success if source else None,
        "last_cve_success": min(
            (w.last_success for w in watches if w.enabled and w.last_success), default=None
        ),
    }
    defaults = dict.fromkeys(
        [
            "assets",
            "without_software",
            "missing_assets",
            "installations",
            "unknown_versions",
            "products",
            "reviews",
            "affected",
            "critical",
            "high",
            "unknown_severity",
            "overdue",
            "issues",
            "risk_assessments",
            "expired_acceptance",
            "response_contacts",
        ],
        0,
    )
    for values in counts:
        defaults.update(values)
    state.update(defaults)
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


def priority_assets(user, orgs, *, timings=None):
    timings = {} if timings is None else timings
    started = perf_counter()
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
    ).select_related("organization", "responsible_contact", "source__instance")
    assets = sorted(
        assets,
        key=lambda asset: (
            -by_asset[asset.pk]["overdue"],
            -by_asset[asset.pk]["affected"],
            -by_asset[asset.pk]["lifecycle"],
            -by_asset[asset.pk]["critical"],
            -by_asset[asset.pk]["reviews"],
            asset.name,
        ),
    )[:12]
    ids = [asset.pk for asset in assets]
    ranked = perf_counter()
    timings["ranking"] = (ranked - started) * 1000
    ranked_issues = (
        issues.filter(asset_id__in=ids)
        .annotate(
            urgent_order=Case(
                When(action_due__lt=timezone.localdate(), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .annotate(
            position=Window(
                expression=RowNumber(),
                partition_by=[F("asset_id")],
                order_by=[F("urgent_order").asc(), F("action_due").asc(nulls_last=True), F("pk").asc()],
            )
        )
        .filter(position__lte=4)
        .order_by("asset_id", "position")
        .values("pk", "asset_id")
    )
    # Rank identifiers, then hydrate only the displayed rows. Joining all preview
    # relations into the window makes PostgreSQL plan/sort a much wider query.
    ranked_rows = list(ranked_issues)
    shown_issues = {issue.pk: issue for issue in issues.filter(pk__in=[row["pk"] for row in ranked_rows])}
    shown_by_asset = {}
    for row in ranked_rows:
        if issue := shown_issues.get(row["pk"]):
            shown_by_asset.setdefault(row["asset_id"], []).append(issue)
    previews = perf_counter()
    timings["issuepreviews"] = (previews - ranked) * 1000
    legacy_by_asset = {}
    needs_legacy = [asset.pk for asset in assets if len(shown_by_asset.get(asset.pk, [])) < 4]
    legacy = (
        reviews.filter(installation__asset_id__in=needs_legacy)
        .filter(~Exists(issues.filter(finding_id=OuterRef("pk"))))
        .annotate(
            position=Window(
                expression=RowNumber(), partition_by=[F("installation__asset_id")], order_by=F("pk").asc()
            )
        )
        .filter(position__lte=4)
        .order_by("installation__asset_id", "position")
        .values("pk", "installation__asset_id")
    )
    legacy_rows = list(legacy)
    legacy_findings = {
        finding.pk: finding for finding in reviews.filter(pk__in=[row["pk"] for row in legacy_rows])
    }
    for row in legacy_rows:
        if finding := legacy_findings.get(row["pk"]):
            legacy_by_asset.setdefault(row["installation__asset_id"], []).append(finding)
    timings["legacypreviews"] = (perf_counter() - previews) * 1000
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
        shown = shown_by_asset.get(asset.pk, [])
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
        for finding in legacy_by_asset.get(asset.pk, [])[: max(0, 4 - len(shown))]:
            row["problems"].append(
                {
                    "title": finding.record.external_id,
                    "kind": "Vulnerability",
                    "url": reverse("intelligence", args=[asset.organization.slug])
                    + f"?finding={finding.pk}#finding-{finding.pk}",
                    "next_action": "Review applicability and vendor fixes",
                }
            )
        row["actions"] = [problem["next_action"] for problem in row["problems"] if problem.get("next_action")]
        result.append(row)
    return result
