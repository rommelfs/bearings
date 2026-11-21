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
        self.assertEqual(response.context["severity_counts"][2]["count"], 1)
        self.assertEqual(response.context["severity_counts"][1]["count"], 0)
        save_browser_evidence("queue-pip-esm", response)
        self.assertEqual((finding.analyst_applicability, finding.status), ("unassessed", "new"))
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
        self.assertContains(fixed, "includes the vendor fix")
        self.assertNotContains(fixed, "Which update addresses this package?")
        save_browser_evidence("queue-pip-esm-fixed", fixed)
        finding.refresh_from_db()
        self.assertEqual((finding.analyst_applicability, finding.status), ("unassessed", "new"))
