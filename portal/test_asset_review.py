import copy
import importlib
from types import SimpleNamespace
from django.apps import apps
from django.db import connection
from django.test import Client
from django.urls import reverse
from .tests import Fixture
from . import test_inventory
from .test_exchange_example import evidence
from .asset_context import asset_context
from .connectors.http import ConnectorError
from .inventory import refresh_inventory
from .models import FindingHistory, SourceRecord
from .services import persist_lookup


class AssetContextImportTests(Fixture):
    setUp = test_inventory.InventoryImportTests.setUp
    response = test_inventory.InventoryImportTests.response
    imported = test_inventory.InventoryImportTests.imported

    def context_records(self):
        self.records["devices"][0].update(
            {
                "primary_ip4": {"id": 3, "address": "192.0.2.25/24", "url": "https://evil.invalid/"},
                "primary_ip6": {"id": 4, "address": "2001:db8::25/64"},
                "site": {"id": 1, "name": "Luxembourg DC"},
                "location": {"id": 2, "name": "Messaging room M1"},
                "rack": {"id": 5, "name": "EX-01", "url": "javascript:bad"},
                "position": 22.0,
                "face": {"value": "front"},
                "platform": {"id": 8, "name": "Windows"},
                "serial": "fixture-serial",
                "asset_tag": "fixture-tag",
            }
        )
        self.records["ip-addresses"] = [
            {
                "id": 3,
                "address": "192.0.2.25/24",
                "dns_name": "mail.example.invalid",
                "vrf": {"id": 8, "name": "Production"},
            },
            {"id": 4, "address": "2001:db8::25/64", "dns_name": "mail.example.invalid"},
            {
                "id": 9,
                "address": "192.0.2.25/24",
                "dns_name": "wrong-vrf.example.invalid",
                "vrf": {"id": 5, "name": "Other"},
            },
        ]

    def test_primary_dns_location_and_links_use_complete_source_local_identity(self):
        self.context_records()
        refresh_inventory(self.sa.pk)
        asset = self.imported()
        context = asset_context(asset)
        self.assertEqual(
            context["dns_names"],
            [{"name": "mail.example.invalid", "url": "https://alpha.example.invalid/ipam/ip-addresses/3/"}],
        )
        self.assertEqual([a["address"] for a in context["addresses"]], ["192.0.2.25", "2001:db8::25"])
        self.assertEqual(context["position"], "22")
        self.assertEqual(context["addresses"][0]["vrf"]["url"], "https://alpha.example.invalid/ipam/vrfs/8/")
        self.assertEqual(context["rack"]["url"], "https://alpha.example.invalid/dcim/racks/5/")
        self.assertEqual(context["site"]["name"], "Luxembourg DC")
        self.assertNotIn("wrong-vrf", str(context))
        self.assertNotIn("evil.invalid", str(context))
        self.assertNotIn("javascript:", str(context))
        self.assertTrue(all(c.args[0] == "GET" for c in self.http.call_args_list))

    def test_address_without_matching_primary_id_does_not_infer_dns(self):
        self.context_records()
        self.records["devices"][0]["primary_ip4"]["id"] = 99
        self.records["devices"][0].pop("primary_ip6")
        refresh_inventory(self.sa.pk)
        self.assertEqual(asset_context(self.imported())["dns_names"], [])
        self.assertEqual(asset_context(self.imported())["addresses"][0]["address"], "192.0.2.25")

    def test_invalid_placement_or_ip_family_preserves_complete_previous_snapshot(self):
        self.context_records()
        refresh_inventory(self.sa.pk)
        previous = self.imported().upstream_data
        valid = copy.deepcopy(self.records)
        for field, value in [
            ("rack", {"id": "5", "name": "invalid"}),
            ("position", "NaN"),
            ("primary_ip4", {"id": 3, "address": "2001:db8::25/64"}),
        ]:
            with self.subTest(field=field):
                self.records = copy.deepcopy(valid)
                self.records["devices"][0][field] = value
                with self.assertRaises(ConnectorError):
                    refresh_inventory(self.sa.pk)
                self.assertEqual(self.imported().upstream_data, previous)


class AssetReviewTests(Fixture):
    def setUp(self):
        self.asset.upstream_data = {
            "site": {"id": 1, "name": "Luxembourg DC"},
            "rack": {"id": 2, "name": "EX-01"},
            "location": {"id": 3, "name": "Messaging room M1"},
            "position": "22",
            "primary_ip4": "192.0.2.25/24",
            "primary_ip4_id": 5,
            "primary_ip4_dns_name": "mail.example.invalid",
        }
        self.asset.responsible_team = "Messaging team"
        self.asset.save()
        self.finding = persist_lookup(
            self.admin, self.installation, "fixture://review", "CVE-2026-70571", evidence()
        )

    def test_dashboard_locates_machine_and_links_entities_to_scoped_details(self):
        self.login(self.analyst)
        response = self.client.get("/")
        for text in [
            "192.0.2.25",
            "mail.example.invalid",
            "Luxembourg DC",
            "EX-01",
            "U22",
            'class="review-cue severity-high"',
        ]:
            self.assertContains(response, text)
        self.assertContains(response, reverse("asset", kwargs={"slug": self.a.slug, "pk": self.asset.pk}))
        for text in [
            "192.0.2.25",
            "mail.example.invalid",
            "Luxembourg",
            "EX-01",
            "Messaging",
            "CVE-2026-70571",
        ]:
            self.assertEqual(self.client.get("/", {"q": text}).context["review_page"].paginator.count, 1)
        self.assertEqual(
            self.client.get("/", {"q": "absent.example.invalid"}).context["review_page"].paginator.count, 0
        )

    def test_severity_order_filter_and_counts_are_global_not_per_page(self):
        for i in range(27):
            persist_lookup(self.admin, self.installation, "fixture://review", f"CVE-2026-{90000 + i}", {})
        critical = evidence()
        critical["containers"]["cna"]["metrics"][0]["cvssV3_1"]["baseScore"] = 9.8
        first = persist_lookup(self.admin, self.installation, "fixture://review", "CVE-2026-99999", critical)
        self.login()
        response = self.client.get("/")
        self.assertEqual([f.pk for f in response.context["review_page"]][:2], [first.pk, self.finding.pk])
        self.assertEqual(response.context["review_total"], 29)
        high = self.client.get("/", {"severity": "high"})
        self.assertEqual(high.context["review_page"].paginator.count, 1)
        counts = {v["key"]: v["count"] for v in high.context["severity_counts"]}
        self.assertEqual((counts["critical"], counts["high"], counts["unknown"]), (1, 1, 27))
        self.assertContains(self.client.get("/", {"severity": "unknown"}), "Score missing")
        self.assertEqual(
            self.client.get("/", {"severity": "critical"}).context["review_page"][0].pk, first.pk
        )

    def test_current_visibility_applies_to_search_counts_details_and_evidence(self):
        self.finding.record.shareable = False
        self.finding.record.save()
        self.login(self.admin)
        response = self.client.get("/", {"q": "192.0.2.25"})
        self.assertEqual(response.context["review_total"], 0)
        page = self.client.get(self.url("asset", pk=self.asset.pk))
        self.assertContains(page, "192.0.2.25")
        self.assertNotContains(page, "CVE-2026-70571")
        self.assertEqual(page.context["page"].paginator.count, 0)
        self.login(self.analyst)
        self.assertContains(self.client.get("/"), "CVE-2026-70571")
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.url("asset", pk=self.asset.pk)).status_code, 404)
        self.assertEqual(self.client.get("/").context["review_total"], 0)
        self.login(self.admin)
        self.assertEqual(self.client.get(self.url("asset", self.b, pk=self.asset.pk)).status_code, 404)

    def test_local_edit_is_scoped_csrf_protected_and_does_not_change_inventory_facts(self):
        url = self.url("edit-local-asset", pk=self.asset.pk)
        self.login(self.reader)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login(self.analyst)
        self.assertEqual(self.client.post(url, {"responsible_team": "changed"}).status_code, 403)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url, {}).status_code, 403)
        self.login(self.admin)
        original = self.asset.upstream_data
        self.assertEqual(
            self.client.post(
                url,
                {
                    "criticality": "high",
                    "lifecycle": "active",
                    "responsible_team": "Incident team",
                    "name": "must-not-change",
                    "upstream_data": "{}",
                },
            ).status_code,
            302,
        )
        self.asset.refresh_from_db()
        self.assertEqual((self.asset.name, self.asset.upstream_data), ("alpha-secret", original))
        self.assertEqual(self.asset.responsible_team, "Incident team")
        self.assertEqual(self.asset.criticality, "high")

    def test_source_cache_refresh_and_backfill_preserve_policy_and_assessments(self):
        record = self.finding.record
        self.assertEqual(record.source_severity, "high")
        record.shareable = False
        record.save(update_fields=["shareable"])
        SourceRecord.objects.filter(pk=record.pk).update(source_severity="unknown")
        migration = importlib.import_module("portal.migrations.0009_sourcerecord_source_severity")
        migration.backfill(apps, SimpleNamespace(connection=connection))
        record.refresh_from_db()
        self.assertEqual(record.source_severity, "high")
        self.assertFalse(record.shareable)
        payload = evidence()
        payload["containers"]["cna"]["metrics"][0]["cvssV3_1"]["baseScore"] = "invalid"
        persist_lookup(self.admin, self.installation, record.source, record.external_id, payload)
        record.refresh_from_db()
        self.assertEqual(record.source_severity, "unknown")
        self.assertFalse(record.shareable)
        self.assertFalse(FindingHistory.objects.filter(finding=self.finding).exists())

    def test_new_context_and_search_text_are_escaped_missing_data_not_fabricated(self):
        self.asset.upstream_data["site"]["name"] = '<script>alert("site")</script>'
        self.asset.upstream_data["primary_ip4_dns_name"] = "<img src=x onerror=alert(1)>"
        self.asset.save()
        self.login()
        response = self.client.get("/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("site")</script>')
        self.assertNotContains(response, "<img src=x onerror=alert(1)>")
        self.asset.upstream_data = {}
        self.asset.name = "inventory-name-is-not-dns.example.invalid"
        self.asset.save()
        context = asset_context(self.asset)
        self.assertEqual((context["dns_names"], context["addresses"]), ([], []))
        self.assertContains(self.client.get(self.url("asset", pk=self.asset.pk)), "Not recorded")

    def test_assessment_action_returns_to_exact_finding_and_keeps_role_checks(self):
        self.login(self.analyst)
        url = self.url("finding-review", pk=self.finding.pk) + "?return=intelligence"
        response = self.client.post(
            url,
            {
                "status": "under_review",
                "assessment": "potential",
                "reason": "Verify version and exposure first",
            },
        )
        expected = self.url("intelligence") + f"?finding={self.finding.pk}#finding-{self.finding.pk}"
        self.assertRedirects(response, expected)
