from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from . import flowintel, notifications, remediation
from .connectors.http import ConnectorError
from .models import Contact, Finding, FlowIntelInstance, RemediationReservation, SourceRecord
from .test_flowintel import FakeAPI
from .tests import Fixture


class RemediationTests(Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.installation.version = "1.2.3"
        self.installation.save(update_fields=["version"])
        self.instance = FlowIntelInstance.objects.create(
            name="Private test",
            base_url="https://cases.example.invalid",
            bearings_url="https://bearings.example.invalid",
            token_env_var="FLOWINTEL_FIXTURE_TOKEN",
            service_org_id=3,
        )
        self.contact.notification_enabled = True
        self.contact.reachable_at = self.contact.reviewed_at = timezone.now()
        self.contact.next_review = timezone.localdate() + timedelta(days=30)
        self.contact.save()
        self.fake = FakeAPI(self.instance)
        api_patch = patch("portal.flowintel.api", side_effect=self.fake)
        self.mock_api = api_patch.start()
        self.addCleanup(api_patch.stop)

    def extra_finding(self, identifier, *, shareable=True):
        record = SourceRecord.objects.create(
            organization=self.a,
            source="fixture://vendor",
            external_id=identifier,
            payload={},
            shareable=shareable,
        )
        return Finding.objects.create(
            organization=self.a,
            record=record,
            installation=self.installation,
            explanation="Additional vendor proof",
        )

    def draft(self, *, cve=None, recipients=(), mitigation=None):
        return remediation.preview(
            self.analyst,
            self.a,
            asset=None if cve else self.asset.pk,
            cve=cve,
            instance=self.instance,
            deadline=None,
            contact_ids=list(recipients),
            mitigation=mitigation,
        )

    def run_case(self, case, steps):
        for _ in range(steps):
            call_command("process_flowintel", case=case.pk, verbosity=0)
        case.refresh_from_db()

    def mitigation(self):
        self.finding.analyst_applicability = "affected"
        self.finding.save(update_fields=["analyst_applicability"])
        return {
            "finding": self.finding.pk,
            "action": "Disable the affected synthetic module",
            "source": "FIXTURE-ADVISORY-42",
            "verification": "Confirm module is disabled and test expected access",
        }

    def test_two_endpoints_share_a_durable_claim(self):
        self.login(self.analyst)
        urls = [
            self.url("remediation-cve", cve=self.finding.record.external_id),
            self.url("remediation-machine", pk=self.asset.pk),
        ]
        landing = self.client.get(self.url("intelligence"), {"view": "machine"})
        self.assertContains(landing, urls[1])
        self.assertContains(self.client.get(self.url("intelligence")), urls[0])
        self.assertContains(landing, "Notify about this machine")
        for query in ({}, {"case": self.finding.pk}, {"finding": self.finding.pk}):
            self.assertContains(self.client.get(self.url("intelligence"), query), "Notify about this CVE")
        self.assertContains(self.client.get(self.url("asset", pk=self.asset.pk)), "Notify about this machine")
        for url in urls:
            self.assertContains(self.client.get(url), "Preview notification")
        self.assertEqual(self.client.get(self.url("remediation-machine", pk=self.other.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("remediation-cve", cve="not-a-cve")).status_code, 404)
        first, _ = self.draft(cve=self.finding.record.external_id)
        second, _ = self.draft()
        self.mock_api.assert_not_called()
        flowintel.approve(self.analyst, first.pk)
        with self.assertRaisesMessage(ValidationError, "already approved"):
            flowintel.approve(self.analyst, second.pk)
        self.assertEqual(RemediationReservation.objects.count(), 1)
        self.assertContains(self.client.get(urls[1]), str(first.pk))
        self.login(self.admin)
        self.assertEqual(self.client.get(urls[1]).status_code, 403)
        self.assertEqual(self.client.get(self.url("flowintel-case", pk=first.pk)).status_code, 404)

    def test_internal_review_has_no_mail_and_restricted_evidence_is_omitted(self):
        private = self.extra_finding("CVE-2025-90001", shareable=False)
        case, _ = self.draft()
        self.login(self.analyst)
        preview = self.client.get(self.url("flowintel-case", pk=case.pk))
        self.assertContains(preview, "Create internal FlowIntel tasks")
        self.assertNotContains(preview, "Send notification")
        self.assertEqual(case.snapshot["finding_ids"], [self.finding.pk])
        self.assertNotIn(private.record.external_id, case.tasks.get().description)
        with self.assertRaisesMessage(ValidationError, "no actionable items"):
            self.draft(recipients=[self.contact.pk])
        flowintel.approve(self.analyst, case.pk)
        self.run_case(case, 3)
        self.assertEqual(case.state, "linked")
        self.assertEqual(len(self.fake.writes), 2)
        self.assertTrue(self.fake.case["is_private"])
        self.assertEqual(case.remediation_batch.deliveries.count(), 0)

    def test_multiple_cves_share_a_package_task_and_keep_requirements(self):
        finding2 = self.extra_finding("CVE-2025-90002")
        targets = {
            self.finding.pk: [{"version": "1.2.4", "basis": "package", "channels": [], "installed": "1.2.3"}],
            finding2.pk: [
                {
                    "version": "1.2.5",
                    "basis": "package",
                    "channels": ["Ubuntu ESM Apps / Ubuntu Pro"],
                    "installed": "1.2.3",
                }
            ],
        }
        with patch("portal.remediation.target_rows", return_value=targets):
            case, _ = self.draft(recipients=[self.contact.pk])
            task = case.tasks.get()
            self.assertIn("1.2.5", task.description)
            self.assertIn("Ubuntu ESM Apps", task.description)
            self.assertIn(finding2.record.external_id, task.description)
            self.assertIn(self.finding.record.external_id, task.description)
            delivery = case.remediation_batch.deliveries.get()
            self.assertIn("candidate", delivery.body)
            self.assertEqual(delivery.findings.count(), 2)
            flowintel.approve(self.analyst, case.pk)
            by_cve, prior = self.draft(cve=finding2.record.external_id)
            self.assertIsNone(by_cve)
            self.assertEqual(prior, {case.pk})

    def test_release_file_only_after_verified_private_case_and_tasks(self):
        mitigation = self.mitigation()
        internal = self.extra_finding("CVE-2025-90003")
        with (
            TemporaryDirectory() as outbox,
            override_settings(EMAIL_FILE_PATH=outbox, NOTIFICATION_TRANSPORT="file"),
        ):
            self.login(self.analyst)
            response = self.client.post(
                self.url("remediation-machine", pk=self.asset.pk),
                {
                    "instance": self.instance.pk,
                    "recipients": [self.contact.pk],
                    "review": mitigation["finding"],
                    "source": mitigation["source"],
                    "verification": mitigation["verification"],
                    "action": mitigation["action"],
                },
            )
            self.assertEqual(response.status_code, 302)
            case = self.finding.flowintel_cases.get()
            preview = self.client.get(response.url)
            self.assertContains(preview, "Queue test notification")
            self.assertNotContains(preview, "Send notification")
            self.assertLess(
                preview.content.index(b"Queue test notification"), preview.content.index(b"<h2>Tasks</h2>")
            )
            delivery = case.remediation_batch.deliveries.get()
            self.assertIn("FIXTURE-ADVISORY-42", delivery.body)
            self.assertNotIn(internal.record.external_id, delivery.body)
            with self.assertRaisesMessage(ValidationError, "linked FlowIntel"):
                notifications.claim_batch(self.analyst, case.remediation_batch_id, [delivery.pk])
            approved = self.client.post(self.url("flowintel-approve", pk=case.pk), follow=True)
            self.assertContains(approved, "Test notification queued")
            self.assertContains(approved, "Waiting for FlowIntel confirmation")
            self.assertNotContains(approved, "Queue test notification")
            self.run_case(case, 3)
            self.assertEqual(notifications.process_queued_notifications(), 0)
            self.run_case(case, 1)
            self.assertEqual(notifications.process_queued_notifications(), 1)
            delivery.refresh_from_db()
            self.assertEqual(delivery.status, "filed")
            self.assertEqual(notifications.process_queued_notifications(), 0)
            self.finding.refresh_from_db()
            self.assertEqual(self.finding.status, "new")

    def test_smtp_preview_prominently_labels_send_without_performing_io(self):
        with patch("portal.notifications.transport_configuration", return_value=("smtp", "fixture")):
            case, _ = self.draft(recipients=[self.contact.pk], mitigation=self.mitigation())
        self.login(self.analyst)
        preview = self.client.get(self.url("flowintel-case", pk=case.pk))
        self.assertContains(preview, "Send notification")
        self.assertContains(preview, self.contact.email)
        self.assertNotContains(preview, "Queue test notification")
        self.mock_api.assert_not_called()

    def test_prepare_explains_missing_configuration_and_contacts(self):
        self.login(self.analyst)
        url = self.url("remediation-machine", pk=self.asset.pk)
        Contact.objects.filter(pk=self.contact.pk).update(notification_enabled=False)
        self.assertContains(self.client.get(url), "no verified contacts eligible")
        FlowIntelInstance.objects.filter(pk=self.instance.pk).update(enabled=False)
        response = self.client.get(url)
        self.assertContains(response, "enable a private FlowIntel destination")
        self.assertNotContains(response, "Preview notification")

    def test_recipient_revocation_blocks_before_first_remote_write(self):
        case, _ = self.draft(recipients=[self.contact.pk], mitigation=self.mitigation())
        flowintel.approve(self.analyst, case.pk)
        Contact.objects.filter(pk=self.contact.pk).update(notification_enabled=False)
        self.run_case(case, 1)
        self.assertEqual(case.state, "blocked")
        self.assertEqual(case.remediation_reservations.count(), 0)
        self.mock_api.assert_not_called()

    def test_flowintel_read_outage_before_mail_can_resume_without_duplicates(self):
        case, _ = self.draft(recipients=[self.contact.pk], mitigation=self.mitigation())
        flowintel.approve(self.analyst, case.pk)
        self.run_case(case, 3)
        delivery = case.remediation_batch.deliveries.get()
        self.assertEqual(delivery.status, "queued")
        with patch("portal.flowintel.remote_case", side_effect=ConnectorError("offline")):
            notifications.process_queued_notifications()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "flowintel_wait")
        self.run_case(case, 1)
        with TemporaryDirectory() as outbox, override_settings(EMAIL_FILE_PATH=outbox):
            self.assertEqual(notifications.process_queued_notifications(), 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "filed")
        self.assertEqual(case.remediation_batch.deliveries.count(), 1)
        self.assertEqual(len(self.fake.writes), 2)

    def test_current_contact_scope_routes_technical_owner_to_assigned_host(self):
        technical = Contact.objects.create(
            organization=self.a,
            name="Owner",
            email="owner@example.invalid",
            function="technical",
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=self.contact.next_review,
            notification_enabled=True,
        )
        mitigation = self.mitigation()
        with self.assertRaisesMessage(ValidationError, "no actionable items"):
            self.draft(recipients=[technical.pk], mitigation=mitigation)
        self.asset.responsible_contact = technical
        self.asset.save(update_fields=["responsible_contact"])
        case, _ = self.draft(recipients=[technical.pk, self.contact.pk], mitigation=mitigation)
        self.assertEqual(case.remediation_batch.deliveries.count(), 2)
