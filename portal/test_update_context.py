"""Explain independent priorities and the actual Ubuntu pip/urllib3 ESM fix."""

import copy
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from django.template.loader import render_to_string
from django.utils import timezone
from django.test import SimpleTestCase
from . import agents, distro_cves, distro_oval
from .distro_verdicts import update_context
from .models import DistroFeed, Finding
from .presentation import vulnerability_summary
from .test_distro_cves import DistroTests
from .test_package_verdicts import save_browser_evidence


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/oval/ubuntu-noble-CVE-2025-66471.json").read_text())


class ContextTests(SimpleTestCase):
    def match(self):
        return SimpleNamespace(
            snapshot={"feed": "ubuntu:24.04"},
            component=SimpleNamespace(name="python3-pip-whl", manager="dpkg"),
            advisory=SimpleNamespace(metadata=fixture()["definition"]["metadata"]),
        )

    def proof(self):
        return {
            "verdict": "affected",
            "comparisons": [
                {
                    "operation": "less than",
                    "matches": True,
                    "vendor_version": "24.0+dfsg-1ubuntu1.3+esm3",
                    "installed_version": "24.0+dfsg-1ubuntu1.3",
                    "basis": "binary package",
                }
            ],
            "vendor_comments": [
                "python-pip source package in esm-apps/noble, is affected and has been fixed (note: '24.0+dfsg-1ubuntu1.3+esm3')."
            ],
        }

    def test_fix_target_requires_explicit_vendor_fix_and_matching_component_condition(self):
        match, proof = self.match(), self.proof()
        context = update_context(match, proof)
        self.assertTrue(context["esm_apps"])
        self.assertEqual(context["targets"][0]["version"], "24.0+dfsg-1ubuntu1.3+esm3")
        self.assertEqual(context["check_command"], "apt-cache policy python3-pip-whl")
        self.assertIn("bundled copy", context["package_context"])
        for field, value in [("operation", "greater than"), ("matches", False)]:
            changed = copy.deepcopy(proof)
            changed["comparisons"][0][field] = value
            self.assertEqual(update_context(match, changed)["targets"], [])
        changed = copy.deepcopy(proof)
        changed["vendor_comments"] = ["Other sibling fixed at 99"]
        self.assertFalse(update_context(match, changed)["targets"])
        self.assertFalse(update_context(match, changed)["esm_apps"])
        changed = copy.deepcopy(proof)
        changed["verdict"] = "fixed"
        self.assertFalse(update_context(match, changed)["targets"])

    def test_esm_infra_requires_a_fix_note_for_the_same_boundary(self):
        match, proof = self.match(), self.proof()
        match.snapshot["feed"] = "ubuntu:20.04"
        match.component.name = "php7.4-fpm"
        proof["vendor_comments"] = [
            "php7.4 source package in esm-infra/focal is affected and has been fixed "
            "(note: '24.0+dfsg-1ubuntu1.3+esm3')."
        ]
        context = update_context(match, proof)
        self.assertTrue(context["esm_infra"])
        self.assertFalse(context["esm_apps"])
        self.assertEqual(context["channels"], ["Ubuntu ESM Infra / Ubuntu Pro"])
        proof["vendor_comments"][0] = proof["vendor_comments"][0].replace("+esm3", "+esm99")
        self.assertEqual(update_context(match, proof)["channels"], [])
        # Do not infer a channel from a version suffix or unrelated vendor prose.
        proof["vendor_comments"] = ["Some packages are in esm-infra/focal"]
        self.assertEqual(update_context(match, proof)["targets"], [])

    def test_non_ubuntu_non_pip_and_unsafe_names_do_not_get_invented_context(self):
        match = self.match()
        match.snapshot["feed"] = "debian:12"
        context = update_context(match, self.proof())
        self.assertFalse(context["esm_apps"])
        self.assertEqual(context["package_context"], "")
        match = self.match()
        match.component.name = "other"
        self.assertEqual(update_context(match, self.proof())["package_context"], "")
        match.component.name = "pip; touch /tmp/unsafe"
        self.assertEqual(update_context(match, self.proof())["check_command"], "")

    def test_cvss_high_and_ubuntu_medium_are_independent_labeled_scales(self):
        payload = {
            "bearings_distro": {
                "schema": "bearings.distro-oval.v1",
                "feed": "ubuntu:24.04",
                "severity": "medium",
            },
            "containers": {"cna": {"metrics": [{"cvssV4_0": {"version": "4.0", "baseScore": 8.9}}]}},
        }
        summary = vulnerability_summary(payload)
        self.assertEqual(
            (summary["severity"], summary["score_severity"], summary["score_key"]), ("Medium", "High", "high")
        )
        finding = SimpleNamespace(
            source_summary=summary, severity_key="medium", organization=SimpleNamespace(slug="alpha"), pk=1
        )
        html = render_to_string("portal/severity.html", {"finding": finding})
        self.assertIn("CVSS 4.0 High 8.9", html)
        self.assertIn("Ubuntu priority", html)
        self.assertIn("severity-badge severity-high", html)
        self.assertIn("severity-badge severity-medium", html)
        self.assertIn("sorts by vendor priority", html)


class UbuntuUpdateTests(DistroTests):
    def test_real_pip_rule_explains_esm_fix_and_separate_urllib3_update(self):
        data = fixture()
        feed = DistroFeed.objects.create(
            key="ubuntu:24.04",
            generation=uuid.uuid4(),
            last_success=timezone.now(),
            summary={"compiler_version": distro_oval.COMPILER_VERSION},
        )
        distro_cves.store_batch(feed, feed.generation, [data["definition"]])
        self.enroll()
        report = self.data(version="24.0+dfsg-1ubuntu1.3")
        report["components"][0].update(name="python3-pip-whl", key="dpkg:python3-pip-whl:amd64")
        self.send(report)
        agents.process_pending()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        self.assertEqual(finding.distro_match.snapshot["package_check"]["verdict"], "affected")
        self.login()
        response = self.client.get("/reviews/")
        for text in [
            "Ubuntu priority",
            "Filter counts use vendor priority when supplied",
            "CVSS 4.0 High 8.9",
            "Ubuntu ESM Apps / Ubuntu Pro",
            "24.0+dfsg-1ubuntu1.3+esm3",
            "Availability on this host: not checked",
            "apt-cache policy python3-pip-whl",
            "bundled copy of urllib3",
        ]:
            self.assertContains(response, text)
        asset_url = self.url("asset", pk=self.device.asset_id)
        intelligence_url = self.url("intelligence")
        evidence_url = intelligence_url + f"?case={finding.pk}"
        for url in (asset_url, intelligence_url, evidence_url):
            preview = self.client.get(url)
            self.assertContains(preview, "Vendor-listed fix:")
            self.assertContains(preview, "Ubuntu ESM Apps / Ubuntu Pro")
            self.assertContains(preview, "24.0+dfsg-1ubuntu1.3+esm3")
            self.assertContains(preview, "Repository update availability has not been checked.")
        machine = self.client.get(intelligence_url, {"view": "machine"}).context["page"][0]
        self.assertEqual((machine["affected_cves"], machine["unverified_cves"]), (1, 0))
        self.assertEqual(float(machine["max_cvss"]), 8.9)
        self.assertEqual(response.context["severity_counts"][2]["count"], 1)
        self.assertEqual(response.context["severity_counts"][1]["count"], 0)
        save_browser_evidence("queue-pip-esm", response)
        self.assertEqual((finding.analyst_applicability, finding.status), ("unassessed", "new"))
        self.login(self.analyst)
        national = self.client.get("/circl/findings/?view=records")
        self.assertEqual(national.status_code, 200)
        save_browser_evidence("national-esm-fix", national)
        self.assertContains(national, "Vendor-listed fix")
        self.assertContains(national, "Ubuntu ESM Apps / Ubuntu Pro")
        self.assertContains(national, "Saved analyst decision")
        self.assertContains(national, "not distinct CVE counts")
        self.assertNotContains(national, "Build unknown")
        # A changed package input must suppress the old fix recommendation.
        component = finding.distro_match.component
        old_version = component.version
        component.version = "99"
        component.save(update_fields=["version"])
        stale = self.client.get("/circl/findings/?view=records&assessment=pending")
        self.assertEqual(self.client.get("/circl/findings/?view=records").context["page"].paginator.count, 0)
        self.assertContains(stale, "Awaiting current package evaluation")
        self.assertNotContains(stale, "Vendor-listed fix")
        self.login()
        for url in (asset_url, intelligence_url, evidence_url):
            self.assertNotContains(self.client.get(url), "Vendor-listed fix:")
        machine = self.client.get(intelligence_url, {"view": "machine"}).context["page"][0]
        self.assertEqual((machine["affected_cves"], machine["unverified_cves"]), (0, 1))
        self.assertIsNone(machine["max_cvss"])
        component.version = old_version
        component.save(update_fields=["version"])
        self.login()
        # A current fixed package must leave the action list without claiming
        # that an operator enabled ESM, installed anything or resolved workflow.
        self.relax()
        report = self.data(sequence=2, version="24.0+dfsg-1ubuntu1.3+esm3")
        report["components"][0].update(name="python3-pip-whl", key="dpkg:python3-pip-whl:amd64")
        self.send(report)
        agents.process_pending()
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(self.client.get("/reviews/").context["review_total"], 0)
        fixed = self.client.get("/reviews/?state=cleared")
        self.login(self.analyst)
        self.assertEqual(self.client.get("/circl/findings/?view=records").context["page"].paginator.count, 0)
        national_fixed = self.client.get("/circl/findings/?view=records&assessment=cleared")
        self.assertContains(national_fixed, "includes the vendor fix")
        self.assertNotContains(national_fixed, "Vendor-listed fix")
        self.login()
        self.assertContains(fixed, "includes the vendor fix")
        self.assertNotContains(fixed, "Which update addresses this package?")
        save_browser_evidence("queue-pip-esm-fixed", fixed)
        finding.refresh_from_db()
        self.assertEqual((finding.analyst_applicability, finding.status), ("unassessed", "new"))
