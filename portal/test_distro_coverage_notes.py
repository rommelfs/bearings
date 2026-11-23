"""Coverage limits describe evidence, not invented host repairs."""

import uuid
from django.test import SimpleTestCase
from django.utils import timezone
from django.urls import reverse
from .tests import Fixture
from . import agents, distro_cves, distro_coverage_notes


class ExplanationTests(SimpleTestCase):
    def test_feed_wide_limits_and_unknown_summary_do_not_create_host_fixes(self):
        note = distro_coverage_notes.explain({"unindexed_definitions": 72})
        self.assertFalse(note["actionable"])
        self.assertIn("72 definitions in the entire vendor feed", note["reason"])
        self.assertIn("relevance to this host is unknown", note["reason"])
        note = distro_coverage_notes.explain(
            {"missing_source_metadata": True, "uncertain": "secret-sentinel"}
        )
        self.assertFalse(note["actionable"])
        self.assertIn("does not identify", note["reason"])
        self.assertNotIn("secret-sentinel", note["reason"])


class OverviewLimitTests(Fixture):
    from .test_overview_cleanup import OverviewCleanupTests as _Overview

    package = _Overview.package
    reporter = _Overview.reporter

    def page(self, summary):
        device, _ = self.reporter()
        device.distro_summary = {"state": "partial", **summary}
        device.save()
        self.login()
        return device, self.client.get(reverse("overview"))

    def test_partial_rule_and_feed_limits_are_information_outside_next_steps(self):
        device, response = self.page(
            {"unindexed_definitions": 72, "unsupported_conditions": 2, "uncertain": 3}
        )
        state = response.context["companies"][0]
        self.assertEqual(len(state["coverage_notes"]), 1)
        self.assertTrue(all(step.get("host") != device.asset.name for step in state["next_steps"]))
        self.assertContains(response, "Coverage limitations · information")
        self.assertContains(response, "72 definitions in the entire vendor feed")
        self.assertContains(response, "2 vendor definitions associated with reported package names")
        self.assertNotContains(response, "Resolve incomplete package coverage")
        self.assertContains(response, "not repair tasks or confirmed vulnerabilities")

    def test_feed_notes_are_grouped_and_do_not_hide_a_fourth_actionable_client(self):
        from .models import AgentDevice, AgentReport, AgentComponent, Asset, Installation

        first, _ = self.page({"unindexed_definitions": 72})
        for n in range(3):
            asset = Asset.objects.create(organization=self.a, source=self.sa, name=f"Synthetic limit {n}")
            installation = Installation.objects.create(asset=asset, product=self.product, version="1")
            summary = {
                "state": "partial",
                **({"missing_source_metadata": 2} if n == 2 else {"unindexed_definitions": 72}),
            }
            device = AgentDevice.objects.create(
                organization=self.a,
                source=self.sa,
                asset=asset,
                public_key=f"synthetic-limit-{n}",
                expires_at=first.expires_at,
                last_observed_at=timezone.now(),
                distro_checked_at=timezone.now(),
                distro_summary=summary,
            )
            report = AgentReport.objects.create(
                id=uuid.uuid4(),
                device=device,
                sequence=1,
                observed_at=timezone.now(),
                body=b"{}",
                body_hash="synthetic",
                status="applied",
                component_count=1,
            )
            AgentComponent.objects.create(
                device=device,
                key="dpkg:nginx:amd64",
                name="nginx",
                manager="dpkg",
                architecture="amd64",
                version="1",
                observed_at=timezone.now(),
                last_report=report,
                installation=installation,
            )
        response = self.client.get(reverse("overview"))
        state = response.context["companies"][0]
        self.assertEqual(state["device_examples_shown"], 3)
        self.assertEqual(len(state["coverage_notes"]), 1)
        self.assertEqual(len(state["coverage_notes"][0]["devices"]), 2)
        self.assertTrue(any(s["title"] == "Supply missing source-package facts" for s in state["next_steps"]))

    def test_missing_source_facts_produce_specific_action_with_count(self):
        device, response = self.page({"missing_source_metadata": 2})
        state = response.context["companies"][0]
        step = next(s for s in state["next_steps"] if s.get("host") == device.asset.name)
        self.assertEqual(step["title"], "Supply missing source-package facts")
        self.assertIn("2 reported Debian packages", step["reason"])
        self.assertIn(str(device.pk), step["url"])
        self.assertEqual(state["coverage_notes"], [])


class PackageExampleTests(Fixture):
    from .test_distro_cves import DistroTests as _Distro

    legacy_manual_projection = False
    setUp = _Distro.setUp
    post = _Distro.post
    enroll = _Distro.enroll
    data = _Distro.data
    send = _Distro.send
    load = _Distro.load

    def prepare(self, total=1):
        from .test_distro_cves import XML

        self.enroll()
        report = self.data()
        if total > 1:
            report["components"] = [
                {
                    **report["components"][0],
                    "key": f"dpkg:nginx:synthetic-{n}",
                    "architecture": f"synthetic-{n}",
                }
                for n in range(total)
            ]
        self.send(report)
        agents.process_pending()
        self.load(XML.replace("<l:evr ", "<l:signature_keyid ").replace("</l:evr>", "</l:signature_keyid>"))
        distro_cves.evaluate_device(self.device.pk)
        self.device.refresh_from_db()
        return self.device.components.filter(name="nginx").first()

    def test_scoped_current_package_example_names_version_and_reason_with_reader_route(self):
        component = self.prepare()
        summary = distro_cves.coverage(self.device)
        self.assertEqual(summary["state"], "partial")
        self.assertEqual(len(summary["examples"]), 1)
        example = summary["examples"][0]
        self.assertEqual(example["version"], component.version)
        self.assertIn("nginx", example["url"])
        self.login(self.reader)
        page = self.client.get(reverse("agent-center", args=[self.a.slug]), {"device": str(self.device.pk)})
        self.assertContains(page, "Package examples · up to five")
        self.assertContains(page, "Package-signature identity")
        self.assertEqual(self.client.get(example["url"]).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("agent-center", args=[self.b.slug]), {"device": str(self.device.pk)}
            ).status_code,
            404,
        )

    def test_queued_changed_and_foreign_package_inputs_never_become_current_examples(self):
        component = self.prepare()
        self.device.distro_requested = True
        self.assertEqual(distro_cves.coverage(self.device)["examples"], [])
        self.device.distro_requested = False
        component.version = "different-input"
        component.save(update_fields=["version"])
        self.assertEqual(distro_cves.coverage(self.device)["examples"], [])
        component.version = self.data()["components"][0]["version"]
        component.save(update_fields=["version"])
        report = component.last_report
        report.status = "pending"
        report.save(update_fields=["status"])
        self.assertEqual(distro_cves.coverage(self.device)["examples"], [])
        report.status = "applied"
        report.save(update_fields=["status"])
        from .models import Installation, Product

        foreign = Installation.objects.create(
            asset=self.other,
            product=Product.objects.create(organization=self.b, name="Foreign synthetic package"),
        )
        component.installation = foreign
        component.save(update_fields=["installation"])
        self.assertEqual(distro_cves.coverage(self.device)["examples"], [])

    def test_examples_are_bounded_and_ignore_changed_feed_generation(self):
        self.prepare(total=14)
        self.assertEqual(len(distro_cves.coverage(self.device)["examples"]), 5)
        self.device.distro_summary["generation"] = "old-generation"
        self.assertEqual(distro_cves.coverage(self.device)["examples"], [])
