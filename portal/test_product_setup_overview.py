"""Company setup should work without knowing catalog keys or interpreting an empty queue as safe."""

import copy
from datetime import timedelta
from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from django.core.management import call_command
from django.test.utils import CaptureQueriesContext
from django.test import Client
from django.test import TransactionTestCase
from django.db import connection, connections, close_old_connections
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import AssetIssue, AuditEvent, Membership, Product, ProductWatch
from .product_matching import ensure_watch, enroll_products, suggestions
from .connectors.http import ConnectorError
from .connectors.vulnerability_lookup import browse_products
from .issues import ensure_vulnerability_issue


class ProductSetupTests(Fixture):
    def setUp(self):
        self.login()

    def test_known_products_are_prefilled_with_auto_refresh_without_get_side_effects(self):
        for name, expected in [
            ("Apache Log4j", ("apache", "log4j")),
            ("Microsoft Exchange Server", ("microsoft", "exchange_server")),
            ("Fortinet FortiOS", ("fortinet", "fortios")),
        ]:
            self.product.name, self.product.identifier = name, "demo:product:0"
            self.product.save()
            with patch("portal.discovery_views.browse_products") as remote:
                response = self.client.get(self.url("discovery-configure", pk=self.product.pk))
                remote.assert_not_called()
            self.assertEqual(response.context["form"]["vendor"].value(), expected[0])
            self.assertEqual(response.context["form"]["product_key"].value(), expected[1])
            self.assertTrue(response.context["form"]["enabled"].value())
            self.assertContains(response, "Product recognized")
            self.assertFalse(ProductWatch.objects.exists())

    def test_cpe_and_package_mapping_are_concrete_and_names_do_not_fuzzily_guess(self):
        self.product.identifier = "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*"
        self.assertEqual(suggestions(self.product)[0]["vendor"], "example")
        self.product.identifier = "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"
        self.assertEqual(suggestions(self.product)[0]["product_key"], "log4j")
        for identifier in [
            "cpe:2.3:a:*:server:*:*:*:*:*:*:*:*",
            "cpe:2.3:a:evil/host:server:*:*:*:*:*:*:*:*",
            "demo:product:0",
        ]:
            self.product.identifier, self.product.name = identifier, "Apache Log4j-like internal service"
            self.assertEqual(suggestions(self.product), [])

    def test_conflicting_name_and_cpe_require_selection_and_stay_unenrolled(self):
        self.product.name = "Apache Log4j"
        self.product.identifier = "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*"
        self.product.save()
        self.assertEqual(ensure_watch(self.product), (None, False))
        response = self.client.get(self.url("discovery-configure", pk=self.product.pk))
        self.assertContains(response, "different identities")
        self.assertEqual(len(response.context["suggestions"]), 2)
        self.assertEqual(response.context["form"]["vendor"].value(), "")

    def test_automatic_enrollment_is_active_idempotent_and_preserves_explicit_pause(self):
        self.product.name = "Apache Log4j"
        self.product.save()
        self.assertEqual(enroll_products(), 1)
        watch = ProductWatch.objects.get(product=self.product)
        self.assertTrue(watch.enabled and watch.requested)
        self.assertEqual((watch.vendor, watch.product_key), ("apache", "log4j"))
        self.assertTrue(
            AuditEvent.objects.filter(
                organization=self.a, action="vulnerability.watch_auto_configured"
            ).exists()
        )
        watch.enabled, watch.vendor, watch.product_key = False, "custom", "custom_key"
        watch.save()
        self.assertEqual(enroll_products(), 0)
        self.assertEqual(ensure_watch(self.product)[1], False)
        response = self.client.get(self.url("discovery-configure", pk=self.product.pk))
        self.assertEqual(response.context["form"]["vendor"].value(), "custom")
        self.assertFalse(response.context["form"]["enabled"].value())

    def test_creating_a_known_software_installation_immediately_enables_its_watch(self):
        response = self.client.post(
            self.url("create-installation", pk=self.asset.pk),
            {"product_name": "Apache Log4j", "version": "2.14.1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProductWatch.objects.get(product__name="Apache Log4j").enabled)

    def test_native_worker_enrolls_existing_recognized_products_before_discovery(self):
        self.product.name = "Apache Log4j"
        self.product.save()
        with patch("portal.management.commands.sync_vulnerabilities.sync_watch") as remote:
            call_command("sync_vulnerabilities", due=True)
        watch = ProductWatch.objects.get()
        remote.assert_called_once_with(watch.pk, due=True)

    def test_invalid_post_keeps_entered_values_instead_of_reapplying_suggestion(self):
        self.product.name = "Apache Log4j"
        self.product.save()
        response = self.client.post(
            self.url("discovery-configure", pk=self.product.pk),
            {"vendor": "custom", "product_key": "entered", "enabled": "on", "interval_minutes": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["vendor"].value(), "custom")
        self.assertFalse(ProductWatch.objects.exists())

    def test_catalog_search_is_scoped_post_csrf_and_read_only(self):
        url = self.url("discovery-catalog-search", pk=self.product.pk)
        with patch(
            "portal.discovery_views.browse_products", return_value={"results": [{"key": "apache"}]}
        ) as remote:
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(
                self.client.post(url, {"kind": "vendors", "q": "apache"}).json()["results"][0]["key"],
                "apache",
            )
            self.assertEqual(remote.call_count, 1)
            self.login(self.reader)
            self.assertEqual(self.client.post(url, {"kind": "vendors"}).status_code, 403)
            self.assertEqual(remote.call_count, 1)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url, {"kind": "vendors"}).status_code, 403)
        self.assertFalse(ProductWatch.objects.exists())

    @patch("portal.discovery_views.browse_products")
    def test_foreign_product_search_denied_before_upstream_call(self, remote):
        foreign = Product.objects.create(organization=self.b, name="Foreign product")
        self.assertEqual(
            self.client.post(self.url("discovery-catalog-search", pk=foreign.pk), {}).status_code, 404
        )
        remote.assert_not_called()

    @patch("portal.discovery_views.browse_products")
    def test_search_preserves_pinned_source_and_failure_leaves_saved_settings(self, remote):
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="old",
            product_key="product",
            source_url="https://catalog.example.invalid",
        )
        url = self.url("discovery-catalog-search", pk=self.product.pk)
        remote.side_effect = ConnectorError("private upstream detail")
        response = self.client.post(url, {"kind": "products", "vendor": "old", "q": "new"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("private upstream detail", response.content.decode())
        self.assertEqual(remote.call_args.args[0], watch.source_url)
        watch.refresh_from_db()
        self.assertEqual((watch.vendor, watch.product_key), ("old", "product"))

    def test_catalog_contract_bounds_url_escaping_and_partial_failures(self):
        sample = {
            "metadata": {"count": 1, "page": 1, "per_page": 20},
            "data": [{"name": "apache log4j", "last_change": None}],
        }
        with (
            patch(
                "portal.connectors.vulnerability_lookup.approved_base",
                return_value="https://vulnerability.circl.lu",
            ),
            patch("portal.connectors.vulnerability_lookup.request_json", return_value=sample) as remote,
        ):
            result = browse_products(
                "https://vulnerability.circl.lu",
                kind="products",
                vendor="apache software foundation",
                query="log4j",
            )
            self.assertEqual(result["results"], [{"key": "apache log4j"}])
            self.assertIn("apache%20software%20foundation/products", remote.call_args.args[1])
            self.assertEqual(remote.call_args.kwargs["params"], {"q": "log4j", "page": 1, "per_page": 20})
            invalid = copy.deepcopy(sample)
            invalid["metadata"]["count"] = 10
            remote.return_value = invalid
            with self.assertRaises(ConnectorError):
                browse_products("https://vulnerability.circl.lu", kind="vendors")
            for vendor in ["../evil", "https://evil.invalid", "a\nb"]:
                with self.assertRaises(ConnectorError):
                    browse_products("https://vulnerability.circl.lu", kind="products", vendor=vendor)
            with self.assertRaises(ConnectorError):
                browse_products("https://vulnerability.circl.lu", kind="vendors", page=101)


class InfrastructureOverviewTests(Fixture):
    def test_overview_query_budget_stays_bounded_across_twelve_companies(self):
        from .models import Asset, InventorySource, Organization

        def add_issue(org, source, name):
            asset = Asset.objects.create(organization=org, source=source, name=name, kind="server")
            AssetIssue.objects.create(
                organization=org,
                asset=asset,
                kind="eol",
                priority="high",
                title=f"Upgrade {name}",
                next_action="Test vendor update",
            )

        add_issue(self.a, self.sa, "first")
        self.login()
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get("/").status_code, 200)
        for number in range(11):
            org = Organization.objects.create(name=f"Company {number}", slug=f"performance-{number}")
            source = InventorySource.objects.create(organization=org, mode="development")
            Membership.objects.create(organization=org, user=self.admin, role="admin")
            for asset_number in range(3):
                add_issue(org, source, f"server-{number}-{asset_number}")
        with CaptureQueriesContext(connection) as large:
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["companies"]), 12)
        self.assertEqual(len(response.context["priority_assets"]), 12)
        self.assertLessEqual(len(large), len(small) + 2)
        self.assertLessEqual(len(large), 45)  # PostgreSQL adds local JIT settings/savepoint bookkeeping.
        for row in response.context["priority_assets"]:
            self.assertEqual(row["lifecycle"], 1)
            self.assertEqual(len(row["problems"]), 1)
            self.assertEqual(row["problems"][0]["scenario"]["profile"], "support")

    def test_twelve_cve_previews_keep_full_scenarios_without_per_preview_queries(self):
        from .models import Asset, Finding, Installation
        from .issues import visible_issues
        from .scenario_suggestions import draft_scenario

        finding = self.record_finding()
        finding.record.payload = {
            "containers": {
                "cna": {"descriptions": [{"lang": "en", "value": "Synthetic remote code execution"}]}
            }
        }
        finding.record.save()
        finding.analyst_applicability = "affected"
        finding.save()
        issue = ensure_vulnerability_issue(finding)
        for number in range(11):
            asset = Asset.objects.create(
                organization=self.a, source=self.sa, name=f"CVE server {number}", kind="server"
            )
            installation = Installation.objects.create(
                asset=asset,
                product=self.product,
                version="1.2.3",
                build="synthetic-build",
                edition="synthetic-edition",
            )
            another = Finding.objects.create(
                organization=self.a,
                installation=installation,
                record=finding.record,
                analyst_applicability="affected",
                explanation="Synthetic evidence",
            )
            ensure_vulnerability_issue(another)
        self.login()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/")
        self.assertEqual(len(response.context["priority_assets"]), 12)
        self.assertLessEqual(len(queries), 40)
        for row in response.context["priority_assets"]:
            scenario = row["problems"][0]["scenario"]
            self.assertEqual(scenario["profile"], "execution")
            self.assertTrue(scenario["fingerprint"])
        original = next(
            row for row in response.context["priority_assets"] if row["asset"].pk == self.asset.pk
        )
        self.assertEqual(
            original["problems"][0]["scenario"], draft_scenario(visible_issues(self.admin).get(pk=issue.pk))
        )

    def test_inventory_counts_do_not_multiply_versions_or_include_retired_and_foreign_sources(self):
        from .models import Asset, Installation

        self.asset.missing_since = timezone.now()
        self.asset.save()
        for number in range(5):
            Installation.objects.create(asset=self.asset, product=self.product, version=str(number))
        Asset.objects.create(organization=self.a, source=self.sa, name="No software")
        Asset.objects.create(organization=self.a, source=self.sa, name="Retired", lifecycle="retired")
        Asset.objects.create(organization=self.a, source=self.sb, name="Wrong source")
        self.login()
        state = self.client.get("/").context["companies"][0]
        self.assertEqual((state["assets"], state["without_software"], state["missing_assets"]), (2, 1, 1))
        self.assertEqual((state["installations"], state["products"], state["unknown_versions"]), (6, 1, 1))

    def test_bulk_counts_keep_product_identity_and_latest_visible_risk_revision(self):
        from .models import Asset, Installation, BusinessRiskRevision

        another = Asset.objects.create(organization=self.a, source=self.sa, name="Second server")
        Installation.objects.create(asset=another, product=self.product, version="1.0")
        ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="server",
            source_url="https://vulnerability.circl.lu",
            last_success=timezone.now(),
        )
        visible = ensure_vulnerability_issue(self.record_finding())
        visible.finding.record.external_id = "CVE-2026-00001"
        visible.finding.record.save()
        hidden = ensure_vulnerability_issue(self.record_finding(shareable=False))
        expired = {
            "decision": "accept",
            "acceptance_until": (timezone.localdate() - timedelta(days=1)).isoformat(),
        }
        for issue in [visible, hidden]:
            BusinessRiskRevision.objects.create(
                issue=issue, actor=self.admin, snapshot=expired, evidence_hash="synthetic"
            )
        BusinessRiskRevision.objects.create(
            issue=visible, actor=self.admin, snapshot={"decision": "mitigate"}, evidence_hash="synthetic"
        )
        self.login()
        state = self.client.get("/").context["companies"][0]
        self.assertEqual((state["assets"], state["installations"], state["unknown_versions"]), (2, 2, 1))
        self.assertEqual((state["products"], state["configured"], state["fresh"]), (1, 1, 1))
        self.assertEqual((state["risk_assessments"], state["expired_acceptance"]), (1, 0))
        self.login(self.analyst)
        state = self.client.get("/").context["companies"][0]
        self.assertEqual((state["risk_assessments"], state["expired_acceptance"]), (2, 1))

    def test_problem_limit_and_deadline_order_apply_to_each_asset(self):
        from .models import Asset

        second = Asset.objects.create(organization=self.a, source=self.sa, name="Second server")
        expected = {}
        for asset in [self.asset, second]:
            issues = []
            for offset in [None, 2, -1, -3, -2, 1]:
                issues.append(
                    AssetIssue.objects.create(
                        organization=self.a,
                        asset=asset,
                        kind="eol",
                        title=f"Lifecycle {offset}",
                        priority="high",
                        action_due=None if offset is None else timezone.localdate() + timedelta(days=offset),
                    )
                )
            expected[asset.pk] = [issues[index].title for index in [3, 4, 2, 5]]
        self.login()
        for row in self.client.get("/").context["priority_assets"]:
            self.assertEqual([problem["title"] for problem in row["problems"]], expected[row["asset"].pk])
            self.assertEqual(row["lifecycle"], 6)
            self.assertEqual(row["overdue"], 3)

    def test_high_priority_lifecycle_issue_is_visible_before_its_deadline(self):
        AssetIssue.objects.create(
            organization=self.a,
            asset=self.asset,
            kind="eol",
            title="Unsupported operating system",
            priority="high",
            source_label="Synthetic lifecycle evidence",
            evidence_text="Vendor support ended",
            next_action="Upgrade the server operating system",
            action_due=timezone.localdate() + timedelta(days=7),
        )
        self.login()
        response = self.client.get("/")
        self.assertContains(response, "Upgrade the server operating system")
        self.assertEqual(response.context["priority_assets"][0]["lifecycle"], 1)

    def test_root_is_scoped_landing_page_with_default_refresh_and_no_get_mutations(self):
        self.login()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Infrastructure overview")
        timing = response.headers["Server-Timing"]
        self.assertTrue(timing.startswith("overview;dur="))
        self.assertGreaterEqual(float(timing.split(",", 1)[0].split("=", 1)[1]), 0)
        self.assertContains(response, "data-overview-refresh checked")
        self.assertEqual([s["org"].pk for s in response.context["companies"]], [self.a.pk])
        self.assertNotContains(response, self.b.name)
        self.assertTrue(response.context["companies"][0]["coverage_gaps"])
        self.assertFalse(ProductWatch.objects.exists())
        self.assertEqual(reverse("home"), "/reviews/")
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_anonymous_and_foreign_company_selection_do_not_expose_data(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.login()
        self.assertEqual(self.client.get("/", {"organization": self.b.slug}).status_code, 404)
        self.assertEqual(self.client.get("/", {"q": self.b.name}).context["page"].paginator.count, 0)

    def test_restricted_evidence_does_not_leak_through_status_counts_or_asset_queue(self):
        finding = self.record_finding(shareable=False)
        finding.record.payload = {"containers": {"cna": {"metrics": [{"cvssV3_1": {"baseScore": 10.0}}]}}}
        finding.record.save()
        finding.analyst_applicability = "affected"
        finding.save()
        ensure_vulnerability_issue(finding)
        self.login(self.reader)
        response = self.client.get("/")
        state = response.context["companies"][0]
        self.assertEqual((state["reviews"], state["affected"], state["critical"]), (0, 0, 0))
        self.assertEqual(response.context["priority_assets"], [])
        self.login(self.analyst)
        response = self.client.get("/")
        self.assertEqual(response.context["companies"][0]["affected"], 1)
        self.assertEqual(response.context["companies"][0]["status"], "Action required")
        self.assertTrue(AuditEvent.objects.filter(actor=self.analyst, action="operator.access").exists())
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get("/").context["companies"], [])

    def test_overdue_remediation_and_unknown_versions_show_concrete_next_actions(self):
        finding = self.record_finding()
        issue = ensure_vulnerability_issue(finding)
        issue.action_due = timezone.localdate() - timedelta(days=1)
        issue.next_action = "Install tested vendor update"
        issue.save()
        self.login()
        response = self.client.get("/")
        self.assertContains(response, "Install tested vendor update")
        self.assertEqual(response.context["companies"][0]["overdue"], 1)
        self.assertEqual(response.context["companies"][0]["unknown_versions"], 1)
        self.assertEqual(response.context["companies"][0]["unmapped"], 1)
        self.assertNotContains(response, "All servers safe")

    def test_not_affected_closed_and_retired_reviews_do_not_raise_active_alerts(self):
        finding = self.record_finding()
        finding.analyst_applicability = "not_affected"
        finding.save()
        self.login()
        self.assertEqual(self.client.get("/").context["companies"][0]["reviews"], 0)
        finding.analyst_applicability, finding.status = "affected", "resolved"
        finding.save()
        self.assertEqual(self.client.get("/").context["companies"][0]["reviews"], 0)
        finding.status = "new"
        finding.save()
        self.asset.lifecycle = "retired"
        self.asset.save()
        self.assertEqual(self.client.get("/").context["priority_assets"], [])

    def test_current_monitoring_and_explicit_pauses_are_separate_from_empty_findings(self):
        self.installation.version = "1.0.0"
        self.installation.save()
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="server",
            source_url="https://vulnerability.circl.lu",
            last_success=timezone.now(),
            requested=False,
        )
        self.contact.notification_enabled = True
        self.contact.reachable_at = self.contact.reviewed_at = timezone.now()
        self.contact.next_review = timezone.localdate() + timedelta(days=30)
        self.contact.save()
        self.login()
        state = self.client.get("/").context["companies"][0]
        self.assertEqual(state["fresh"], 1)
        self.assertEqual(state["status"], "No open items recorded")
        watch.enabled = False
        watch.save()
        state = self.client.get("/").context["companies"][0]
        self.assertEqual(state["paused"], 1)
        self.assertTrue(state["coverage_gaps"])

    def test_overview_aggregates_do_not_multiply_memberships_and_escape_search(self):
        Membership.objects.create(organization=self.a, user=self.platform, role="editor")
        self.login(self.platform)
        response = self.client.get("/")
        self.assertEqual(len(response.context["companies"]), 2)
        self.assertEqual(response.context["companies"][0]["assets"], 1)
        response = self.client.get("/", {"q": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class AutoEnrollmentConcurrency(TransactionTestCase):
    def setUp(self):
        Fixture.setUpTestData.__func__(type(self))
        self.product.name = "Apache Log4j"
        self.product.save()

    def test_two_workers_create_one_enabled_mapping_without_replacing_settings(self):
        def enroll(_):
            close_old_connections()
            try:
                return ensure_watch(self.product)[1]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            result = list(workers.map(enroll, range(2)))
        self.assertEqual(sorted(result), [False, True])
        self.assertEqual(ProductWatch.objects.count(), 1)
        self.assertTrue(ProductWatch.objects.get().enabled)
