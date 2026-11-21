"""National aggregates and confidential no-CVE research keep current organization/evidence policy."""

import logging
from datetime import timedelta
from unittest.mock import patch
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from config.oidc import RedactAuthQueries
from .tests import Fixture
from .models import (
    Asset,
    AssetIssue,
    AuditEvent,
    DiscoveryMatch,
    DiscoveryRevision,
    FindingHistory,
    Installation,
    InventorySource,
    Organization,
    Product,
    Membership,
    ProductWatch,
    SourceRecordRevision,
)
from .intelligence import digest


class CIRCLTests(Fixture):
    def setUp(self):
        self.login(self.analyst)
        self.post = dict(
            product=self.product.name, product_match="exact", mode="exact", version="1.2.3", bucket="matches"
        )

    def test_roles_navigation_and_global_sensitive_read_audit(self):
        for user in [self.admin, self.reader, self.editor]:
            self.login(user)
            for name in ["circl-overview", "circl-findings", "circl-research"]:
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
            self.assertNotContains(self.client.get("/"), 'href="/circl/"')
        self.login(self.analyst)
        response = self.client.get(reverse("circl-overview"))
        self.assertContains(response, "National overview")
        self.assertContains(response, "data-overview-refresh checked")
        self.assertEqual(response.context["workspace_area"], "national")
        self.assertTrue(
            AuditEvent.objects.filter(actor=self.analyst, action="operator.national_overview").exists()
        )
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("circl-overview")).status_code, 302)

    def test_outstanding_reviews_include_accepted_risk_and_preserve_source_policy(self):
        finding = self.record_finding(shareable=False)
        finding.analyst_applicability = "affected"
        finding.status = "accepted_risk"
        finding.save()
        response = self.client.get(reverse("circl-panel", args=["summary"]))
        self.assertEqual(response.context["counts"]["affected"], 1)
        self.assertEqual(response.context["counts"]["accepted"], 1)
        self.assertEqual(response.context["counts"]["organizations"], 1)
        self.assertNotContains(response, self.b.name)
        target = self.client.get(
            reverse("circl-findings"), {"record": finding.record.external_id, "bucket": "accepted"}
        )
        self.assertEqual(target.context["page"].paginator.count, 1)
        self.assertContains(target, f"?finding={finding.pk}#finding-{finding.pk}")
        finding.status = "resolved"
        finding.save()
        self.assertEqual(
            self.client.get(reverse("circl-panel", args=["summary"])).context["counts"]["reviews"], 0
        )
        finding.status, finding.analyst_applicability = "new", "not_affected"
        finding.save()
        self.assertEqual(
            self.client.get(reverse("circl-panel", args=["summary"])).context["counts"]["reviews"], 0
        )
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(
            self.client.get(reverse("circl-panel", args=["summary"])).context["counts"]["organizations"], 0
        )
        Membership.objects.create(organization=self.a, user=self.analyst, role="reader")
        finding.analyst_applicability = "affected"
        finding.save()
        self.assertEqual(
            self.client.get(reverse("circl-panel", args=["summary"])).context["counts"]["reviews"], 0
        )
        finding.record.shareable = True
        finding.record.save()
        self.assertEqual(
            self.client.get(reverse("circl-panel", args=["summary"])).context["counts"]["reviews"], 1
        )

    def test_prevalence_and_inventory_counters_exclude_foreign_sources_and_retired_assets(self):
        self.installation.version = "1.2.3"
        self.installation.save()
        Installation.objects.create(asset=self.asset, product=self.product, version="1.2.3")
        for asset in [
            Asset.objects.create(organization=self.a, source=self.sb, name="Wrong source"),
            Asset.objects.create(organization=self.a, source=self.sa, name="Retired", lifecycle="retired"),
        ]:
            Installation.objects.create(asset=asset, product=self.product, version="1.2.3")
        response = self.client.get(reverse("circl-panel", args=["summary"]))
        self.assertEqual(response.context["counts"]["installations"], 2)
        response = self.client.get(reverse("circl-panel", args=["versions"]))
        item = response.context["versions"][0]
        self.assertEqual((item["companies"], item["assets"], item["total"]), (1, 1, 2))
        self.assertContains(response, 'action="/circl/research/"')

    def test_exact_custom_versions_unknowns_pagination_and_no_source_io_or_saved_criteria(self):
        self.installation.version = "2019 CU12"
        self.installation.save()
        for number in range(27):
            Installation.objects.create(asset=self.asset, product=self.product, version="2019 CU12")
        Installation.objects.create(asset=self.asset, product=self.product, version="")
        data = {**self.post, "version": "2019 CU12"}
        with patch("requests.request") as remote, patch("httpx.Client.request") as connector:
            response = self.client.post(reverse("circl-research"), data)
            remote.assert_not_called()
            connector.assert_not_called()
        self.assertEqual(response.context["match_counts"], {"matches": 28, "unknown": 1, "unsupported": 0})
        self.assertEqual(len(response.context["page"]), 25)
        response = self.client.post(reverse("circl-research"), {**data, "page": 2})
        self.assertEqual(len(response.context["page"]), 3)
        self.assertContains(response, 'form="research-form" name="page"')
        self.assertEqual(
            self.client.post(reverse("circl-research"), {**data, "bucket": "unknown"})
            .context["page"]
            .paginator.count,
            1,
        )
        self.assertNotIn("2019 CU12", str(list(AuditEvent.objects.values("target", "details"))))
        self.assertNotIn("2019 CU12", str(dict(self.client.session)))
        self.assertEqual(AssetIssue.objects.count(), 0)

    def test_ranges_are_numeric_exclusive_and_unsupported_versions_are_separate(self):
        for version in ["1.2.3", "1.9.0", "1.10.0", "2.0.0", "1.2.3-vendor"]:
            Installation.objects.create(asset=self.asset, product=self.product, version=version)
        data = {**self.post, "mode": "range", "minimum": "1.9.0", "maximum": "2.0.0"}
        response = self.client.post(reverse("circl-research"), data)
        self.assertEqual(response.context["match_counts"], {"matches": 2, "unknown": 1, "unsupported": 1})
        self.assertEqual({i.version for i in response.context["page"]}, {"1.9.0", "1.10.0"})
        unknown = self.client.post(reverse("circl-research"), {**data, "bucket": "unsupported"})
        self.assertEqual([i.version for i in unknown.context["page"]], ["1.2.3-vendor"])
        for changed in [{"minimum": "1.2.3-beta"}, {"minimum": "3.0.0"}]:
            invalid = self.client.post(reverse("circl-research"), {**data, **changed})
            self.assertTrue(invalid.context["form"].errors)
            self.assertNotIn("page", invalid.context)
        with patch("portal.circl.MAX_RANGE_VERSIONS", 2):
            broad = self.client.post(reverse("circl-research"), data)
        self.assertTrue(broad.context["form"].non_field_errors())
        self.assertNotIn("page", broad.context)

    def test_confidential_get_parameters_ignored_csrf_required_and_query_log_redacted(self):
        secret = "Private advisory <script>secret</script>"
        response = self.client.get(reverse("circl-research"), {"product": secret})
        self.assertNotContains(response, secret)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.analyst)
        self.assertEqual(csrf.post(reverse("circl-research"), self.post).status_code, 403)
        csrf.get(reverse("circl-research"), secure=True)
        accepted = csrf.post(
            reverse("circl-research"),
            {**self.post, "csrfmiddlewaretoken": csrf.cookies["csrftoken"].value},
            secure=True,
            HTTP_ORIGIN="https://testserver",
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertIn("match_counts", accepted.context)
        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            1,
            "%s",
            ("GET /circl/research/?product=private-version HTTP/1.1",),
            None,
        )
        RedactAuthQueries().filter(record)
        self.assertNotIn("private-version", record.getMessage())
        self.assertIn("[redacted]", record.getMessage())

    def test_research_revocation_empty_results_and_html_escaping(self):
        self.product.name = '<img src=x onerror="bad()">'
        self.product.save()
        self.installation.version = "1.2.3"
        self.installation.save()
        data = {**self.post, "product": self.product.name}
        response = self.client.post(reverse("circl-research"), data)
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, "<img src=x")
        self.a.operator_visibility = False
        self.a.save()
        response = self.client.post(reverse("circl-research"), data)
        self.assertEqual(response.context["page"].paginator.count, 0)
        self.assertContains(response, "No installations in this group")
        self.assertNotContains(response, self.asset.name)

    def test_trends_count_first_automated_revision_and_resolution_events_once(self):
        finding = self.record_finding()
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="server",
            source_url="https://vulnerability.circl.lu",
        )
        revision = SourceRecordRevision.objects.create(
            record=finding.record, payload={}, content_hash=digest({})
        )
        match = DiscoveryMatch.objects.create(
            watch=watch,
            finding=finding,
            evidence_revision=revision,
            input_hash="synthetic",
            explanation="Synthetic",
            result="unknown",
        )
        for days, fingerprint in [(8, "first"), (1, "refresh")]:
            DiscoveryRevision.objects.create(
                match=match,
                fingerprint=fingerprint,
                snapshot={},
                created_at=timezone.now() - timedelta(days=days),
            )
        FindingHistory.objects.create(
            finding=finding, previous_status="new", status="resolved", reason="Synthetic"
        )
        FindingHistory.objects.create(
            finding=finding, previous_status="resolved", status="resolved", reason="No transition"
        )
        response = self.client.get(reverse("circl-panel", args=["activity"]))
        self.assertEqual(response.context["trend"]["new"], 1)
        self.assertEqual(response.context["trend"]["recent"], 0)
        self.assertEqual(response.context["trend"]["previous"], 1)
        self.assertEqual(response.context["trend"]["closures"], 1)
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(
            self.client.get(reverse("circl-panel", args=["activity"])).context["trend"]["new"], 0
        )

    def test_dashboard_query_budget_is_bounded_without_per_company_counts(self):
        self.record_finding()
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(reverse("circl-panel", args=["summary"])).status_code, 200)
        for number in range(12):
            org = Organization.objects.create(
                name=f"Reporting company {number}", slug=f"national-budget-{number}", operator_visibility=True
            )
            source = InventorySource.objects.create(organization=org, mode="development")
            asset = Asset.objects.create(organization=org, source=source, name=f"Reporting asset {number}")
            product = Product.objects.create(organization=org, name=self.product.name)
            Installation.objects.create(asset=asset, product=product)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(reverse("circl-panel", args=["summary"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["counts"]["organizations"], 13)
        self.assertEqual(response.context["counts"]["installations"], 13)
        self.assertLessEqual(len(large), len(small) + 1)
        self.assertLessEqual(len(large), 35)

    def test_shell_never_runs_aggregates_and_sections_fail_independently(self):
        from django.db import OperationalError

        with patch("portal.circl_views.dashboard", side_effect=AssertionError("No heavy shell query")):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse("circl-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-national-panel="summary"')
        self.assertFalse(any("portal_finding" in query["sql"] for query in queries))
        with patch("portal.circl_views.dashboard", side_effect=OperationalError("private query text")):
            response = self.client.get(reverse("circl-panel", args=["activity"]))
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "private query text", status_code=503)
        self.assertContains(response, "missing results are not zero", status_code=503)
        self.assertEqual(self.client.get(reverse("circl-panel", args=["versions"])).status_code, 200)
        self.login(self.admin)
        for section in ["summary", "problems", "versions", "activity"]:
            self.assertEqual(self.client.get(reverse("circl-panel", args=[section])).status_code, 403)


class ResearchOverloadTests(Fixture):
    def test_timeout_is_private_retryable_and_never_a_partial_result(self):
        from django.db import OperationalError

        self.login(self.analyst)
        with patch("portal.circl_views.research", side_effect=OperationalError("synthetic timeout")):
            response = self.client.post(
                "/circl/research/",
                dict(
                    product="confidential fixture",
                    product_match="exact",
                    mode="exact",
                    version="1",
                    bucket="matches",
                ),
            )
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "no partial results", status_code=503)
        self.assertNotIn("page", response.context)
        self.assertIn("no-store", response["Cache-Control"])
