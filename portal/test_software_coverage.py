"""Synthetic inventory accounting, scoped current proofs and retained review decisions."""

from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from . import discovery
from .models import Asset, Finding, Installation, Product, ProductWatch, SourceRecord
from .tests import Fixture
from .test_package_verdicts import save_browser_evidence


class SoftwareCoverageTests(Fixture):
    def page(self, **params):
        return self.client.get(reverse("software-coverage", args=[self.a.slug]), params)

    def watch(self):
        self.installation.version = "1.2.0"
        self.installation.save(update_fields=["version"])
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="example_product",
            source_url="https://vendor.example.invalid",
        )
        payload = {
            "cveMetadata": {"cveId": "CVE-2099-10101", "state": "PUBLISHED"},
            "containers": {
                "cna": {
                    "affected": [
                        {
                            "vendor": "example",
                            "product": "example_product",
                            "versions": [
                                {
                                    "version": "1.0.0",
                                    "lessThan": "2.0.0",
                                    "versionType": "semver",
                                    "status": "affected",
                                }
                            ],
                        }
                    ],
                    "references": [{"url": "https://manufacturer.example.invalid/security/CVE-2099-10101"}],
                }
            },
        }
        with patch(
            "portal.discovery.product_records", return_value=(watch.source_url, [("CVE-2099-10101", payload)])
        ):
            discovery.sync_watch(watch.pk)
        watch.refresh_from_db()
        return watch

    def test_every_retained_installation_is_accounted_once_and_not_called_evaluated(self):
        self.login(self.reader)
        product = Product.objects.create(
            organization=self.a, name="Unmapped", identifier="pkg:generic/unmapped"
        )
        Installation.objects.create(asset=self.asset, product=product, version="1")
        package = Product.objects.create(
            organization=self.a, name="Package", identifier="pkg:deb/ubuntu/example"
        )
        Installation.objects.create(asset=self.asset, product=package, version="1")
        retired = Asset.objects.create(
            organization=self.a, source=self.sa, name="Old fixture", lifecycle="retired"
        )
        Installation.objects.create(asset=retired, product=product, version="1")
        page = self.page()
        self.assertEqual(page.status_code, 200)
        save_browser_evidence("software-coverage-ledger", page)
        save_browser_evidence(
            "software-coverage-overview-four",
            self.client.get(reverse("overview"), {"organization": self.a.slug}),
        )
        summary = page.context["summary"]
        self.assertEqual(summary["total"], 4)
        self.assertEqual(sum(row["count"] for row in summary["categories"]), 4)
        self.assertEqual(
            {i.coverage_category for i in page.context["page"]},
            {"version", "unmapped", "package", "retained"},
        )
        self.assertContains(page, "not a guarantee")
        self.assertContains(page, "No installed version is recorded")
        self.assertContains(page, "matching device metadata is unavailable")
        self.assertNotContains(page, "beta-secret")
        for row in summary["categories"]:
            response = self.client.get(row["url"])
            self.assertEqual(response.context["page"].paginator.count, row["count"])

    def test_current_application_proof_and_manual_decisions_are_separate(self):
        self.watch()
        finding = Finding.objects.get(installation=self.installation)
        Finding.objects.filter(pk=finding.pk).update(
            analyst_applicability="not_affected", status="accepted_risk"
        )
        self.login(self.reader)
        with patch(
            "portal.connectors.http.request_json",
            side_effect=AssertionError("Ledger must not fetch external data"),
        ):
            page = self.page()
        self.assertEqual(page.status_code, 200)
        row = page.context["page"][0]
        self.assertEqual(len(row.coverage_evidence), 1)
        self.assertTrue(row.coverage_evidence[0]["current"])
        self.assertContains(page, "Affected-version rule matched")
        self.assertContains(page, "CVE-2099-10101")
        self.assertContains(page, "Evaluated version: 1.2.0")
        self.assertContains(page, "not_affected")
        finding.refresh_from_db()
        self.assertEqual(finding.status, "accepted_risk")
        self.assertEqual(finding.analyst_applicability, "not_affected")
        destination = self.client.get(row.coverage_evidence[0]["url"])
        self.assertEqual(destination.status_code, 200)

    def test_changed_version_and_advisory_snapshot_never_look_current(self):
        self.watch()
        self.login(self.reader)
        Installation.objects.filter(pk=self.installation.pk).update(version="3.0.0")
        page = self.page()
        self.assertContains(page, "Retained evidence needs reevaluation")
        evidence = page.context["page"][0].coverage_evidence[0]
        self.assertFalse(evidence["current"])
        self.assertEqual(evidence["version"], "1.2.0")
        Installation.objects.filter(pk=self.installation.pk).update(version="1.2.0")
        record = SourceRecord.objects.get()
        record.payload = {"changed": "unvalidated synthetic source"}
        record.save()
        self.assertFalse(self.page().context["page"][0].coverage_evidence[0]["current"])

    def test_absent_index_advisory_is_historical_even_when_its_inputs_match(self):
        watch = self.watch()
        ProductWatch.objects.filter(pk=watch.pk).update(
            last_attempt=timezone.now(), last_success=timezone.now()
        )
        self.login(self.reader)
        self.assertFalse(self.page().context["page"][0].coverage_evidence[0]["current"])

    def test_source_outage_pause_and_zero_records_remain_explicit_gaps(self):
        watch = self.watch()
        self.login(self.reader)
        ProductWatch.objects.filter(pk=watch.pk).update(error="synthetic outage")
        self.assertContains(self.page(), "Current evaluation unavailable")
        ProductWatch.objects.filter(pk=watch.pk).update(error="", enabled=False)
        self.assertContains(self.page(), "Automatic checks paused")
        ProductWatch.objects.filter(pk=watch.pk).update(enabled=True)
        extra = Installation.objects.create(asset=self.asset, product=self.product, version="1.2.0")
        row = next(i for i in self.page().context["page"] if i.pk == extra.pk)
        self.assertEqual(row.coverage_label, "No visible version-rule evidence")

    def test_restricted_intelligence_never_supplies_counts_examples_or_verdicts(self):
        self.watch()
        SourceRecord.objects.update(shareable=False)
        self.login(self.reader)
        page = self.page()
        self.assertNotContains(page, "CVE-2099-10101")
        self.assertEqual(page.context["page"][0].coverage_reviews, 0)
        self.assertEqual(page.context["page"][0].coverage_evidence, [])
        self.assertContains(page, "No visible version-rule evidence")
        self.login(self.platform)
        self.assertContains(self.page(), "CVE-2099-10101")
        self.a.operator_visibility = False
        self.a.save(update_fields=["operator_visibility"])
        self.login(self.analyst)
        self.assertEqual(self.page().status_code, 404)

    def test_request_scoped_permission_reads_recheck_revocation(self):
        from django.contrib.auth.models import Group
        from .access import ANALYST_GROUP
        from .models import Membership

        self.a.operator_visibility = True
        self.a.save(update_fields=["operator_visibility"])
        Membership.objects.filter(user=self.analyst, organization=self.a).delete()
        self.login(self.analyst)
        overview = reverse("overview")
        params = {"organization": self.a.slug}
        self.assertEqual(self.client.get(overview, params).status_code, 200)
        self.assertEqual(self.page().status_code, 200)
        self.analyst.groups.remove(Group.objects.get(name=ANALYST_GROUP))
        self.assertEqual(self.client.get(overview, params).status_code, 404)
        self.assertEqual(self.page().status_code, 404)

    def test_corrupt_cross_company_product_is_counted_without_its_identity(self):
        foreign = Product.objects.create(
            organization=self.b, name="Foreign classified product", identifier="secret-foreign-identity"
        )
        Installation.objects.filter(pk=self.installation.pk).update(product=foreign)
        self.login(self.reader)
        page = self.page()
        self.assertEqual(page.context["summary"]["total"], 1)
        self.assertEqual(page.context["page"][0].coverage_category, "integrity")
        self.assertNotContains(page, foreign.name)
        self.assertNotContains(page, foreign.identifier)
        self.assertEqual(self.page(q=foreign.name).context["summary"]["total"], 0)

    def test_scope_search_filters_and_pages_preserve_inventory_denominator(self):
        self.login(self.reader)
        with CaptureQueriesContext(connection) as baseline:
            self.page(asset=self.asset.pk, q="Example")
        for index in range(55):
            Installation.objects.create(asset=self.asset, product=self.product, version=str(index))
        with CaptureQueriesContext(connection) as queries:
            first = self.page(asset=self.asset.pk, q="Example")
        self.assertEqual(first.context["summary"]["total"], 56)
        self.assertEqual(len(first.context["page"]), 25)
        self.assertLessEqual(len(queries), len(baseline) + 4)
        self.assertLessEqual(len(queries), 40)
        second = self.client.get(reverse("software-coverage", args=[self.a.slug]) + first.context["next_url"])
        self.assertEqual(second.context["summary"]["total"], 56)
        self.assertFalse({i.pk for i in first.context["page"]} & {i.pk for i in second.context["page"]})
        self.assertEqual(self.page(category="invented").status_code, 404)
        self.assertEqual(self.client.post(reverse("software-coverage", args=[self.a.slug])).status_code, 405)
        self.assertEqual(self.page(asset=self.other.pk).status_code, 404)
        self.assertEqual(self.client.get(reverse("software-coverage", args=[self.b.slug])).status_code, 404)

    def test_untrusted_explanation_is_escaped_bounded_and_retained(self):
        self.watch()
        from .models import DiscoveryMatch

        match = DiscoveryMatch.objects.get()
        text = "<script>UNTRUSTED()</script>" * 400
        DiscoveryMatch.objects.filter(pk=match.pk).update(explanation=text)
        self.login(self.reader)
        response = self.page()
        self.assertContains(response, "&lt;script&gt;UNTRUSTED()")
        self.assertNotContains(response, "<script>UNTRUSTED()")
        self.assertContains(response, "Explanation preview shortened")
        self.assertEqual(len(response.context["page"][0].coverage_evidence[0]["explanation"]), 2000)
        match.refresh_from_db()
        self.assertEqual(match.explanation, text)

    def test_overview_promotes_software_accounting_and_names_package_scope(self):
        self.login(self.reader)
        response = self.client.get(reverse("overview"), {"organization": self.a.slug})
        self.assertEqual(response.status_code, 200)
        save_browser_evidence("software-coverage-overview", response)
        self.assertContains(response, "Inspect every software installation")
        self.assertContains(response, "Machines with a current Linux package check")
        self.assertContains(response, "Coverage gaps to inspect")
        self.assertNotContains(response, "Machines evaluated</span>")
        self.assertEqual(response.context["companies"][0]["software_accounting"]["total"], 1)


class WindowsSoftwareCoverageTests(Fixture):
    from .test_windows_cves import WindowsDiscovery as _fixture

    legacy_manual_projection = False
    setUp = _fixture.setUp
    enroll = _fixture.enroll
    post = _fixture.post
    send = _fixture.send
    relax = _fixture.relax
    publish = _fixture.publish
    prepare = _fixture.prepare
    sync = _fixture.sync

    def page(self):
        self.login(self.reader)
        response = self.client.get(reverse("software-coverage", args=[self.a.slug]))
        self.assertEqual(response.status_code, 200)
        return response

    def test_windows_os_channel_gaps_and_signed_application_proof_remain_distinct(self):
        self.prepare()
        self.sync()
        response = self.page()
        rows = list(response.context["page"])
        edge = next(i for i in rows if i.pk == self.i.pk)
        self.assertEqual(edge.coverage_evidence[0]["result"], "potential")
        self.assertTrue(edge.coverage_evidence[0]["current"])
        self.assertIn("windows-vendor-rules/v3", edge.coverage_evidence[0]["rule"])
        self.assertContains(response, "Windows mapping evidence incomplete")
        self.assertContains(response, "Update line missing")
        self.assertContains(response, "https://msrc.microsoft.com/")
        self.assertEqual(
            sum(r["count"] for r in response.context["summary"]["categories"]),
            response.context["summary"]["total"],
        )

    def test_revoked_observations_and_source_rebinding_never_supply_current_proof(self):
        self.prepare()
        self.sync()
        from .models import AgentDevice

        AgentDevice.objects.filter(pk=self.device.pk).update(enabled=False)
        row = next(i for i in self.page().context["page"] if i.pk == self.i.pk)
        self.assertEqual(row.coverage_category, "retained")
        self.assertEqual(row.coverage_evidence, [])
        AgentDevice.objects.filter(pk=self.device.pk).update(enabled=True, source=self.sb)
        response = self.page()
        row = next(i for i in response.context["page"] if i.pk == self.i.pk)
        self.assertEqual(row.coverage_category, "integrity")
        self.assertNotContains(response, "CVE-2026-99999")
        self.assertNotContains(response, "Microsoft Edge")

    def test_unlinked_and_excluded_observations_are_accounted_separately(self):
        self.prepare()
        from .models import AgentComponent

        AgentComponent.objects.filter(pk=self.component.pk).update(installation=None, inventory_excluded=True)
        response = self.page()
        self.assertEqual(response.context["unlinked"], 1)
        self.assertContains(response, "1 unlinked client observations")
        observations = self.client.get(
            reverse("software-coverage", args=[self.a.slug]), {"view": "observations"}
        )
        self.assertEqual(observations.status_code, 200)
        self.assertEqual(observations.context["page"].paginator.count, 1)
        self.assertContains(observations, "Microsoft Edge")
        self.assertContains(observations, "Explicitly excluded")
        self.assertNotContains(observations, "CVE-2026-99999")
        from .models import AgentDevice

        AgentDevice.objects.filter(pk=self.device.pk).update(source=self.sb)
        observations = self.client.get(
            reverse("software-coverage", args=[self.a.slug]), {"view": "observations"}
        )
        self.assertEqual(observations.context["page"].paginator.count, 1)
        self.assertNotContains(observations, "Microsoft Edge")
        self.assertContains(observations, "foreign details withheld")
