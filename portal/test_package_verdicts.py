"""Vendor package proof, independent Boolean branches and native-version decisions."""

import json
import os
import uuid
import shutil
import subprocess
from unittest import skipUnless
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase
from django.utils import timezone
from . import distro_oval, distro_cves, agents
from .test_distro_cves import DistroTests
from .models import DistroFeed, Finding, AgentDevice


def save_browser_evidence(name, response):
    directory = os.environ.get("BEARINGS_PACKAGE_UI_DIR")
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / (name + ".html")).write_bytes(response.content)


def leaf(name, bound="2", states=None):
    return {
        "package": [name],
        "manager": "dpkg",
        "source": False,
        "states": states
        if states is not None
        else [[{"field": "evr", "operation": "less than", "text": bound}]],
        "state_operator": "AND",
        "check": "at least one",
        "existence": "at_least_one_exists",
    }


def facts(*versions):
    return {
        ("dpkg", False, name): [{"id": index + 1, "version": version, "architecture": "amd64"}]
        for index, (name, version) in enumerate(versions)
    }


class AttributionTests(SimpleTestCase):
    def test_existence_is_true_but_does_not_prove_an_affected_version(self):
        truth, outcomes = distro_oval.evaluate_matches(
            leaf("pip", states=[]), facts(("pip", "24.0+dfsg-1ubuntu1.3")), True, {}
        )
        self.assertIs(truth, True)
        self.assertEqual(outcomes, {1: None})

    def test_true_or_branch_does_not_mark_fixed_sibling_vulnerable(self):
        node = {
            "operator": "AND",
            "children": [{"constant": True}, {"operator": "OR", "children": [leaf("one"), leaf("two")]}],
        }
        truth, outcomes = distro_oval.evaluate_matches(node, facts(("one", "1"), ("two", "3")), True, {})
        self.assertIs(truth, True)
        self.assertEqual(outcomes, {1: True, 2: False})

    def test_true_or_branch_does_not_promote_unknown_sibling(self):
        unknown = leaf("two", states=[[{"field": "signature_keyid", "text": "unreported"}]])
        node = {"operator": "OR", "children": [leaf("one"), unknown]}
        self.assertEqual(
            distro_oval.evaluate_matches(node, facts(("one", "1"), ("two", "1")), True, {})[1],
            {1: True, 2: None},
        )

    def test_unknown_required_guard_keeps_version_match_unresolved(self):
        node = {"operator": "AND", "children": [leaf("one"), {"unknown": "runtime fact"}]}
        self.assertEqual(distro_oval.evaluate_matches(node, facts(("one", "1")), True, {})[1], {1: None})

    def test_presence_guard_does_not_invalidate_a_proven_version_of_same_package(self):
        node = {"operator": "AND", "children": [leaf("one", states=[]), leaf("one")]}
        self.assertEqual(distro_oval.evaluate_matches(node, facts(("one", "1")), True, {})[1], {1: True})

    def test_architecture_or_alternative_cannot_replace_an_affected_version_proof(self):
        node = leaf(
            "one",
            states=[
                [{"field": "evr", "operation": "less than", "text": "2"}],
                [{"field": "arch", "text": "amd64"}],
            ],
        )
        node["state_operator"] = "OR"
        self.assertEqual(distro_oval.evaluate_matches(node, facts(("one", "3")), True, {})[1], {1: None})

    def test_unknown_unattributed_or_branch_cannot_prove_not_affected(self):
        node = {"operator": "OR", "children": [leaf("one"), {"unknown": "unsupported extension"}]}
        self.assertEqual(distro_oval.evaluate_matches(node, facts(("one", "3")), True, {})[1], {1: None})

    def test_unsupported_package_field_and_architecture_pattern_stay_unknown(self):
        node = leaf(
            "one",
            states=[
                [
                    {"field": "evr", "operation": "less than", "text": "2"},
                    {"field": "machine_class", "text": "amd64"},
                ]
            ],
        )
        self.assertEqual(distro_oval.evaluate_matches(node, facts(("one", "1")), True, {})[1], {1: None})
        for pattern in ("^amd64|arm64$", "amd64", "amd.64"):
            self.assertIsNone(
                distro_oval.condition(
                    "amd64", {"field": "arch", "operation": "pattern match", "text": pattern}, "dpkg"
                )
            )
        self.assertIs(
            distro_oval.condition(
                "amd64", {"field": "arch", "operation": "pattern match", "text": "^(amd64|arm64)$"}, "dpkg"
            ),
            True,
        )

    def test_missing_host_architecture_does_not_become_false_or_unaffected(self):
        node = {
            "operator": "AND",
            "children": [leaf("one"), {"host_states": [[{"field": "machine_class", "text": "x86_64"}]]}],
        }
        self.assertEqual(distro_oval.evaluate_matches(node, facts(("one", "1")), True, {})[1], {1: None})
        self.assertEqual(
            distro_oval.evaluate_matches(node, facts(("one", "1")), True, {"architecture": "x86_64"})[1],
            {1: True},
        )

    def test_native_backport_threshold_uses_debian_epoch_and_revision(self):
        node = leaf("nginx", "1.24.0-2ubuntu7.20")
        for version, expected in [
            ("1.24.0-2ubuntu7.19", True),
            ("1.24.0-2ubuntu7.20", False),
            ("1.24.0-2ubuntu7.21", False),
        ]:
            self.assertEqual(
                distro_oval.evaluate_matches(node, facts(("nginx", version)), True, {})[1], {1: expected}
            )
        self.assertGreater(distro_oval.compare("dpkg", "1:1.0-1ubuntu1", "9.0-1"), 0)

    @skipUnless(shutil.which("dpkg"), "Native Debian version oracle required")
    def test_debian_comparison_agrees_with_dpkg_for_epochs_tildes_and_backports(self):
        pairs = [
            ("1.24.0-2ubuntu7.19", "1.24.0-2ubuntu7.21"),
            ("1:1.0-1", "9.0-1"),
            ("2.0~rc1-1", "2.0-1"),
            ("1.0+dfsg-1ubuntu1.3", "1.0+dfsg-1ubuntu1.10"),
            ("1.0-1+b1", "1.0-1"),
            ("1.0-1ubuntu0.24.04.1", "1.0-1ubuntu0.24.04.2"),
        ]
        for a, b in pairs:
            native = (
                -1
                if subprocess.run(["dpkg", "--compare-versions", a, "lt", b], check=False).returncode == 0
                else 1
                if subprocess.run(["dpkg", "--compare-versions", a, "gt", b], check=False).returncode == 0
                else 0
            )
            self.assertEqual(distro_oval.compare("dpkg", a, b), native)
            self.assertEqual(distro_oval.compare("dpkg", b, a), -native)


class ExactUbuntuCaseTests(DistroTests):
    def test_actual_97688_pip_package_is_unresolved_not_a_version_match(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/oval/ubuntu-noble-CVE-2026-97688.json").read_text()
        )
        feed = DistroFeed.objects.create(
            key="ubuntu:24.04",
            generation=uuid.uuid4(),
            last_success=timezone.now(),
            summary={"compiler_version": distro_oval.COMPILER_VERSION},
        )
        distro_cves.store_batch(feed, feed.generation, [fixture["definition"]])
        self.enroll()
        data = self.data(version="24.0+dfsg-1ubuntu1.3")
        data["components"][0].update(name="python3-pip-whl", key="dpkg:python3-pip-whl:amd64")
        self.send(data)
        agents.process_pending()
        summary = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(summary["potential"], 0)
        self.assertEqual(summary["uncertain"], 1)
        finding = Finding.objects.get()
        proof = finding.distro_match.snapshot["package_check"]
        self.assertEqual(finding.applicability, "unknown")
        self.assertEqual(proof["verdict"], "unresolved")
        self.assertFalse(proof["version_checked"])
        self.assertIn("might be affected", proof["vendor_comments"][0])
        self.assertNotIn("Exact native Debian/RPM comparison", finding.explanation)
        self.login()
        response = self.client.get("/organizations/alpha/intelligence/", {"finding": finding.pk})
        self.assertContains(response, "Package affectedness unresolved")
        self.assertContains(response, "No affected/fixed version condition")
        self.assertNotContains(response, "Automated applicability: potential")
        save_browser_evidence("unresolved", response)

    def test_confirmed_version_comparison_is_presented_without_changing_human_assessment(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        self.assertEqual(finding.distro_match.snapshot["package_check"]["verdict"], "affected")
        self.assertTrue(finding.distro_match.snapshot["package_check"]["comparisons"][0]["matches"])
        self.assertEqual(finding.analyst_applicability, "unassessed")
        self.login()
        response = self.client.get("/organizations/alpha/intelligence/", {"finding": finding.pk})
        self.assertContains(response, "Affected package version")
        save_browser_evidence("affected", response)
        self.relax()
        self.send(self.data(sequence=2, version="1:1.24.0-2ubuntu7.9"))
        agents.process_pending()
        distro_cves.evaluate_device(self.device.pk)
        finding.refresh_from_db()
        self.assertEqual(finding.distro_match.snapshot["package_check"]["verdict"], "fixed")
        self.assertEqual(finding.status, "new")
        self.assertEqual(finding.analyst_applicability, "unassessed")
        response = self.client.get("/organizations/alpha/intelligence/", {"finding": finding.pk})
        self.assertContains(response, "includes the vendor fix")
        save_browser_evidence("fixed", response)

    def test_previous_evaluator_receipt_is_requeued_without_new_report(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        AgentDevice.objects.filter(pk=self.device.pk).update(
            distro_requested=False, distro_summary={"state": "ready", "evaluator_version": 1}
        )
        with (
            patch("portal.distro_cves.refresh", return_value=False),
            patch("portal.distro_cves.evaluate_device") as evaluate,
        ):
            distro_cves.run()
        evaluate.assert_called_once_with(self.device.pk)

    def test_changed_os_or_rule_inputs_withhold_the_previous_verdict(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        self.assertFalse(finding.distro_match.inputs_changed)
        match = finding.distro_match
        match.component.device.os = {**match.component.device.os, "kernel": "new-kernel"}
        self.assertTrue(match.inputs_changed)
        match = Finding.objects.get().distro_match
        match.advisory.content_hash = "different-rule"
        self.assertTrue(match.inputs_changed)

    def test_canonical_cvss_is_bound_to_its_cve_and_preserved_in_evidence(self):
        from .test_distro_cves import XML
        from .presentation import vulnerability_summary

        self.enroll()
        self.send()
        agents.process_pending()
        xml = XML.replace(
            "</advisory>",
            '<cve cvss_score="6.9" cvss_vector="CVSS:4.0/AV:N">CVE-2099-99999</cve><cve cvss_score="9.9" cvss_vector="CVSS:4.0/AV:N">CVE-2099-11111</cve></advisory>',
        )
        self.load(xml)
        distro_cves.evaluate_device(self.device.pk)
        summary = vulnerability_summary(Finding.objects.get().record.payload)
        self.assertEqual(summary["score"], 6.9)
        self.assertEqual(summary["severity"], "High")
        self.assertTrue(summary["vendor_priority"])

    def test_new_report_invalidates_context_but_identical_proof_does_not_reopen_review(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        match = finding.distro_match
        match.review_required = False
        match.save()
        revisions = match.history.count()
        original_context = match.snapshot["package_check"]["context_hash"]
        self.relax()
        self.send(self.data(sequence=2))
        agents.process_pending()
        match = Finding.objects.get().distro_match
        self.assertTrue(match.inputs_changed)
        distro_cves.evaluate_device(self.device.pk)
        match = Finding.objects.get().distro_match
        self.assertFalse(match.inputs_changed)
        self.assertFalse(match.review_required)
        self.assertEqual(match.history.count(), revisions)
        self.assertEqual(match.snapshot["package_check"]["context_hash"], original_context)
