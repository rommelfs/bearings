"""Concrete, bounded company next steps never turn review totals into vulnerability verdicts."""

import uuid
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext
from .tests import Fixture
from .models import AgentComponent, AgentDevice, AgentReport, Asset, Installation


class OverviewNextStepsTests(Fixture):
    from .test_overview_cleanup import OverviewCleanupTests as _Overview

    package = _Overview.package
    reporter = _Overview.reporter

    def view(self):
        self.login()
        return self.client.get(reverse("overview"))

    def test_recorded_error_identifies_host_role_cause_and_exact_device_route(self):
        device, _ = self.reporter(state="error")
        device.distro_summary = {
            "state": "error",
            "message": "Evaluation deferred (TypeError); retained evidence needs review.",
        }
        device.save()
        response = self.view()
        step = response.context["companies"][0]["next_steps"][0]
        self.assertEqual(step["host"], self.asset.name)
        self.assertEqual(step["owner"], "Platform operator")
        self.assertIn("TypeError", step["reason"])
        self.assertIn(str(device.pk), step["url"])
        self.assertTrue(step["url"].endswith("#automatic-cves"))
        self.assertContains(response, "Next steps")
        self.assertContains(response, "not counts of confirmed vulnerable installations")
        self.assertContains(response, '<details class="overview-diagnostics">')

    def test_classified_limit_explains_cause_and_does_not_echo_arbitrary_message(self):
        device, _ = self.reporter(state="error")
        device.distro_summary = {"state": "error", "error_code": "match_limit", "message": "secret-sentinel"}
        device.save()
        response = self.view()
        step = response.context["companies"][0]["next_steps"][0]
        self.assertIn("10,000 package/definition/CVE matches", step["reason"])
        self.assertIn("restarting the Linux client will not change this limit", step["reason"])
        self.assertNotContains(response, "secret-sentinel")

    def test_expired_credential_and_recent_receipt_have_different_recovery_instructions(self):
        device, _ = self.reporter(state="ready")
        device.expires_at = timezone.now() - timedelta(seconds=1)
        device.save()
        step = self.view().context["companies"][0]["next_steps"][0]
        self.assertEqual(step["title"], "Renew client credentials")
        device.expires_at = timezone.now() + timedelta(days=1)
        device.last_observed_at = timezone.now() - timedelta(days=1)
        device.last_received_at = timezone.now()
        device.save()
        step = self.view().context["companies"][0]["next_steps"][0]
        self.assertEqual(step["title"], "Check receipt processing and report timestamps")
        device.last_received_at = None
        device.save()
        self.assertEqual(
            self.view().context["companies"][0]["next_steps"][0]["title"], "Restore server reporting"
        )

    def test_untrusted_messages_are_not_exposed_and_cross_source_examples_are_excluded(self):
        device, _ = self.reporter(state="error")
        device.distro_summary = {"state": "error", "message": "secret-credential-sentinel"}
        device.save()
        self.asset.name = '<img src=x onerror="alert(1)">'
        self.asset.save()
        response = self.view()
        self.assertNotContains(response, "secret-credential-sentinel")
        self.assertContains(response, "no classified cause")
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertContains(response, "&lt;img")
        AgentDevice.objects.filter(pk=device.pk).update(source=self.sb)
        state = self.view().context["companies"][0]
        self.assertEqual(state["device_examples_shown"], 0)

    def test_saved_affected_assessment_is_prioritized_without_granting_configuration_access(self):
        self.reporter(state="error")
        finding = self.record_finding()
        finding.analyst_applicability = "affected"
        finding.save()
        response = self.view()
        self.assertEqual(
            response.context["companies"][0]["next_steps"][0]["title"],
            "Review remediation for confirmed cases",
        )
        self.assertIn("no-store", response["Cache-Control"])
        self.login(self.reader)
        response = self.client.get(reverse("overview"))
        self.assertNotContains(response, reverse("configuration", args=[self.a.slug]))
        self.assertContains(response, reverse("organization", args=[self.a.slug]) + "#contacts")

    def test_large_fleet_examples_and_primary_steps_are_bounded_without_per_host_queries(self):
        device, report = self.reporter(state="error")
        component = AgentComponent.objects.get(device=device)
        self.view()
        with CaptureQueriesContext(connection) as small:
            self.view()
        for index in range(12):
            asset = Asset.objects.create(organization=self.a, source=self.sa, name=f"Synthetic host {index}")
            other = AgentDevice.objects.create(
                organization=self.a,
                source=self.sa,
                asset=asset,
                public_key=f"synthetic-next-step-{index}",
                expires_at=device.expires_at,
                last_observed_at=timezone.now(),
                distro_summary={"state": "error"},
            )
            receipt = AgentReport.objects.create(
                id=uuid.uuid4(),
                device=other,
                sequence=1,
                observed_at=timezone.now(),
                body=b"{}",
                body_hash="synthetic",
                component_count=1,
                status="applied",
            )
            installation = Installation.objects.create(asset=asset, product=self.product, version="1")
            AgentComponent.objects.create(
                device=other,
                key=component.key,
                manager="dpkg",
                name="nginx",
                architecture="amd64",
                version="1",
                observed_at=timezone.now(),
                last_report=receipt,
                installation=installation,
            )
        with CaptureQueriesContext(connection) as large:
            response = self.view()
        state = response.context["companies"][0]
        self.assertEqual(state["package_errors"], 13)
        self.assertEqual(state["device_examples_shown"], 3)
        self.assertLessEqual(len(state["next_steps"]), 5)
        self.assertLessEqual(len(large), len(small) + 1)
