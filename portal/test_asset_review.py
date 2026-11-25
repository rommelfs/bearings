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
from .models import Asset, FindingHistory, Installation, Product, SourceRecord
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
        response = self.client.get(reverse("home"))
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
            self.assertEqual(
                self.client.get(reverse("home"), {"q": text}).context["review_page"].paginator.count, 1
            )
        self.assertEqual(
            self.client.get(reverse("home"), {"q": "absent.example.invalid"})
            .context["review_page"]
            .paginator.count,
            0,
        )

    def test_severity_order_filter_and_counts_are_global_not_per_page(self):
        for i in range(27):
            persist_lookup(self.admin, self.installation, "fixture://review", f"CVE-2026-{90000 + i}", {})
        critical = evidence()
        critical["containers"]["cna"]["metrics"][0]["cvssV3_1"]["baseScore"] = 9.8
        first = persist_lookup(self.admin, self.installation, "fixture://review", "CVE-2026-99999", critical)
        self.login()
        response = self.client.get(reverse("home"))
        self.assertEqual([f.pk for f in response.context["review_page"]][:2], [first.pk, self.finding.pk])
        self.assertEqual(response.context["review_total"], 29)
        high = self.client.get(reverse("home"), {"severity": "high"})
        self.assertEqual(high.context["review_page"].paginator.count, 1)
        counts = {v["key"]: v["count"] for v in high.context["severity_counts"]}
        self.assertEqual((counts["critical"], counts["high"], counts["unknown"]), (1, 1, 27))
        self.assertContains(self.client.get(reverse("home"), {"severity": "unknown"}), "Score missing")
        self.assertEqual(
            self.client.get(reverse("home"), {"severity": "critical"}).context["review_page"][0].pk, first.pk
        )

    def test_host_case_lists_distinct_software_and_keeps_scoped_evidence(self):
        identifier = self.finding.record.external_id
        duplicate = persist_lookup(
            self.admin, self.installation, "fixture://another-source", identifier.lower(), {}
        )
        duplicate.analyst_applicability = "not_affected"
        duplicate.save(update_fields=["analyst_applicability"])
        self.finding.analyst_applicability = "affected"
        self.finding.save(update_fields=["analyst_applicability"])
        other_version = Installation.objects.create(
            asset=self.asset, product=self.installation.product, version="2.0"
        )
        other_version_finding = persist_lookup(
            self.admin, other_version, "fixture://another-source", identifier, {}
        )
        product = Product.objects.create(organization=self.a, name="Second synthetic package")
        second_package = Installation.objects.create(asset=self.asset, product=product, version="3.0")
        second_finding = persist_lookup(
            self.admin, second_package, "fixture://another-source", identifier, {}
        )
        hidden_product = Product.objects.create(organization=self.a, name="Restricted synthetic package")
        hidden_installation = Installation.objects.create(asset=self.asset, product=hidden_product)
        hidden = persist_lookup(
            self.admin, hidden_installation, "fixture://restricted-source", identifier, {}
        )
        SourceRecord.objects.filter(pk=hidden.record_id).update(shareable=False)
        other_host = Asset.objects.create(organization=self.a, source=self.asset.source, name="another-host")
        remote = Installation.objects.create(asset=other_host, product=product)
        remote_finding = persist_lookup(self.admin, remote, "fixture://another-source", identifier, {})

        self.login(self.admin)
        response = self.client.get(reverse("home"), {"state": "all", "review_page": "999999999999"})
        host_case, remote_case = response.context["review_page"]
        self.assertEqual((host_case.pk, remote_case.pk), (self.finding.pk, remote_finding.pk))
        self.assertEqual(
            dict(host_case.software_preview),
            {
                self.installation.product.name: "action",
                product.name: "action",
            },
        )
        self.assertContains(response, "View software &amp; evidence (4)")
        self.assertContains(response, "Different saved assessments")
        self.assertNotContains(response, hidden_product.name)
        self.assertEqual(response.context["review_total"], 2)

        search = self.client.get(reverse("home"), {"q": "Second synthetic package"})
        self.assertEqual(search.context["review_total"], 2)
        self.assertEqual(search.context["review_page"][0].software_preview, host_case.software_preview)
        self.assertEqual(
            self.client.get(reverse("home"), {"q": hidden_product.name}).context["review_total"], 0
        )
        detail = self.client.get(reverse("review-evidence", args=[self.finding.pk]))
        self.assertEqual(
            {row["pk"] for row in detail.context["page"]},
            {self.finding.pk, duplicate.pk, other_version_finding.pk, second_finding.pk},
        )
        self.assertContains(detail, "2.0")
        self.assertContains(detail, product.name)
        self.assertNotContains(detail, "fixture://restricted-source")
        self.assertEqual(self.client.get(reverse("review-evidence", args=[hidden.pk])).status_code, 404)

    def test_intelligence_groups_a_host_cve_and_keeps_filtered_records_and_history(self):
        identifier = self.finding.record.external_id
        product = Product.objects.create(organization=self.a, name="Second intelligence package")
        installation = Installation.objects.create(asset=self.asset, product=product, version="3.0")
        second = persist_lookup(self.admin, installation, "fixture://secondary", identifier.lower(), {})
        second.status = "resolved"
        second.save(update_fields=["status"])
        hidden = persist_lookup(self.admin, self.installation, "fixture://restricted-source", identifier, {})
        SourceRecord.objects.filter(pk=hidden.record_id).update(shareable=False)

        self.login(self.reader)
        url = self.url("intelligence")
        scope = {"asset": str(self.asset.pk)}
        response = self.client.get(url, scope)
        (summary,) = response.context["page"]
        self.assertEqual(summary.evidence_count, 2)
        self.assertContains(response, "View software &amp; evidence (2)")
        self.assertContains(response, product.name)
        self.assertNotContains(response, 'id="assessment-')
        comparison = self.client.get(url + summary.case_url)
        self.assertEqual({row["pk"] for row in comparison.context["page"]}, {self.finding.pk, second.pk})
        self.assertContains(comparison, "resolved")
        self.assertContains(comparison, f"asset={self.asset.pk}")
        self.assertEqual(self.client.get(url, {"case": hidden.pk}).status_code, 404)
        self.assertContains(self.client.get(url, {"finding": second.pk}), f'id="assessment-{second.pk}"')
        self.assertEqual(self.client.get(self.url("api-intelligence")).json()["pagination"]["count"], 2)
        single = self.client.get(url, {"product": product.pk})
        self.assertContains(single, f'id="assessment-{second.pk}"')

    def test_host_case_limits_preview_and_preserves_all_evidence_in_details(self):
        for i in range(7):
            product = Product.objects.create(organization=self.a, name=f"Synthetic package {i}")
            installation = Installation.objects.create(asset=self.asset, product=product)
            persist_lookup(self.admin, installation, "fixture://package", self.finding.record.external_id, {})
        self.login()
        response = self.client.get(reverse("home"))
        (finding,) = response.context["review_page"]
        self.assertEqual(len(finding.software_preview), 6)
        self.assertEqual(finding.more_software, 2)
        detail = self.client.get(reverse("review-evidence", args=[finding.pk]))
        self.assertEqual(detail.context["page"].paginator.count, 8)

    def test_current_visibility_applies_to_search_counts_details_and_evidence(self):
        self.finding.record.shareable = False
        self.finding.record.save()
        self.login(self.admin)
        response = self.client.get(reverse("home"), {"q": "192.0.2.25"})
        self.assertEqual(response.context["review_total"], 0)
        page = self.client.get(self.url("asset", pk=self.asset.pk))
        self.assertContains(page, "192.0.2.25")
        self.assertNotContains(page, "CVE-2026-70571")
        self.assertEqual(page.context["page"].paginator.count, 0)
        self.login(self.analyst)
        self.assertContains(self.client.get(reverse("home")), "CVE-2026-70571")
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.url("asset", pk=self.asset.pk)).status_code, 404)
        self.assertEqual(self.client.get(reverse("home")).context["review_total"], 0)
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
        response = self.client.get(reverse("home"))
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


class CompanyFindingOrderTests(Fixture):
    def add_review(self, number, score=None, shareable=True):
        payload = (
            {}
            if score is None
            else {"containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": score}}]}}}
        )
        finding = persist_lookup(
            self.admin, self.installation, "fixture://severity-order", f"CVE-2026-{10000 + number}", payload
        )
        finding.record.shareable = shareable
        finding.record.save()
        return finding

    def test_company_asset_and_intelligence_put_critical_first_unknown_last(self):
        reviews = [self.add_review(i, score) for i, score in enumerate([None, 2.0, 5.0, 8.0, 10.0, 0.0])]
        expected = [reviews[i].pk for i in [4, 3, 2, 1, 5, 0]]
        self.login()
        company = self.client.get(self.url("organization"))
        self.assertEqual(company.context["finding_summary"]["total"], 6)
        self.assertNotContains(company, "CVE-2026-")
        for name, kwargs in [("asset", {"pk": self.asset.pk}), ("intelligence", {})]:
            response = self.client.get(self.url(name, **kwargs))
            self.assertEqual([f.pk for f in response.context["page"]], expected)

    def test_sorting_applies_before_pagination_and_preserves_evidence_visibility(self):
        critical = self.add_review(1, 10.0)
        restricted = self.add_review(2, 10.0, shareable=False)
        for i in range(3, 33):
            self.add_review(i)
        self.login(self.reader)
        for name, kwargs in [("asset", {"pk": self.asset.pk}), ("intelligence", {})]:
            response = self.client.get(self.url(name, **kwargs))
            self.assertEqual(response.context["page"][0].pk, critical.pk)
            self.assertEqual(response.context["page"].paginator.count, 31)
            self.assertNotIn(restricted.pk, [f.pk for f in response.context["page"]])
            second = self.client.get(self.url(name, **kwargs), {"page": 2})
            self.assertEqual(len(second.context["page"]), 6)
