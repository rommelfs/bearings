"""Host summaries keep version evidence, scope, gaps and installability distinct."""

import copy
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from django.db.models import F
from django.db import OperationalError
from django.utils import timezone
from unittest.mock import patch
from .tests import Fixture
from . import test_ubuntu_status as fixture
from .distro_fix_evidence import HasVendorFix
from .distro_projection import DistroVendorFixInputsV1
from .models import Asset, AssetIssue, DistroMatch, Finding, SourceRecord


class HostOverviewTests(Fixture):
    legacy_manual_projection = False
    setUp = fixture.UbuntuStatusTests.setUp
    post = fixture.UbuntuStatusTests.post
    enroll = fixture.UbuntuStatusTests.enroll
    data = fixture.UbuntuStatusTests.data
    send = fixture.UbuntuStatusTests.send
    load = fixture.UbuntuStatusTests.load
    cached = fixture.UbuntuStatusTests.cached
    prepare = fixture.UbuntuStatusTests.prepare

    def page(self, **params):
        self.login(self.reader)
        response = self.client.get(self.url("organization-hosts"), params)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("host_overview_unavailable", response.context)
        return response

    def test_current_distinct_package_fix_and_stale_invalidation(self):
        self.cached()
        self.prepare()
        response = self.page()
        host = next(h for h in response.context["host_page"] if h.pk == self.device.asset_id)
        self.assertEqual(host.affected_packages, 1)
        self.assertEqual(host.fix_packages, 1)
        self.assertEqual(response.context["host_stats"]["fixes"], 1)
        self.assertIn("dbmax;dur=", response["Server-Timing"])
        with patch("portal.host_overview.MAX_GROUPED_PACKAGE_HOSTS", 0):
            fallback = self.page()
        old_host = next(h for h in fallback.context["host_page"] if h.pk == self.device.asset_id)
        self.assertEqual((old_host.affected_packages, old_host.fix_packages), (1, 1))
        self.assertEqual(response.context["host_stats"], fallback.context["host_stats"])
        self.assertContains(response, "Repository updates: not checked")
        self.assertContains(response, "Fixed version explicitly documented")
        # A second advisory/record for the same installation never multiplies packages.
        original = Finding.objects.get()
        duplicate = copy.copy(original)
        duplicate.pk = None
        record = SourceRecord.objects.create(
            organization=self.a,
            source="fixture://host-overview",
            external_id="CVE-2099-123456",
            shareable=True,
            payload={},
        )
        duplicate.record = record
        duplicate.rule = "manual-copy"
        duplicate.save()
        self.assertEqual(self.page().context["host_stats"]["fixes"], 1)
        self.device.expires_at = timezone.now() - timedelta(minutes=1)
        self.device.save(update_fields=["expires_at"])
        response = self.page()
        self.assertEqual(response.context["host_stats"]["fixes"], 0)
        host = next(h for h in response.context["host_page"] if h.pk == self.device.asset_id)
        self.assertIsNone(host.fix_packages)
        self.assertIsNone(host.source_priority)
        self.assertNotEqual(host.priority_tone, "clear")

    def test_linux_asset_prioritizes_current_fix_and_excludes_private_or_stale_evidence(self):
        from .test_package_verdicts import save_browser_evidence

        self.cached()
        self.prepare()
        self.login(self.reader)
        url = self.url("asset", pk=self.device.asset_id)
        page = self.client.get(url)
        self.assertContains(page, "1 package with documented vendor fixes")
        self.assertContains(page, "Repository update availability has not been checked")
        self.assertContains(page, "1 package with current affected-version matches")
        self.assertContains(page, 'aria-label="Reports received.')
        save_browser_evidence("asset-attention-linux", page)
        SourceRecord.objects.update(shareable=False)
        page = self.client.get(url)
        self.assertNotContains(page, "package with documented vendor fixes")
        self.assertNotContains(page, "1 package with current affected-version matches")
        SourceRecord.objects.update(shareable=True)
        self.device.expires_at = timezone.now() - timedelta(minutes=1)
        self.device.save(update_fields=["expires_at"])
        page = self.client.get(url)
        self.assertContains(page, "Update backlog unknown")
        self.assertNotContains(page, "current affected package-version match")

    def test_private_intelligence_and_foreign_source_do_not_supply_priorities(self):
        self.cached()
        self.prepare()
        Finding.objects.update(status="confirmed")
        SourceRecord.objects.update(shareable=False, source_severity="critical")
        host = next(h for h in self.page().context["host_page"] if h.pk == self.device.asset_id)
        self.assertIsNone(host.source_priority)
        self.assertEqual(host.fix_packages, 0)
        self.login(self.platform)
        response = self.client.get(self.url("organization-hosts"))
        host = next(h for h in response.context["host_page"] if h.pk == self.device.asset_id)
        self.assertEqual(host.source_priority, 0)
        bad = Asset.objects.create(
            organization=self.a, source=self.sb, name="cross-source-secret", kind="server"
        )
        self.assertNotIn(bad.pk, [h.pk for h in self.page().context["host_page"]])
        self.assertEqual(self.client.get(self.url("organization", self.b)).status_code, 404)

    def test_sort_filter_and_pagination_use_full_cohort_and_keep_context(self):
        self.cached()
        self.prepare()
        Asset.objects.filter(pk=self.device.asset_id).update(name="ZZZ critical")
        SourceRecord.objects.update(source_severity="critical")
        for index in range(28):
            Asset.objects.create(organization=self.a, source=self.sa, name=f"AAA {index:02}", kind="server")
        r = self.page(host_filter="all", host_q="", contact_page="2")
        self.assertEqual(r.context["host_page"][0].pk, self.device.asset_id)
        self.assertEqual(len(r.context["host_page"]), 25)
        params = parse_qs(urlsplit(r.context["host_next_url"]).query)
        self.assertEqual(params["host_filter"], ["all"])
        self.assertEqual(params["contact_page"], ["2"])
        self.assertEqual(params["page"], ["2"])
        filtered = self.page(host_filter="fixes")
        self.assertEqual(filtered.context["host_page"].paginator.count, 1)
        for key in ["host", "priority", "coverage", "fixes", "observed"]:
            for direction in ["asc", "desc"]:
                self.assertEqual(self.page(sort=key, direction=direction).context["host_sort_key"], key)
        self.assertEqual(self.page(sort="host", direction="asc").context["host_page"][0].name, "AAA 00")
        self.assertEqual(self.page(host_q="ZZZ").context["host_stats"]["total"], 1)
        for params in [{"host_filter": "bad"}, {"sort": "bad"}, {"direction": "bad"}]:
            self.assertEqual(self.client.get(self.url("organization"), params).status_code, 400)

    def test_issue_priority_and_missing_mapping_remain_explicit(self):
        AssetIssue.objects.create(
            organization=self.a,
            asset=self.asset,
            kind="support",
            title="Synthetic expired support",
            priority="critical",
        )
        response = self.page(host_filter="attention")
        host = next(h for h in response.context["host_page"] if h.pk == self.asset.pk)
        self.assertEqual(host.priority_label, "Critical")
        self.assertEqual(host.priority_origin, "asset issue")
        self.assertIsNone(host.fix_packages)
        self.assertGreater(host.mapping_gaps, 0)
        self.assertContains(response, "discovery / version gaps")
        # Private standalone lifecycle issues cannot leak into participant rows.
        AssetIssue.objects.update(operator_only=True)
        host = next(h for h in self.page().context["host_page"] if h.pk == self.asset.pk)
        self.assertEqual(host.issue_count, 0)
        self.assertIsNone(host.host_priority)

    def test_inventory_is_independent_of_host_overview_and_fragment_stays_scoped(self):
        self.login(self.reader)
        with patch(
            "portal.host_overview.overview", side_effect=OperationalError("synthetic timeout")
        ) as overview:
            document = self.client.get(self.url("organization"))
            self.assertContains(document, self.asset.name)
            self.assertContains(document, "data-host-panel=")
            self.assertContains(document, "Host inventory preview")
            self.assertEqual(
                [row["pk"] for row in document.context["host_inventory_preview"]], [self.asset.pk]
            )
            self.assertNotContains(document, self.other.name)
            self.assertNotContains(document, "0 matching hosts")
            self.assertIn("company;dur=", document["Server-Timing"])
            overview.assert_not_called()
            panel = self.client.get(self.url("organization-hosts"))
            self.assertContains(panel, "CVE assessment temporarily unavailable", status_code=503)
            self.assertContains(panel, "Retry CVE assessment", status_code=503)
            self.assertContains(panel, self.asset.name, status_code=503)
            self.assertNotContains(panel, "0 matching hosts", status_code=503)
            self.assertNotContains(panel, self.other.name, status_code=503)
            self.assertIn("hosts;dur=", panel["Server-Timing"])
            self.assertIn("dbmax;dur=", panel["Server-Timing"])
            self.assertEqual(panel["X-Bearings-Host-Error"], "database")
            self.assertIn("no-store", panel["Cache-Control"])
            self.assertEqual(self.client.get(self.url("organization-hosts", self.b)).status_code, 404)
            overview.assert_called_once()
            inline = self.client.get(self.url("organization"), {"host_filter": "fixes", "host_q": "alpha"})
            self.assertContains(inline, "CVE assessment temporarily unavailable")
            self.assertContains(inline, "?host_filter=fixes&amp;host_q=alpha#hosts")
            self.assertEqual([row["pk"] for row in inline.context["host_inventory_preview"]], [self.asset.pk])
        self.client.logout()
        self.assertEqual(self.client.get(self.url("organization-hosts")).status_code, 302)

    def test_vendor_fix_contract_matches_exact_bound_and_ignores_malformed_evidence(self):
        row = SourceRecord.objects.create(
            organization=self.a, source="fixture://host-fix", external_id="fixture-fix", payload={}
        )
        good = {
            "comparisons": [{"vendor_version": "1.2", "operation": "less than", "matches": True}],
            "vendor_comments": ["This issue has been fixed (note: '1.2') in security/main"],
        }
        cases = [
            (good, True),
            ({**good, "vendor_comments": ["has been fixed (note: '9.9')"]}, False),
            ({**good, "comparisons": [{**good["comparisons"][0], "matches": "true"}]}, False),
            ({**good, "comparisons": ["not an object", None]}, False),
            ({**good, "vendor_comments": {"invalid": "array"}}, False),
            ({}, False),
        ]
        for proof, expected in cases:
            with self.subTest(proof=proof):
                SourceRecord.objects.filter(pk=row.pk).update(payload={"package_check": proof})
                actual = (
                    SourceRecord.objects.filter(pk=row.pk)
                    .annotate(
                        fixed=HasVendorFix(F("payload")),
                        projected=HasVendorFix(DistroVendorFixInputsV1(F("payload"))),
                    )
                    .values_list("fixed", "projected")
                    .get()
                )
                self.assertEqual(actual, (expected, expected))

    def test_bulk_snapshot_update_recomputes_vendor_fix_without_losing_affectedness(self):
        self.cached()
        self.prepare()
        match = DistroMatch.objects.get()
        snapshot = copy.deepcopy(match.snapshot)
        snapshot["package_check"].pop("vendor_comments")
        DistroMatch.objects.filter(pk=match.pk).update(snapshot=snapshot)
        response = self.page(host_filter="affected")
        host = response.context["host_page"][0]
        self.assertEqual(host.affected_packages, 1)
        self.assertEqual(host.fix_packages, 0)
        self.assertEqual(response.context["host_stats"]["fixes"], 0)
        match.refresh_from_db()
        self.assertIsNone(match.vendor_fix_inputs["package_check"]["vendor_comments"])

    def test_analyst_read_snapshot_rechecks_revocation_on_the_next_request(self):
        from django.contrib.auth.models import Group
        from .access import ANALYST_GROUP
        from .models import Membership

        self.a.operator_visibility = True
        self.a.save(update_fields=["operator_visibility"])
        Membership.objects.filter(user=self.analyst, organization=self.a).delete()
        self.login(self.analyst)
        self.assertEqual(self.client.get(self.url("organization")).status_code, 200)
        self.analyst.groups.remove(Group.objects.get(name=ANALYST_GROUP))
        self.assertEqual(self.client.get(self.url("organization")).status_code, 404)

    def test_application_discovery_freshness_is_separate_from_no_cve_matches(self):
        from .models import ProductWatch

        self.installation.version = "1.2.3"
        self.installation.save(update_fields=["version"])
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="fixture",
            product_key="fixture",
            source_url="https://example.invalid",
            enabled=True,
            requested=False,
            last_success=timezone.now(),
            interval_minutes=60,
        )
        host = next(h for h in self.page().context["host_page"] if h.pk == self.asset.pk)
        self.assertEqual(host.mapping_gaps, 0)
        for changes in [
            {"requested": True},
            {"error": "synthetic timeout"},
            {"enabled": False},
            {"last_success": timezone.now() - timedelta(hours=3)},
        ]:
            with self.subTest(changes=changes):
                ProductWatch.objects.filter(pk=watch.pk).update(
                    requested=False, error="", enabled=True, last_success=timezone.now()
                )
                ProductWatch.objects.filter(pk=watch.pk).update(**changes)
                host = next(h for h in self.page().context["host_page"] if h.pk == self.asset.pk)
                self.assertEqual(host.mapping_gaps, 1)
                self.assertNotEqual(host.priority_tone, "clear")

    def test_host_filters_survive_asset_and_evidence_round_trips(self):
        from html.parser import HTMLParser

        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    self.urls.append(dict(attrs).get("href", ""))

        self.cached()
        self.prepare()
        filters = {
            "host_filter": "affected",
            "host_q": "alpha",
            "sort": "fixes",
            "direction": "desc",
            "page": "1",
        }
        r = self.page(**filters)
        parser = Links()
        parser.feed(r.content.decode())
        for prefix in ["/organizations/alpha/intelligence/?asset=", "/organizations/alpha/assets/"]:
            link = next(url for url in parser.urls if url.startswith(prefix) and "return_to=" in url)
            response = self.client.get(link)
            self.assertEqual(response.status_code, 200)
            target = response.context["queue_return_url"]
            self.assertEqual(urlsplit(target).path, self.url("organization"))
            self.assertEqual(
                parse_qs(urlsplit(target).query), {key: [value] for key, value in filters.items()}
            )
            self.assertContains(response, "Back to filtered list")
