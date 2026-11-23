"""Classify safe failures and retain atomic evidence when local publication aborts."""

from unittest.mock import patch
from django.test import SimpleTestCase
from django.urls import reverse
from .connectors.http import ConnectorError
from . import agents, distro_cves, distro_errors
from .models import AgentDevice, DistroAdvisory, DistroMatchRevision, Finding
from .tests import Fixture


class DiagnosticTests(SimpleTestCase):
    def test_all_local_limits_are_specific_and_unknown_messages_are_withheld(self):
        for code, row in distro_errors.CAUSES.items():
            with self.subTest(code=code):
                value = distro_errors.failure(ConnectorError(row[0]))
                self.assertEqual(value["error_code"], code)
                self.assertTrue(value["next_action"])
        for exc in (ConnectorError("secret-token-sentinel"), ValueError("secret-token-sentinel")):
            value = distro_errors.failure(exc)
            self.assertEqual(value["error_code"], "unclassified")
            self.assertNotIn("secret-token-sentinel", str(value))
        self.assertEqual(distro_errors.diagnostic(["match_limit"]), {})
        self.assertEqual(distro_errors.diagnostic("secret-token-sentinel"), {})


class FailureRetentionTests(Fixture):
    from .test_distro_cves import DistroTests as _Distro

    legacy_manual_projection = False
    setUp = _Distro.setUp
    post = _Distro.post
    enroll = _Distro.enroll
    data = _Distro.data
    send = _Distro.send
    relax = _Distro.relax
    load = _Distro.load

    def test_worker_records_safe_cause_and_rolls_back_partial_publication_then_recovers(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        original = Finding.objects.get()
        original.analyst_applicability = "affected"
        original.status = "confirmed"
        original.save()
        revisions = DistroMatchRevision.objects.count()
        component = self.device.components.get(manager="dpkg", name="nginx")
        retained_check = component.distro_check
        AgentDevice.objects.filter(pk=self.device.pk).update(distro_requested=True)
        real_evaluate = distro_cves.evaluate_device

        def abort(pk):
            real_evaluate(pk)
            Finding.objects.filter(pk=original.pk).update(explanation="Partial write must roll back")
            raise ConnectorError(distro_errors.CAUSES["publication_timeout"][0])

        with patch("portal.distro_cves.evaluate_device", side_effect=abort):
            distro_cves.run(limit=1)
        self.device.refresh_from_db()
        original.refresh_from_db()
        component.refresh_from_db()
        self.assertEqual(self.device.distro_summary["error_code"], "publication_timeout")
        self.assertEqual(self.device.distro_summary["state"], "error")
        self.assertFalse(self.device.distro_requested)
        self.login()
        response = self.client.get(
            reverse("agent-center", args=[self.a.slug]), {"device": str(self.device.pk)}
        )
        self.assertContains(response, "No current package verdict is available")
        self.assertContains(response, "publication_timeout")
        self.assertContains(response, "inspect publication/database performance")
        self.assertNotContains(response, "0 packages · 0 vendor definitions checked")
        self.assertNotEqual(original.explanation, "Partial write must roll back")
        self.assertEqual(original.analyst_applicability, "affected")
        self.assertEqual(original.status, "confirmed")
        self.assertEqual(DistroMatchRevision.objects.count(), revisions)
        self.assertEqual(component.distro_check, retained_check)
        AgentDevice.objects.filter(pk=self.device.pk).update(distro_requested=True)
        distro_cves.run(limit=1)
        self.device.refresh_from_db()
        self.assertNotEqual(self.device.distro_summary["state"], "error")
        self.assertNotIn("error_code", self.device.distro_summary)

    def test_more_than_2000_matches_publish_completely_and_overflow_still_rolls_back(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        advisory = DistroAdvisory.objects.get()
        advisory.metadata = {**advisory.metadata, "cves": [f"CVE-2099-{n:05d}" for n in range(10000, 12001)]}
        advisory.save(update_fields=["metadata"])
        with patch("portal.distro_cves.MAX_MATCHES", 2000):
            distro_cves.run(limit=1)
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["error_code"], "match_limit")
        self.assertFalse(Finding.objects.exists())
        self.assertFalse(DistroMatchRevision.objects.exists())
        AgentDevice.objects.filter(pk=self.device.pk).update(distro_requested=True)
        distro_cves.run(limit=1)
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["state"], "ready")
        self.assertEqual(self.device.distro_summary["potential"], 2001)
        self.assertEqual(Finding.objects.count(), 2001)
        self.assertEqual(DistroMatchRevision.objects.count(), 2001)
        component = self.device.components.get(manager="dpkg", name="nginx")
        self.assertEqual(component.distro_check["counts"]["potential"], 2001)
