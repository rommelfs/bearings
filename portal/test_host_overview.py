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
from .host_overview import HasVendorFix
from .models import Asset, AssetIssue, Finding, SourceRecord


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
        response = self.client.get(self.url("organization"), params)
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

    def test_private_intelligence_and_foreign_source_do_not_supply_priorities(self):
        self.cached()
        self.prepare()
        Finding.objects.update(status="confirmed")
        SourceRecord.objects.update(shareable=False, source_severity="critical")
        host = next(h for h in self.page().context["host_page"] if h.pk == self.device.asset_id)
        self.assertIsNone(host.source_priority)
        self.assertEqual(host.fix_packages, 0)
        self.login(self.platform)
        response = self.client.get(self.url("organization"))
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

    def test_timeout_has_retry_state_and_keeps_full_inventory(self):
        with patch("portal.host_overview.overview", side_effect=OperationalError("synthetic timeout")):
            self.login(self.reader)
            response = self.client.get(self.url("organization"))
        self.assertContains(response, "Host overview temporarily unavailable")
        self.assertContains(response, self.asset.name)
        self.assertNotContains(response, "0 matching hosts")

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
                    .annotate(fixed=HasVendorFix(F("payload")))
                    .values_list("fixed", flat=True)
                    .get()
                )
                self.assertEqual(actual, expected)

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
