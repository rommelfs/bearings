"""Package receipts prove evaluated negatives without creating or closing human reviews."""

import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import override_settings, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from . import agents, distro_cves, distro_results
from . import test_distro_cves as distro_tests

from . import test_agents as legacy
from .models import AgentComponent, AgentDevice, DistroFeed, Finding
from .connectors.http import ConnectorError

XML = distro_tests.XML


class PackageResultsTests(Fixture):
    legacy_manual_projection = False
    setUp = legacy.AgentTests.setUp
    post = legacy.AgentTests.post
    enroll = legacy.AgentTests.enroll
    data = legacy.AgentTests.data
    send = legacy.AgentTests.send
    relax = legacy.AgentTests.relax
    load = distro_tests.DistroTests.load

    def prepare(self, version="1:1.24.0-2ubuntu7.9", xml=XML):
        self.enroll()
        self.send(self.data(version=version))
        agents.process_pending()
        self.feed = self.load(xml)
        distro_cves.evaluate_device(self.device.pk)
        self.device.refresh_from_db()
        return self.device.components.get(name="nginx")

    def page(self, component):
        self.login()
        return self.client.get(reverse("discovery"), {"product": component.installation.product_id})

    def test_initial_fixed_package_records_proof_without_creating_a_finding(self):
        c = self.prepare()
        self.assertFalse(Finding.objects.exists())
        receipt = c.distro_check
        self.assertEqual(receipt["counts"], {"potential": 0, "unknown": 0, "fixed": 1, "not_matched": 0})
        self.assertEqual(receipt["samples"]["fixed"][0]["fixed_version"], "1:1.24.0-2ubuntu7.6")
        self.assertEqual(receipt["input_hash"], distro_results.inputs(c, c.device))
        response = self.page(c)
        self.assertContains(response, "No package-rule alert in the evaluated results")
        self.assertContains(response, "CVE-2099-99999")
        self.assertContains(response, "Rule SHA-256:")
        self.assertContains(response, "Fixed by installed package version · 1")
        self.assertContains(response, "Last successful package check:")

    def test_version_update_keeps_human_decision_while_technical_result_changes(self):
        c = self.prepare("1:1.24.0-2ubuntu7.5")
        f = Finding.objects.get()
        f.status = "confirmed"
        f.analyst_applicability = "affected"
        f.save()
        self.assertContains(self.page(c), "Review required")
        self.relax()
        self.send(self.data(sequence=2, version="1:1.24.0-2ubuntu7.21"))
        self.assertContains(self.page(c), "Current package result unavailable")
        agents.process_pending()
        c.refresh_from_db()
        self.assertContains(self.page(c), "Current package result unavailable")
        distro_cves.evaluate_device(self.device.pk)
        f.refresh_from_db()
        self.assertEqual((f.status, f.analyst_applicability), ("confirmed", "affected"))
        response = self.page(c)
        self.assertContains(response, "1 outstanding reviews")
        self.assertContains(response, "No package-rule alert in the evaluated results")

    def test_stale_failed_changed_disabled_and_old_generation_are_never_current(self):
        c = self.prepare()
        original = self.device.distro_summary
        for changes in [
            {"distro_requested": True},
            {"distro_summary": {"state": "error"}},
            {"enabled": False},
        ]:
            AgentDevice.objects.filter(pk=self.device.pk).update(**changes)
            self.assertContains(self.page(c), "Current package result unavailable")
            AgentDevice.objects.filter(pk=self.device.pk).update(
                enabled=True, distro_requested=False, distro_summary=original
            )
        AgentComponent.objects.filter(pk=c.pk).update(version="1:1.24.0-2ubuntu7.22")
        self.assertContains(self.page(c), "Current package result unavailable")
        AgentComponent.objects.filter(pk=c.pk).update(version=c.version)
        with override_settings(DISTRO_CVE_ENABLED=False):
            self.assertContains(self.page(c), "Disabled by platform configuration")
            self.assertNotContains(self.page(c), "No package-rule alert in the evaluated results")
        DistroFeed.objects.filter(pk=self.feed.pk).update(generation=uuid.uuid4())
        self.assertContains(self.page(c), "Current package result unavailable")
        DistroFeed.objects.filter(pk=self.feed.pk).update(last_success=timezone.now() - timedelta(hours=13))
        self.assertContains(self.page(c), "Current package result unavailable")

    def test_architecture_mismatch_and_unsupported_conditions_are_not_fixed_proof(self):
        xml = XML.replace("<l:evr datatype=", '<l:arch operation="equals">arm64</l:arch><l:evr datatype=')
        c = self.prepare(xml=xml)
        self.assertEqual(c.distro_check["counts"]["fixed"], 0)
        self.assertEqual(c.distro_check["counts"]["not_matched"], 1)
        self.assertEqual(c.distro_check["counts"]["potential"], 0)
        self.assertFalse(Finding.objects.exists())

    def test_unresolved_condition_is_explicit_and_not_a_successful_negative(self):
        xml = XML.replace(
            "</l:dpkginfo_state>", "<l:signature_keyid>unknown-key</l:signature_keyid></l:dpkginfo_state>"
        )
        c = self.prepare(version="1:1.24.0-2ubuntu7.5", xml=xml)
        self.assertEqual(c.distro_check["counts"]["unknown"], 1)
        self.assertEqual(c.distro_check["counts"]["fixed"], 0)
        self.assertContains(self.page(c), "Review required")
        self.assertNotContains(self.page(c), "No package-rule alert in the evaluated results")

    def test_failed_publication_retains_previous_receipt_atomically(self):
        c = self.prepare()
        original = c.distro_check
        self.relax()
        self.send(self.data(sequence=2, version="1:1.24.0-2ubuntu7.5"))
        agents.process_pending()
        with patch(
            "portal.distro_results.Collector.receipt", side_effect=ConnectorError("Synthetic budget failure")
        ):
            with self.assertRaises(ConnectorError):
                distro_cves.evaluate_device(self.device.pk)
        c.refresh_from_db()
        self.assertEqual(c.distro_check, original)
        self.assertFalse(Finding.objects.exists(), "A failed receipt must roll back new finding publication")
        with patch("portal.distro_results.MAX_OUTCOMES", 0):
            with self.assertRaises(ConnectorError):
                distro_cves.evaluate_device(self.device.pk)
        c.refresh_from_db()
        self.assertEqual(c.distro_check, original)
        self.assertFalse(Finding.objects.exists())

    def test_bounded_samples_keep_full_distinct_counts(self):
        xml = XML.replace('ref_id="CVE-2099-99999"', 'ref_id="CVE-2099-99999"')
        references = "".join(f'<reference source="CVE" ref_id="CVE-2099-{90000 + i}"/>' for i in range(30))
        c = self.prepare(xml=xml.replace("</metadata>", references + "</metadata>"))
        self.assertEqual(c.distro_check["counts"]["fixed"], 31)
        self.assertEqual(len(c.distro_check["samples"]["fixed"]), distro_results.SAMPLE_LIMIT)
        self.assertFalse(Finding.objects.exists())


class NegativeProofTests(SimpleTestCase):
    def test_source_version_proof_is_not_mislabeled_as_the_binary_version(self):
        from types import SimpleNamespace

        leaf = {
            "package": ["nginx-source"],
            "manager": "dpkg",
            "source": True,
            "states": [[{"field": "evr", "operation": "less than", "text": "1.24.0-1"}]],
            "state_operator": "AND",
            "check": "at least one",
            "existence": "at_least_one_exists",
        }
        fact = {"id": 1, "version": "1.24.0-2", "architecture": "amd64"}
        advisory = SimpleNamespace(
            pk=1,
            criteria=leaf,
            identity="synthetic-source",
            content_hash="a" * 64,
            metadata={"cves": ["CVE-2099-99999"]},
        )
        checks = distro_results.Collector()
        checks.add(advisory, {("dpkg", True, "nginx-source"): [fact]}, False, {1: False}, {})
        result = checks.results[1]["CVE-2099-99999"]
        self.assertEqual(result["result"], "fixed")
        self.assertEqual(result["compared_version"], "1.24.0-2")
        self.assertEqual(result["comparison_basis"], "source package")
        advisory.criteria = {"operator": "AND", "children": [leaf, {"unknown": "unsupported OS guard"}]}
        checks = distro_results.Collector()
        checks.add(advisory, {("dpkg", True, "nginx-source"): [fact]}, False, {1: False}, {})
        self.assertEqual(checks.results[1]["CVE-2099-99999"]["result"], "not_matched")
