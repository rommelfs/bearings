"""Bounded, request-local package/feed associations; no network calls or upstream guessing."""

from collections import defaultdict
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
from . import agents, distro_cves, distro_sources, distro_results
from .access import visible_findings_for
from .models import AgentComponent, AgentReport, DistroFeed, DistroAdvisoryPackage


def decorate(user, products, installation_ids=None, finding_scope=None):
    products = {p.pk: p for p in products if p.distro_package}
    for p in products.values():
        p.distro_devices = []
    if not products:
        return
    # Five installations per displayed product, rather than five per-product queries.
    candidates = AgentComponent.objects.all()
    if installation_ids is not None:
        candidates = candidates.filter(installation_id__in=installation_ids)
    components = list(
        candidates.filter(
            installation__product_id__in=products,
            device__organization_id=F("installation__product__organization_id"),
            installation__asset__organization_id=F("device__organization_id"),
            device__source__organization_id=F("device__organization_id"),
            installation__asset_id=F("device__asset_id"),
            installation__asset__source_id=F("device__source_id"),
        )
        .annotate(
            position=Window(
                RowNumber(),
                partition_by=[F("installation__product_id")],
                order_by=[F("device_id").asc(), F("pk").asc()],
            )
        )
        .filter(position__lte=5 if installation_ids is None else len(installation_ids))
        .select_related("device__asset", "device__source", "device__organization", "installation")
        .defer("binary", "device__reported_network", "device__services", "device__asset__upstream_data")
        .order_by("installation__product_id", "device_id", "pk")
    )
    pending_reports = set(
        AgentReport.objects.filter(
            device_id__in={c.device_id for c in components}, status="pending"
        ).values_list("device_id", flat=True)
    )
    feeds = {
        f.key: f
        for f in DistroFeed.objects.filter(key__in={distro_sources.key_for(c.device.os) for c in components})
    }
    lookup = Q(pk__in=[])
    groups = defaultdict(set)
    for c in components:
        c.feed_key = distro_sources.key_for(c.device.os)
        c.vendor_feed = feeds.get(c.feed_key)
        c.lookup_name = (
            c.package_source.get("name", "") if (c.feed_key or "").startswith("debian:") else c.name
        )
        if c.vendor_feed and c.lookup_name:
            groups[(c.vendor_feed.pk, c.vendor_feed.generation, c.manager)].add(c.lookup_name)
    for (feed_id, generation, manager), names in groups.items():
        lookup |= Q(feed_id=feed_id, manager=manager, name__in=names, advisory__generation=generation)
    counts = {
        (r["feed_id"], r["manager"], r["name"]): r["total"]
        for r in DistroAdvisoryPackage.objects.filter(lookup)
        .values("feed_id", "manager", "name")
        .annotate(total=Count("advisory_id", distinct=True))
    }
    if finding_scope is None:
        finding_scope = visible_findings_for(user)
    reviews = {
        r["distro_match__component_id"]: r
        for r in finding_scope.filter(
            distro_match__component_id__in=[c.pk for c in components],
            installation_id=F("distro_match__component__installation_id"),
            organization_id=F("distro_match__component__device__organization_id"),
            record__organization_id=F("organization_id"),
        )
        .values("distro_match__component_id")
        .annotate(
            potential=Count("pk", filter=Q(distro_match__result="potential")),
            uncertain=Count("pk", filter=Q(distro_match__result="unknown")),
            retained=Count("pk"),
            human_pending=Count("pk", filter=Q(status__in=["new", "under_review", "confirmed"])),
        )
    }
    for c in components:
        c.vendor_source_url = distro_sources.url_for(c.feed_key) if c.feed_key else ""
        c.rule_count = counts.get((c.vendor_feed.pk, c.manager, c.lookup_name), 0) if c.vendor_feed else 0
        c.review_counts = reviews.get(
            c.pk, {"potential": 0, "uncertain": 0, "retained": 0, "human_pending": 0}
        )
        c.feed_status = distro_cves.feed_state(c.vendor_feed) if c.feed_key else "unsupported"
        c.package_status = (
            "Vendor rules linked" if c.rule_count else "No indexed vendor rules for this package"
        )
        if not c.feed_key:
            c.package_status = "Unsupported distribution/release"
        elif not c.lookup_name:
            c.package_status = "Source-package metadata missing; update the Linux client"
        elif c.feed_status != "ready":
            c.package_status = (
                "Vendor cache pending refresh" if c.feed_status == "pending" else "Vendor cache stale"
            )
        elif c.stale or c.missing_since or not agents.current(c.device):
            c.package_status = "Reported installation stale or unavailable"
        elif c.package_identity.get("distribution") != c.device.os.get("id") or c.package_identity.get(
            "release"
        ) != c.device.os.get("version"):
            c.package_status = "Package platform metadata changed; waiting for a fresh evaluation"
        c.evaluation_pending = (
            c.device.distro_requested
            or c.device_id in pending_reports
            or not c.device.distro_checked_at
            or (c.vendor_feed and str(c.vendor_feed.generation) != c.device.distro_summary.get("generation"))
        )
        c.identity_status = (
            "Recognized by vendor definitions" if c.rule_count else "Normalized package identity recorded"
        )
        metadata_current = c.package_identity.get("distribution") == c.device.os.get(
            "id"
        ) and c.package_identity.get("release") == c.device.os.get("version")
        if not settings.DISTRO_CVE_ENABLED:
            c.matching_status = "Disabled by platform configuration"
        elif (
            not c.feed_key
            or not c.lookup_name
            or not metadata_current
            or c.stale
            or c.missing_since
            or not agents.current(c.device)
        ):
            c.matching_status = c.package_status
        elif c.feed_status != "ready":
            c.matching_status = "Configured automatically; vendor cache refresh pending"
        elif c.device.distro_summary.get("state") == "error":
            c.matching_status = "Evaluation failed; retry required"
        elif c.evaluation_pending:
            c.matching_status = "Configured automatically; evaluation queued"
        elif not c.rule_count:
            c.matching_status = "Monitoring vendor feed; no indexed advisory for this identity yet"
        else:
            c.matching_status = "Ready — supported vendor advisories are checked automatically"
        receipt = c.distro_check
        c.result_checked_at = parse_datetime(receipt["checked_at"]) if receipt.get("checked_at") else None
        c.result_reported_at = parse_datetime(receipt["reported_at"]) if receipt.get("reported_at") else None
        c.result_vendor_at = (
            parse_datetime(receipt["vendor_data_at"]) if receipt.get("vendor_data_at") else None
        )
        c.check_current = bool(
            settings.DISTRO_CVE_ENABLED
            and c.feed_status == "ready"
            and not c.evaluation_pending
            and metadata_current
            and not c.stale
            and not c.missing_since
            and agents.current(c.device)
            and c.device.distro_summary.get("state") not in {"error", "unsupported", "pending", "stale"}
            and receipt.get("version") == distro_results.VERSION
            and receipt.get("generation") == str(c.vendor_feed.generation)
            and receipt.get("input_hash") == distro_results.inputs(c, c.device)
        )
        if not c.check_current:
            c.result_heading = "Current package result unavailable"
            if c.matching_status.startswith("Ready"):
                c.matching_status = "Configured automatically; package result pending reevaluation"
        else:
            counts = receipt["counts"]
            if counts["potential"] or counts["unknown"]:
                c.result_heading = "Review required"
            elif not receipt["rules_checked"]:
                c.result_heading = "No vendor rules indexed for this package yet"
            else:
                c.result_heading = "No package-rule alert in the evaluated results"
        products[c.installation.product_id].distro_devices.append(c)


def decorate_installations(user, installations):
    """Decorate only the displayed authorized installations, never a whole asset/fleet."""
    installations = list(installations)
    products = {}
    for installation in installations:
        product = installation.product
        product.distro_package = product.identifier.startswith(("pkg:deb/", "pkg:rpm/"))
        products[product.pk] = product
    # Each displayed installation needs its own status, even when a product occurs on >5 assets.
    for installation in installations:
        installation.distro_package = installation.product.distro_package
    finding_scope = visible_findings_for(user)
    decorate(
        user, products.values(), installation_ids=[i.pk for i in installations], finding_scope=finding_scope
    )
    components = {
        c.installation_id: c for p in products.values() if p.distro_package for c in p.distro_devices
    }
    # Callers select installations through an authorized asset and matching product
    # organization. Bind those concrete IDs to their concrete company again here:
    # joining the complete inventory into a grouped count can yield a catastrophic
    # nested-loop plan after a bulk import, even for a small displayed page.
    review_groups = defaultdict(list)
    for installation in installations:
        review_groups[installation.product.organization_id].append(installation.pk)
    review_scope = Q(pk__in=[])
    for org_id, ids in review_groups.items():
        review_scope |= Q(installation_id__in=ids, organization_id=org_id, record__organization_id=org_id)
    counts = dict(
        finding_scope.filter(review_scope)
        .values("installation_id")
        .annotate(total=Count("pk"))
        .values_list("installation_id", "total")
    )
    for installation in installations:
        installation.cve_component = components.get(installation.pk)
        installation.visible_review_count = counts.get(installation.pk, 0)
