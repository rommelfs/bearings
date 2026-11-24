"""Current scoped infrastructure state; missing evidence is never a clean bill of health."""

from dataclasses import dataclass
from functools import cached_property
from time import perf_counter
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When, Window
from django.db.models import QuerySet
from django.db.models.functions import RowNumber
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from .access import visible_findings_for
from .issues import FACT_FIELDS, visible_issues, active_filter
from django.conf import settings
from .inventory_presentation import grouped_address_filter, decorate_addresses, host_network_summary
from .overview_monitoring import package_reporters
from .models import (
    Asset,
    BusinessRiskRevision,
    Contact,
    Installation,
    ProductWatch,
    IssueRevision,
    IssueHistory,
)
from .notifications import contact_policy
from .presentation import ACTIVE_REVIEWS, SEVERITY_ORDER
from .overview_explanations import review_explanation


def reviews_for(user, *, include_cleared=False):
    from .review_queue import classified

    reviews = classified(
        visible_findings_for(user).filter(status__in=ACTIVE_REVIEWS, installation__asset__lifecycle="active")
    )
    return reviews if include_cleared else reviews.exclude(queue_bucket="cleared")


@dataclass(frozen=True)
class OverviewEvidence:
    """Lazy scoped querysets shared only within one overview request."""

    reviews: QuerySet
    issues: QuerySet
    all_reviews: QuerySet | None = None

    @classmethod
    def for_page(cls, user, orgs):
        ids = [org.pk for org in orgs]
        all_reviews = reviews_for(user, include_cleared=True).filter(organization_id__in=ids)
        return cls(
            all_reviews.exclude(queue_bucket="cleared"),
            visible_issues(user).filter(organization_id__in=ids),
            all_reviews,
        )

    @cached_property
    def review_totals(self):
        """One current classification pass, reused by company and asset counters.

        Retain aggregate bins only, never whole findings/proofs. This object lives
        for one scoped request; changed policy/inputs are read again next time.
        """
        companies, assets = {}, {}
        scope = self.all_reviews if self.all_reviews is not None else self.reviews
        bins = (
            scope.order_by()
            .values(
                "organization_id",
                "installation__asset_id",
                "queue_bucket",
                "package_current",
                "analyst_applicability",
                "record__source_severity",
                "distro_match__queue_proof__verdict",
            )
            .annotate(total=Count("pk"))
        )
        for row in bins:
            counts = companies.setdefault(row["organization_id"], _review_counts())
            total = row["total"]
            if row["package_current"] and row["distro_match__queue_proof__verdict"] == "affected":
                counts["automatic_affected"] += total
            if row["queue_bucket"] == "cleared":
                counts["review_cleared"] += total
                continue
            asset_counts = assets.setdefault(
                row["installation__asset_id"], {"reviews": 0, "affected": 0, "critical": 0}
            )
            counts["reviews"] += total
            asset_counts["reviews"] += total
            counts["review_" + row["queue_bucket"]] += total
            if row["analyst_applicability"] == "affected":
                counts["affected"] += total
                asset_counts["affected"] += total
            severity = row["record__source_severity"]
            if severity in {"critical", "high", "unknown"}:
                counts["unknown_severity" if severity == "unknown" else severity] += total
            if severity == "critical":
                asset_counts["critical"] += total
        return companies, assets

    @cached_property
    def active_issues(self):
        return (
            self.issues.filter(asset__lifecycle="active")
            .filter(active_filter())
            .exclude(finding__analyst_applicability="not_affected")
            .filter(
                Q(finding__isnull=True)
                | Exists(self.reviews.filter(pk=OuterRef("finding_id")))
                | Q(action_due__isnull=False)
                | ~Q(next_action="")
                | ~Q(consequence="")
                | ~Q(priority="review")
                | Exists(IssueRevision.objects.filter(issue_id=OuterRef("pk"), actor__isnull=False))
                | Exists(IssueHistory.objects.filter(issue_id=OuterRef("pk")))
            )
        )

    @cached_property
    def issue_totals(self):
        # Window counters and the four preview identities share one policy/proof
        # pass. Only four small rows per asset leave the database, not issue facts.
        companies, assets, previews = {}, {}, {}
        partition = [F("asset_id")]
        rows = (
            _ranked_issues(self.active_issues)
            .annotate(
                issues=Window(Count("pk"), partition_by=partition),
                overdue=Window(
                    Count("pk", filter=Q(action_due__lt=timezone.localdate())), partition_by=partition
                ),
                lifecycle=Window(
                    Count("pk", filter=Q(finding__isnull=True, priority__in=["critical", "high"])),
                    partition_by=partition,
                ),
            )
            .filter(position__lte=4)
            .order_by("asset_id", "position")
            .values("pk", "organization_id", "asset_id", "issues", "overdue", "lifecycle")
        )
        for row in rows:
            if row["asset_id"] not in assets:
                counts = companies.setdefault(row["organization_id"], {"issues": 0, "overdue": 0})
                for name in counts:
                    counts[name] += row[name]
                assets[row["asset_id"]] = {name: row[name] for name in ("overdue", "lifecycle")}
            previews.setdefault(row["asset_id"], []).append(row["pk"])
        return companies, assets, previews


def _severity_cases(prefix):
    return Case(
        *[When(**{prefix: value}, then=Value(index)) for index, value in enumerate(SEVERITY_ORDER)],
        default=Value(len(SEVERITY_ORDER)),
        output_field=IntegerField(),
    )


def _ranked_issues(issues):
    return issues.annotate(
        assessment_order=Case(
            When(finding__analyst_applicability="affected", then=Value(0)),
            When(finding__isnull=True, priority__in=["critical", "high"], then=Value(1)),
            When(finding__applicability="potential", then=Value(2)),
            When(finding__applicability="not_affected", then=Value(4)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        severity_order=_severity_cases("finding__record__source_severity"),
        urgent_order=Case(
            When(action_due__lt=timezone.localdate(), then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
    ).annotate(
        position=Window(
            expression=RowNumber(),
            partition_by=[F("asset_id")],
            order_by=[
                F("urgent_order").asc(),
                F("assessment_order").asc(),
                F("severity_order").asc(),
                F("action_due").asc(nulls_last=True),
                F("pk").asc(),
            ],
        )
    )


def _review_counts():
    return dict.fromkeys(
        [
            "reviews",
            "review_cleared",
            "affected",
            "review_action",
            "review_pending",
            "review_unresolved",
            "automatic_affected",
            "critical",
            "high",
            "unknown_severity",
        ],
        0,
    )


def company_states(user, orgs, *, evidence=None):
    """Aggregate once per visible page, without joining independent count dimensions."""
    ids = [org.pk for org in orgs]
    assets = Asset.objects.filter(
        organization_id__in=ids, source__organization_id=F("organization_id"), lifecycle="active"
    )
    installations = Installation.objects.filter(
        asset__in=assets, product__organization_id=F("asset__organization_id")
    )
    evidence = evidence or OverviewEvidence.for_page(user, orgs)
    visible = evidence.issues
    latest = (
        BusinessRiskRevision.objects.filter(issue_id=OuterRef("issue_id")).order_by("-pk").values("pk")[:1]
    )
    risks = BusinessRiskRevision.objects.filter(issue__organization_id__in=ids, pk=Subquery(latest)).filter(
        Exists(visible.filter(pk=OuterRef("issue_id")))
    )

    def grouped(qs, field="organization_id", **counts):
        return {row.pop(field): row for row in qs.order_by().values(field).annotate(**counts)}

    # Inventory has one asset -> installation hierarchy. Count it in one pass;
    # unrelated reviews/issues/contacts remain separate to avoid multiplication.
    owned_product = Q(installations__product__organization_id=F("organization_id"))
    package_product = owned_product & (
        Q(installations__product__identifier__startswith="pkg:deb/")
        | Q(installations__product__identifier__startswith="pkg:rpm/")
    )
    primary_asset = ~grouped_address_filter()
    asset_counts = grouped(
        assets,
        assets=Count("pk", distinct=True, filter=primary_asset),
        without_software=Count(
            "pk",
            distinct=True,
            filter=primary_asset & Q(installations__isnull=True) & ~Q(kind__in=("ip_address", "prefix")),
        ),
        missing_assets=Count("pk", distinct=True, filter=Q(missing_since__isnull=False)),
        unknown_versions=Count("installations", filter=owned_product & Q(installations__version="")),
        products=Count("installations__product_id", distinct=True, filter=owned_product),
        package_products=Count("installations__product_id", distinct=True, filter=package_product),
        # Define this alias last: it shares the reverse relation name used above.
        installations=Count("installations", filter=owned_product),
    )
    review_counts = evidence.review_totals[0]
    issue_counts = evidence.issue_totals[0]
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
    packages = package_reporters(ids)
    watches = {}
    for watch in (
        ProductWatch.objects.filter(product_id__in=installations.values("product_id"))
        .select_related("product")
        .only(
            "product__organization_id",
            "product__identifier",
            "enabled",
            "requested",
            "error",
            "last_success",
            "interval_minutes",
        )
    ):
        watches.setdefault(watch.product.organization_id, []).append(watch)
    return [
        _company_state(
            org,
            watches.get(org.pk, []),
            [
                counts.get(org.pk, {})
                for counts in [
                    asset_counts,
                    review_counts,
                    issue_counts,
                    risk_counts,
                    contact_counts,
                    packages,
                ]
            ],
        )
        for org in orgs
    ]


def _company_state(org, watches, counts):
    source = getattr(org, "inventory_source", None)
    policy = getattr(org, "inventory_review_policy", None) if source and source.mode == "manual" else None
    if source and source.mode == "manual":
        source_stale = not policy or not policy.last_reviewed_at or policy.next_due <= timezone.localdate()
    else:
        source_stale = (
            source is None
            or source.mode != "development"
            and (not source.instance_id or not source.instance.enabled or source.import_stale)
        )
    state = {
        "org": org,
        "configured": len(watches),
        "watch_count": len(watches),
        "package_matching_enabled": settings.DISTRO_CVE_ENABLED,
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
            "package_products",
            "package_clients",
            "package_queued",
            "package_unavailable",
            "package_errors",
            "package_uncertain",
            "reviews",
            "affected",
            "review_action",
            "review_pending",
            "review_unresolved",
            "automatic_affected",
            "review_cleared",
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
    state["legacy_products"] = state["products"] - state["package_products"]
    legacy_watches = sum(not w.product.identifier.startswith(("pkg:deb/", "pkg:rpm/")) for w in watches)
    state["configured"] = legacy_watches + state["package_products"]
    state["unmapped"] = max(0, state["legacy_products"] - legacy_watches)
    state.setdefault("package_last_attempt", None)
    state["package_gaps"] = bool(
        state["package_products"]
        and (
            not settings.DISTRO_CVE_ENABLED
            or not state["package_clients"]
            or state["package_queued"]
            or state["package_unavailable"]
            or state["package_uncertain"]
        )
    )
    state["coverage_gaps"] = bool(
        source_stale
        or not state["assets"]
        or state["unknown_versions"]
        or state["without_software"]
        or state["missing_assets"]
        or state["unmapped"]
        or state["package_gaps"]
        or state["paused"]
        or state["stale_watches"]
        or not state["response_contacts"]
    )
    if state["affected"] or state["overdue"] or state["expired_acceptance"]:
        state.update(status="Action required", tone="action")
    elif state["review_action"] or state["issues"]:
        state.update(status="Review required", tone="review")
    elif state["review_pending"]:
        state.update(status="Current evaluation pending", tone="incomplete")
    elif state["review_unresolved"]:
        state.update(status="Vendor clarification pending", tone="incomplete")
    elif not state["assets"]:
        state.update(status="No active inventory", tone="incomplete")
    elif state["coverage_gaps"]:
        state.update(status="Coverage incomplete", tone="incomplete")
    else:
        state.update(status="No open items recorded", tone="recorded")
    return state


def priority_assets(user, orgs, *, timings=None, evidence=None):
    timings = {} if timings is None else timings
    started = perf_counter()
    evidence = evidence or OverviewEvidence.for_page(user, orgs)
    reviews = evidence.reviews
    review_totals = evidence.review_totals[1]
    issue_totals = evidence.issue_totals[1]
    # Select the same bounded candidate sets from the already computed bins,
    # instead of running the correlated proof/policy predicates four more times.
    candidates = set(
        sorted(
            review_totals,
            key=lambda pk: (
                -review_totals[pk]["affected"],
                -review_totals[pk]["critical"],
                -review_totals[pk]["reviews"],
                pk,
            ),
        )[:12]
    )
    for name in ("overdue", "lifecycle"):
        candidates.update(
            sorted(
                (pk for pk, counts in issue_totals.items() if counts[name]),
                key=lambda pk: (-issue_totals[pk][name], pk),
            )[:12]
        )
    by_asset = {
        pk: {
            "affected": 0,
            "critical": 0,
            "reviews": 0,
            "overdue": 0,
            "lifecycle": 0,
            **review_totals.get(pk, {}),
            **issue_totals.get(pk, {}),
        }
        for pk in candidates
    }
    issues = evidence.active_issues
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

    ranked_rows = [
        {"pk": pk, "asset_id": asset_id}
        for asset_id in ids
        for pk in evidence.issue_totals[2].get(asset_id, [])
    ]
    # Scenario drafts require issue facts and the linked evidence, not the
    # organization's/source's entire inventory configuration and duplicate products.
    previews = (
        issues.filter(pk__in=[row["pk"] for row in ranked_rows])
        .select_related(None)
        .select_related("asset", "finding__record", "finding__installation__product")
        .only(
            *FACT_FIELDS,
            "asset_id",
            "installation_id",
            "finding_id",
            "asset__kind",
            "asset__criticality",
            "finding__status",
            "finding__analyst_applicability",
            "finding__applicability",
            "finding__rule",
            "finding__evaluated_at",
            "finding__record__source",
            "finding__record__source_severity",
            "finding__record__external_id",
            "finding__record__payload",
            "finding__installation__version",
            "finding__installation__build",
            "finding__installation__edition",
            "finding__installation__product__name",
            "finding__installation__product__identifier",
        )
    )
    shown_issues = {issue.pk: issue for issue in previews}
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
            assessment_order=Case(
                When(analyst_applicability="affected", then=Value(0)),
                When(applicability="potential", then=Value(1)),
                When(applicability="not_affected", then=Value(3)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            severity_order=_severity_cases("record__source_severity"),
            position=Window(
                expression=RowNumber(),
                partition_by=[F("installation__asset_id")],
                order_by=[
                    F("assessment_order").asc(),
                    F("severity_order").asc(),
                    F("pk").asc(),
                ],
            ),
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
    decorate_addresses(assets)
    result = []
    for asset in assets:
        row = {**by_asset[asset.pk], "asset": asset}
        row["context"] = host_network_summary(asset)

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
                "review": review_explanation(issue.finding) if issue.finding_id else None,
                "review_url": reverse("intelligence", args=[asset.organization.slug])
                + f"?finding={issue.finding_id}#finding-{issue.finding_id}"
                if issue.finding_id and not issue.next_action
                else "",
                "next_action": issue.next_action
                or (
                    review_explanation(issue.finding)["next_action"]
                    if issue.finding_id
                    else "Review the recorded issue evidence and assign the next action"
                ),
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
                    "review": review_explanation(finding),
                    "next_action": review_explanation(finding)["next_action"],
                }
            )
        row["actions"] = [problem["next_action"] for problem in row["problems"] if problem.get("next_action")]
        result.append(row)
    return result
