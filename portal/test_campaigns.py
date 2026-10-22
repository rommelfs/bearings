"""Multi-constituent outreach, private payloads and bounded committed dispatch."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from . import tests
from .models import Contact, Finding, Installation, NotificationBatch, NotificationReceipt, Product
from .notifications import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    NotificationForm,
    campaign_audience,
    preview_batch,
    process_queued_notifications,
    queue_campaign,
)
from .services import persist_lookup
from .test_notifications import NotificationTests


class CampaignTests(tests.Fixture):
    def setUp(self):
        NotificationTests.setUp(self)
        self.b.operator_visibility = True
        self.b.save()
        product = Product.objects.create(organization=self.b, name="Example product")
        installation = Installation.objects.create(asset=self.other, product=product)
        persist_lookup(None, installation, "fixture://beta", "CVE-2021-44228", self.finding.record.payload)
        self.second = Contact.objects.create(
            organization=self.b,
            name="Beta security",
            email="beta@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=30),
        )
        self.filters = {
            **self.filters,
            "organization": None,
            "audience_scope": "all",
            "missing_contacts": "block",
        }

    def preview(self):
        return preview_batch(self.analyst, "circl", self.filters, DEFAULT_SUBJECT, DEFAULT_BODY)

    def queue(self, batch):
        queue_campaign(self.analyst, batch.pk, set(batch.deliveries.values_list("pk", flat=True)))

    def test_all_scope_ignores_single_company_and_selected_scope_is_validated(self):
        data = {
            "mode": "circl",
            "audience_scope": "all",
            "organization": self.a.pk,
            "sort": "severity",
            "subject_template": DEFAULT_SUBJECT,
            "body_template": DEFAULT_BODY,
        }
        form = NotificationForm(self.analyst, data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.filters()["organization"])
        data.update(audience_scope="selected", organizations=[self.b.pk])
        form = NotificationForm(self.analyst, data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.filters()["organizations"], [self.b.pk])
        batch = preview_batch(self.analyst, "circl", form.filters(), DEFAULT_SUBJECT, DEFAULT_BODY)
        self.assertEqual(list(batch.deliveries.values_list("organization_id", flat=True)), [self.b.pk])
        self.b.operator_visibility = False
        self.b.save()
        self.assertFalse(NotificationForm(self.analyst, data).is_valid())
        self.assertFalse(NotificationForm(self.admin, data).is_valid())

    def test_missing_contacts_block_atomically_or_are_explicitly_reported(self):
        self.second.notification_enabled = False
        self.second.save()
        with self.assertRaisesMessage(ValidationError, "no opted-in contacts"):
            self.preview()
        self.assertFalse(NotificationBatch.objects.exists())
        self.filters["missing_contacts"] = "exclude"
        batch = self.preview()
        self.assertEqual(batch.deliveries.count(), 1)
        self.assertEqual(batch.audience_report["organizations"], 2)
        self.assertEqual(batch.audience_report["blocked_organizations"], 1)
        self.assertEqual(batch.audience_report["matches"], 2)
        self.login(self.analyst)
        response = self.client.get(reverse("notification-batch", args=[batch.pk]))
        self.assertContains(response, "Beta")
        self.assertContains(response, "Approve entire campaign")
        self.assertNotIn(self.other.name, batch.deliveries.get().body)
        self.contact.notification_enabled = False
        self.contact.save()
        with self.assertRaises(ValidationError):
            self.preview()
        self.assertEqual(NotificationBatch.objects.count(), 1)

    def test_complete_readiness_exceeds_first_hundred_displayed_matches(self):
        for n in range(101):
            installation = Installation.objects.create(asset=self.asset, product=self.product, version=str(n))
            Finding.objects.create(organization=self.a, installation=installation, record=self.finding.record)
        report = campaign_audience(self.analyst, "circl", self.filters)
        self.assertEqual(report["matches"], 103)
        self.assertEqual(report["organizations"], 2)
        self.assertEqual(report["recipients"], 2)

    def test_single_http_approval_queues_every_constituent_without_io_then_files_privately(self):
        batch = self.preview()
        self.login(self.analyst)
        response = self.client.post(reverse("notification-approve", args=[batch.pk]), {"selection": "all"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(batch.deliveries.filter(status="queued").count(), 2)
        self.assertFalse(list(Path(self.directory.name).iterdir()))
        self.assertEqual(process_queued_notifications(1), 1)
        self.assertEqual(batch.deliveries.filter(status="queued").count(), 1)
        self.assertEqual(process_queued_notifications(), 1)
        self.assertEqual(process_queued_notifications(), 0)
        self.assertEqual(batch.deliveries.filter(status="filed").count(), 2)
        self.assertEqual(NotificationReceipt.objects.count(), 2)
        for delivery in batch.deliveries.all():
            self.assertIn(
                self.asset.name if delivery.organization_id == self.a.pk else self.other.name, delivery.body
            )
            self.assertNotIn(
                self.other.name if delivery.organization_id == self.a.pk else self.asset.name, delivery.body
            )
        self.login()
        response = self.client.get(reverse("notifications"))
        self.assertNotContains(response, self.other.name)
        self.assertEqual(self.client.get(reverse("notification-batch", args=[batch.pk])).status_code, 404)

    def test_one_stale_recipient_prevents_partial_campaign_approval(self):
        batch = self.preview()
        self.second.notification_enabled = False
        self.second.save()
        with self.assertRaises(ValidationError):
            self.queue(batch)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "draft")
        self.assertFalse(NotificationReceipt.objects.exists())
        self.assertFalse(list(Path(self.directory.name).iterdir()))

    def test_policy_revocation_after_queue_prevents_io_and_never_retries(self):
        batch = self.preview()
        self.queue(batch)
        self.b.operator_visibility = False
        self.b.save()
        self.assertEqual(process_queued_notifications(), 2)
        self.assertEqual(batch.deliveries.filter(status="uncertain").count(), 1)
        self.assertEqual(batch.deliveries.filter(status="filed").count(), 1)
        self.assertEqual(process_queued_notifications(), 0)

    def test_queue_interruption_cannot_automatically_retry_claimed_message(self):
        batch = self.preview()
        self.queue(batch)
        with patch("portal.notifications.deliver_claimed", side_effect=RuntimeError("worker interruption")):
            with self.assertRaises(RuntimeError):
                process_queued_notifications(1)
        self.assertEqual(batch.deliveries.filter(status="filing").count(), 1)
        self.assertEqual(process_queued_notifications(), 1)
        self.assertEqual(process_queued_notifications(), 0)

    def test_excluded_counts_are_hidden_when_pinned_evidence_loses_redistribution(self):
        self.second.notification_enabled = False
        self.second.save()
        self.filters["missing_contacts"] = "exclude"
        batch = self.preview()
        record = Finding.objects.get(organization=self.b).record
        record.shareable = False
        record.save()
        self.login(self.analyst)
        self.assertEqual(self.client.get(reverse("notification-batch", args=[batch.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("notification-approve", args=[batch.pk]), {"selection": "all"}
            ).status_code,
            404,
        )

    def test_excluded_audience_names_disappear_when_visibility_is_revoked(self):
        self.second.notification_enabled = False
        self.second.save()
        self.filters["missing_contacts"] = "exclude"
        batch = self.preview()
        self.b.operator_visibility = False
        self.b.save()
        self.login(self.analyst)
        self.assertEqual(self.client.get(reverse("notification-batch", args=[batch.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("notification-approve", args=[batch.pk]), {"selection": "all"}
            ).status_code,
            404,
        )
        self.assertFalse(NotificationReceipt.objects.exists())

    def test_modern_campaign_can_exceed_old_hundred_recipient_limit(self):
        Contact.objects.bulk_create(
            [
                Contact(
                    organization=self.a,
                    name=f"Synthetic team {n}",
                    email=f"team-{n}@example.invalid",
                    notification_enabled=True,
                    reachable_at=timezone.now(),
                    reviewed_at=timezone.now(),
                    next_review=timezone.localdate() + timedelta(days=30),
                )
                for n in range(100)
            ]
        )
        self.assertEqual(self.preview().deliveries.count(), 102)

    def test_multi_constituent_subscription_only_prepares_changed_drafts(self):
        from .models import NotificationSubscription
        from .subscriptions import prepare

        row = NotificationSubscription.objects.create(
            creator=self.analyst,
            name="Synthetic multi-company",
            mode="circl",
            filters=self.filters,
            subject_template=DEFAULT_SUBJECT,
            body_template=DEFAULT_BODY,
        )
        prepare(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.last_batch.deliveries.count(), 2)
        self.assertEqual(row.last_batch.status, "draft")
        original = row.last_batch_id
        prepare(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.last_batch_id, original)
        self.assertFalse(NotificationReceipt.objects.exists())
        self.assertFalse(list(Path(self.directory.name).iterdir()))

    @override_settings(CIRCL_CAMPAIGN_MAX_REVIEWS=1)
    def test_review_cap_rejects_complete_campaign_without_silent_truncation(self):
        with self.assertRaises(ValidationError):
            self.preview()
        self.assertFalse(NotificationBatch.objects.exists())

    @override_settings(CIRCL_CAMPAIGN_MAX_RECIPIENTS=1)
    def test_recipient_cap_rolls_back_whole_campaign(self):
        with self.assertRaises(ValidationError):
            self.preview()
        self.assertFalse(NotificationBatch.objects.exists())


@override_settings(DEBUG=True)
class CampaignExampleTests(tests.Fixture):
    def test_example_has_creation_provenance_and_preserves_optouts_then_can_be_removed(self):
        from django.core.management import call_command
        from .demo_showcase import seed
        from .demo_data import removal_plan, purge
        from .models import DemoObject

        dataset, _ = seed(self.platform, companies=3, assets_per_company=6)
        call_command("seed_circl_campaign_example", actor=self.platform.username)
        contacts = Contact.objects.filter(name="SYNTHETIC campaign contact")
        self.assertEqual(contacts.count(), 2)
        for contact in contacts:
            self.assertTrue(
                DemoObject.objects.filter(
                    dataset=dataset, model_label="portal.contact", object_pk=str(contact.pk)
                ).exists()
            )
        contact = contacts.first()
        contact.notification_enabled = False
        contact.save()
        count = dataset.entries.count()
        call_command("seed_circl_campaign_example", actor=self.platform.username)
        self.assertEqual(dataset.entries.count(), count)
        contact.refresh_from_db()
        self.assertFalse(contact.notification_enabled)
        plan, _ = removal_plan(dataset)
        self.assertEqual(plan["blockers"], [])
        purge(self.platform, dataset.key, plan["fingerprint"])
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_circl_campaign_example", actor=self.platform.username)
