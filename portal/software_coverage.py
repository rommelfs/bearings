"""Inventory accounting and bounded, currently visible version-rule evidence.

Mapping prerequisites are counted independently of CVE results. A mapping or an
empty advisory index never establishes full evaluation or a safe installation.
"""

from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Case, CharField, Count, F, OuterRef, Q, Subquery, Value, When, Window
from django.db.models.functions import RowNumber
from django.db.models.fields.json import KT
from django.urls import reverse
from django.utils import timezone

from .access import organizations_for, visible_findings_for
from .models import DiscoveryMatch, DiscoveryRevision, Installation
from .query_integrity import consistent

CATEGORIES = {
    "integrity": "Inventory link needs review",
    "retained": "Retained or unavailable observation",
    "version": "Version missing",
    "package": "Distribution package identity recorded",
    "mapped": "Product watch configured",
    "unmapped": "Product watch missing",
}


def inventory(user, org_ids=None):
    orgs = organizations_for(user)
    if org_ids is not None:
        orgs = orgs.filter(pk__in=org_ids)
    qs = Installation.objects.filter(asset__organization__in=orgs)
    qs = qs.annotate(
        coverage_integrity=consistent(
            product__organization_id=F("asset__organization_id"),
            asset__source__organization_id=F("asset__organization_id"),
        ),
        coverage_component_integrity=Case(
            When(agent_component__isnull=True, then=Value(True)),
            default=consistent(
                agent_component__device__organization_id=F("asset__organization_id"),
                agent_component__device__asset_id=F("asset_id"),
                agent_component__device__source_id=F("asset__source_id"),
                agent_component__last_report__device_id=F("agent_component__device_id"),
                agent_component__version=F("version"),
            ),
        ),
    )
    unavailable = ~Q(asset__lifecycle="active") | Q(asset__missing_since__isnull=False)
    unavailable |= Q(agent_component__isnull=False) & (
        Q(agent_component__missing_since__isnull=False)
        | Q(agent_component__device__enabled=False)
        | Q(agent_component__device__expires_at__lte=timezone.now())
        | Q(agent_component__observed_at__lt=timezone.now() - timedelta(hours=12))
        | Q(agent_component__device__last_observed_at__isnull=True)
        | Q(agent_component__device__last_observed_at__lt=timezone.now() - timedelta(hours=12))
        | ~Q(agent_component__device__last_sequence=F("agent_component__device__applied_sequence"))
        | ~Q(agent_component__last_report__status="applied")
    )
    package = Q(product__identifier__startswith="pkg:deb/") | Q(product__identifier__startswith="pkg:rpm/")
    return qs.annotate(
        coverage_category=Case(
            When(
                Q(coverage_integrity=False) | Q(coverage_component_integrity=False), then=Value("integrity")
            ),
            When(unavailable, then=Value("retained")),
            When(version="", then=Value("version")),
            When(package, then=Value("package")),
            When(
                Q(product__watch__isnull=False)
                & ~Q(product__watch__vendor="")
                & ~Q(product__watch__product_key=""),
                then=Value("mapped"),
            ),
            default=Value("unmapped"),
            output_field=CharField(),
        )
    )


def accounting(qs):
    """One disjoint category per retained installation, including invalid links."""
    groups = defaultdict(dict)
    for row in (
        qs.order_by().values("asset__organization_id", "coverage_category").annotate(total=Count("pk"))
    ):
        groups[row["asset__organization_id"]][row["coverage_category"]] = row["total"]
    return {
        org_id: {
            "total": sum(counts.values()),
            "categories": [
                {"key": key, "label": label, "count": counts.get(key, 0)} for key, label in CATEGORIES.items()
            ],
        }
        for org_id, counts in groups.items()
    }


def url(slug, **filters):
    return reverse("software-coverage", args=[slug]) + ("?" + urlencode(filters) if filters else "")


def decorate(user, installations):
    """Only hydrate a bounded displayed page; do not fetch vendor data or change decisions."""
    from . import discovery, windows_cves
    from .distro_display import decorate_installations
    from .intelligence import digest

    safe = [i for i in installations if i.coverage_integrity and i.coverage_component_integrity]
    decorate_installations(user, safe)
    scope = visible_findings_for(user).filter(
        installation_id__in=[i.pk for i in safe],
        organization_id=F("installation__asset__organization_id"),
        record__organization_id=F("organization_id"),
        installation__product__organization_id=F("organization_id"),
    )
    # Four samples prove neither absence nor complete coverage; count all visible
    # records separately and explicitly mark preview truncation on each row.
    counts = dict(
        scope.order_by()
        .values("installation_id")
        .annotate(total=Count("pk"))
        .values_list("installation_id", "total")
    )
    history = DiscoveryRevision.objects.filter(
        match_id=OuterRef("pk"), fingerprint=OuterRef("input_hash")
    ).annotate(saved_version=KT("snapshot__version"), saved_rule=KT("snapshot__windows__rule"))
    matches = defaultdict(list)
    for match in (
        DiscoveryMatch.objects.filter(
            finding__in=scope,
            watch__product_id=F("finding__installation__product_id"),
            evidence_revision__record_id=F("finding__record_id"),
        )
        .annotate(
            ledger_version=Subquery(history.values("saved_version")[:1]),
            ledger_windows_rule=Subquery(history.values("saved_rule")[:1]),
        )
        .annotate(
            position=Window(RowNumber(), partition_by=[F("finding__installation_id")], order_by=F("pk").asc())
        )
        .filter(position__lte=4)
        .select_related("finding__record", "watch", "evidence_revision")
        .defer("evidence_revision__payload")
    ):
        matches[match.finding.installation_id].append(match)
    for i in installations:
        i.coverage_label = CATEGORIES[i.coverage_category]
        i.coverage_reason = (
            "Inspect the recorded version and original evidence. A mapping is not an affectedness decision."
        )
        i.coverage_evidence = []
        i.coverage_reviews = counts.get(i.pk, 0)
        i.coverage_observed = None
        i.coverage_mapping = "Not established"
        i.coverage_product = (
            i.product.name
            if i.coverage_integrity and i.coverage_component_integrity
            else "Software identity unavailable"
        )
        i.coverage_identifier = (
            i.product.identifier if i.coverage_integrity and i.coverage_component_integrity else ""
        )
        i.coverage_next = "Inspect software identity and source ownership"
        if not i.coverage_integrity or not i.coverage_component_integrity:
            i.coverage_reason = "Inventory, product or observation links do not agree. Foreign source details and evidence are withheld."
            continue
        i.coverage_next = "Inspect version, mapping and evidence"
        component = getattr(i, "agent_component", None)
        if component:
            i.coverage_observed = component.observed_at
        if i.coverage_category == "retained":
            i.coverage_reason = "The host or observation is inactive, missing, stale, revoked, expired or awaiting application of its report. Obtain a current observation."
            continue
        if i.coverage_category == "version":
            i.coverage_reason = (
                "No installed version is recorded. Record a version before assessing affected-version rules."
            )
            continue
        if i.distro_package:
            c = i.cve_component
            i.coverage_mapping = i.product.identifier
            if not c:
                i.coverage_reason = (
                    "Package identity is recorded, but matching device metadata is unavailable."
                )
            elif not c.check_current:
                i.coverage_reason = c.matching_status
            elif not c.distro_check.get("rules_checked"):
                i.coverage_label = "No vendor rules indexed"
                i.coverage_reason = "The current feed contains no indexed rule for this package; absence of CVEs is not established."
            else:
                i.coverage_label = "Current supported package check recorded"
                if c.device.distro_summary.get("state") == "partial":
                    i.coverage_label = "Current package check; host coverage is partial"
                i.coverage_reason = c.matching_status
                i.coverage_checked = c.result_checked_at
            continue
        try:
            context = windows_cves.context(i)
        except (ValueError, KeyError, TypeError):
            i.coverage_label = "Windows observation proof unavailable"
            i.coverage_reason = "The retained observation cannot establish a current product identity. Review its source and collect a valid report."
            continue
        if context:
            i.coverage_mapping = context.get("cpe") or context.get("msrc_product") or "Not established"
            if context.get("gaps"):
                i.coverage_label = "Windows mapping evidence incomplete"
                i.coverage_reason = " ".join(context["gaps"])
                continue
        watch = getattr(i.product, "watch", None)
        if not watch:
            i.coverage_reason = "No explicit automatic product mapping is configured. A product name alone cannot establish applicability."
            continue
        i.coverage_mapping = f"{watch.vendor}/{watch.product_key}"
        if not watch.enabled:
            i.coverage_label, i.coverage_reason = (
                "Automatic checks paused",
                "The saved product watch is explicitly disabled.",
            )
            continue
        if watch.requested or watch.stale or not watch.last_attempt:
            i.coverage_label, i.coverage_reason = (
                "Current evaluation unavailable",
                "The product source needs a complete successful refresh or has stale/failed results.",
            )
            continue
        for match in matches[i.pk]:
            finding, record = match.finding, match.finding.record
            current = (
                match.ledger_version == i.version
                and match.watch_id == watch.pk
                and record.source.rstrip("/") == watch.source_url.rstrip("/")
                and record.ingested_at >= watch.last_attempt
                and match.evidence_revision.record_id == record.pk
                and match.evidence_revision.content_hash == digest(record.payload)
                and match.input_hash
                == digest(discovery.evaluation_inputs(watch, i, record.payload, windows=context))
            )
            i.coverage_evidence.append(
                {
                    "identifier": record.external_id,
                    "current": current,
                    "result": match.result if current else "Historical inputs; reevaluation required",
                    "label": {
                        "potential": "Affected-version rule matched; assess local applicability",
                        "unknown": "Vendor conditions unresolved",
                    }.get(match.result, "Recorded decision requires review")
                    if current
                    else "Historical inputs; reevaluation required",
                    "rule": discovery.RULE
                    + (" · " + match.ledger_windows_rule if match.ledger_windows_rule else ""),
                    "version": match.ledger_version or "Not retained in an evaluation snapshot",
                    "explanation": match.explanation[:2000],
                    "truncated": len(match.explanation) > 2000,
                    "checked_at": match.evaluated_at,
                    "analyst": finding.analyst_applicability,
                    "workflow": finding.status,
                    "url": reverse("intelligence", args=[i.asset.organization.slug])
                    + "?"
                    + urlencode({"finding": finding.pk, "installation": i.pk}),
                }
            )
        if not i.coverage_evidence:
            i.coverage_label = "No visible version-rule evidence"
            i.coverage_reason = "The mapping has no visible evaluation evidence for this installation. Empty results do not establish safety."
        elif not all(e["current"] for e in i.coverage_evidence):
            i.coverage_label = "Retained evidence needs reevaluation"
        else:
            i.coverage_label = (
                "Affected-version rule matched — assess local applicability"
                if any(e["result"] == "potential" for e in i.coverage_evidence)
                else "Vendor conditions unresolved"
            )
            i.coverage_reason = "Inspect the sampled rules and all reviews. Unsupported conditions and unlisted advisories remain coverage gaps. Saved analyst decisions are shown separately."


def observations(user, org_ids=None):
    """Unlinked reports are a separate inventory population, never silently omitted."""
    from django.db.models import DateTimeField
    from .models import AgentComponent

    orgs = organizations_for(user)
    if org_ids is not None:
        orgs = orgs.filter(pk__in=org_ids)
    return (
        AgentComponent.objects.filter(device__organization__in=orgs, installation__isnull=True)
        .annotate(
            coverage_integrity=consistent(
                device__asset__organization_id=F("device__organization_id"),
                device__source__organization_id=F("device__organization_id"),
                device__source_id=F("device__asset__source_id"),
                last_report__device_id=F("device_id"),
            ),
        )
        .annotate(
            coverage_name=Case(
                When(coverage_integrity=True, then=F("name")),
                default=Value("Observation identity unavailable"),
            ),
            coverage_version=Case(When(coverage_integrity=True, then=F("version")), default=Value("")),
            coverage_host=Case(
                When(coverage_integrity=True, then=F("device__asset__name")),
                default=Value("Host identity unavailable"),
            ),
            coverage_observed=Case(
                When(coverage_integrity=True, then=F("observed_at")),
                default=Value(None),
                output_field=DateTimeField(),
            ),
        )
    )


def observation_counts(user, org_ids):
    return dict(
        observations(user, org_ids)
        .order_by()
        .values("device__organization_id")
        .annotate(total=Count("pk"))
        .values_list("device__organization_id", "total")
    )
