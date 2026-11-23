"""Classify safe failures and retain atomic evidence when local publication aborts."""

from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from django.test import SimpleTestCase, TransactionTestCase
from django.db import connection, connections, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .connectors.http import ConnectorError
from . import agents, distro_cves, distro_errors
from .models import AgentDevice, DistroAdvisory, DistroMatchRevision, Finding, AssetIssue, IssueRevision
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
        with CaptureQueriesContext(connection) as queries:
            distro_cves.run(limit=1)
        self.assertLess(len(queries), 700, "Publication must batch, not issue queries per match")
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["state"], "ready")
        self.assertEqual(self.device.distro_summary["potential"], 2001)
        self.assertEqual(Finding.objects.count(), 2001)
        self.assertEqual(DistroMatchRevision.objects.count(), 2001)
        component = self.device.components.get(manager="dpkg", name="nginx")
        self.assertEqual(component.distro_check["counts"]["potential"], 2001)

    def test_late_batch_failure_rolls_back_and_repetition_preserves_reviews_and_issue_history(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        finding.status = "resolved"
        finding.analyst_applicability = "not_affected"
        finding.save()
        match = finding.distro_match
        match.review_required = False
        match.save()
        check = self.device.components.get(name="nginx").distro_check
        advisory = DistroAdvisory.objects.get()
        advisory.metadata = {
            **advisory.metadata,
            "cves": [finding.record.external_id, "CVE-2099-10001", "CVE-2099-10002"],
        }
        advisory.save(update_fields=["metadata"])
        AgentDevice.objects.filter(pk=self.device.pk).update(distro_requested=True)
        with (
            patch("portal.distro_publish.BATCH_SIZE", 2),
            patch(
                "portal.distro_publish.time.monotonic",
                side_effect=lambda: float("inf") if IssueRevision.objects.count() > 1 else 0,
            ),
        ):
            distro_cves.run(limit=1)
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["error_code"], "publication_timeout")
        self.assertEqual(Finding.objects.count(), 1)
        self.assertEqual(AssetIssue.objects.count(), 1)
        self.assertEqual(IssueRevision.objects.count(), 1)
        self.assertEqual(DistroMatchRevision.objects.count(), 1)
        self.assertEqual(self.device.components.get(name="nginx").distro_check, check)
        distro_cves.evaluate_device(self.device.pk)
        distro_cves.evaluate_device(self.device.pk)
        finding.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(finding.status, "resolved")
        self.assertEqual(finding.analyst_applicability, "not_affected")
        self.assertFalse(match.review_required)
        self.assertEqual(Finding.objects.count(), 3)
        self.assertEqual(AssetIssue.objects.count(), 3)
        self.assertEqual(IssueRevision.objects.count(), 3)
        self.assertEqual(DistroMatchRevision.objects.count(), 3)

    def test_publication_upgrade_retries_old_timeout_once_without_removing_failure_backoff(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        failed_at = timezone.now()
        old = {"evaluator_version": 2, "state": "error", "error_code": "publication_timeout"}
        AgentDevice.objects.filter(pk=self.device.pk).update(
            distro_requested=False, distro_checked_at=failed_at, distro_summary=old
        )
        distro_cves.run(limit=1)
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["state"], "ready")
        AgentDevice.objects.filter(pk=self.device.pk).update(
            distro_requested=False,
            distro_checked_at=failed_at,
            distro_summary={**old, "publication_version": distro_cves.PUBLICATION_VERSION},
        )
        distro_cves.run(limit=1)
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["state"], "error")
        self.assertFalse(self.device.distro_requested)
        self.assertEqual(self.device.distro_checked_at, failed_at)

    def test_changed_vendor_payload_keeps_old_revision_and_restricted_sharing(self):
        from .test_distro_cves import XML

        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        record = finding.record
        old_payload = record.payload
        record.shareable = False
        record.save(update_fields=["shareable"])
        self.load(
            XML.replace("<severity>High</severity>", "<severity>Low</severity>").replace(
                "Synthetic vendor fixture, not operational intelligence", "Changed synthetic vendor evidence"
            )
        )
        distro_cves.evaluate_device(self.device.pk)
        record.refresh_from_db()
        finding.refresh_from_db()
        self.assertFalse(record.shareable)
        self.assertEqual(record.source_severity, "low")
        self.assertNotEqual(record.payload, old_payload)
        self.assertEqual(record.revisions.count(), 2)
        self.assertTrue(record.revisions.filter(payload=old_payload).exists())
        self.assertEqual(finding.distro_match.evidence_revision.payload, record.payload)

    def test_batch_matches_reference_evidence_and_issue_projection(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        advisory = DistroAdvisory.objects.get()
        advisory.metadata = {
            **advisory.metadata,
            "cves": ["CVE-2099-10001", "CVE-2099-10002", "CVE-2099-10003"],
        }
        advisory.save(update_fields=["metadata"])

        def reference(device, feed, rows, deadline):
            for component, rule, cve, result, proof in rows:
                distro_cves.publish(device, feed, component, rule, cve, result, proof)

        def retained():
            data = []
            for finding in Finding.objects.select_related("record", "distro_match", "asset_issue").order_by(
                "record__external_id"
            ):
                match = finding.distro_match
                issue = finding.asset_issue
                data.append(
                    (
                        finding.record.external_id,
                        finding.record.payload,
                        finding.record.source_severity,
                        finding.record.shareable,
                        finding.applicability,
                        finding.analyst_applicability,
                        finding.explanation,
                        finding.status,
                        finding.priority,
                        match.input_hash,
                        match.snapshot,
                        match.review_required,
                        match.evidence_revision.payload,
                        issue.title,
                        issue.kind,
                        issue.source_label,
                        issue.evidence_text,
                        finding.record.revisions.count(),
                        match.history.count(),
                        issue.revisions.count(),
                    )
                )
            return data

        with transaction.atomic():
            with patch("portal.distro_publish.publish_many", side_effect=reference):
                distro_cves.evaluate_device(self.device.pk)
            expected = retained()
            transaction.set_rollback(True)
        with patch("portal.distro_publish.BATCH_SIZE", 2):
            distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(retained(), expected)


@skipUnless(connection.vendor == "postgresql", "Row lock ordering requires PostgreSQL")
class PublicationLockTests(TransactionTestCase):
    from .test_distro_cves import DistroTests as _Distro

    legacy_manual_projection = False
    post = _Distro.post
    enroll = _Distro.enroll
    data = _Distro.data
    send = _Distro.send
    load = _Distro.load

    def setUp(self):
        Fixture.setUpTestData.__func__(type(self))
        self._Distro.setUp(self)

    def test_human_finding_then_record_lock_and_later_batch_publication_do_not_deadlock(self):
        from . import distro_publish
        from .models import SourceRecord

        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        entered = Event()
        real_lock = distro_publish.lock_findings

        def lock(device):
            entered.set()
            return real_lock(device)

        def evaluate():
            try:
                return distro_cves.evaluate_device(self.device.pk)
            finally:
                connections.close_all()

        with patch("portal.distro_publish.lock_findings", side_effect=lock):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    reviewed = Finding.objects.select_for_update().get(pk=finding.pk)
                    future = pool.submit(evaluate)
                    self.assertTrue(entered.wait(5))
                    # Risk linking must still be able to lock its evidence while
                    # the evaluator waits for the human's Finding lock.
                    SourceRecord.objects.select_for_update(nowait=True).get(pk=reviewed.record_id)
                    reviewed.analyst_applicability = "not_affected"
                    reviewed.status = "resolved"
                    reviewed.save(update_fields=["analyst_applicability", "status"])
                self.assertIsNotNone(future.result(timeout=15))
        finding.refresh_from_db()
        self.assertEqual(finding.analyst_applicability, "not_affected")
        self.assertEqual(finding.status, "resolved")
