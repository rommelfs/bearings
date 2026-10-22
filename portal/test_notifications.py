import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command, CommandError
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import tests
from .models import (
    AuditEvent,
    Contact,
    Finding,
    Installation,
    InventorySource,
    Membership,
    NotificationBatch,
    NotificationDelivery,
    NotificationReceipt,
    Organization,
    Product,
    Asset,
)
from .notifications import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    NotificationForm,
    approve_local,
    candidates,
    claim_batch,
    eligible_contacts,
    preview_batch,
    queue_campaign,
    process_queued_notifications,
    render_text,
)


class NotificationTests(tests.Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.finding.record.payload = {
            "containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 8.1}}]}}
        }
        self.finding.record.save()
        self.contact.notification_enabled = True
        self.contact.reachable_at = self.contact.reviewed_at = timezone.now()
        self.contact.next_review = timezone.localdate() + timedelta(days=30)
        self.contact.save()
        self.asset.upstream_data = {
            "primary_ip4": "192.0.2.25/24",
            "primary_ip4_dns_name": "mail.example.invalid",
            "rack": {"id": 1, "name": "EX-01"},
            "position": "22",
        }
        self.asset.save()
        self.filters = {
            "organization": self.a.pk,
            "product": "Example",
            "severity": "high",
            "sort": "severity",
        }
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(
            EMAIL_FILE_PATH=Path(self.directory.name),
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def preview(self, user=None, mode="company", filters=None):
        return preview_batch(user or self.admin, mode, filters or self.filters, DEFAULT_SUBJECT, DEFAULT_BODY)

    def approve(self, batch, user=None):
        return approve_local(user or self.admin, batch.pk, set(batch.deliveries.values_list("pk", flat=True)))

    def test_home_prompts_authorized_reviewers_to_notify_scoped_contacts(self):
        self.login(self.analyst)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Review & notify contacts")
        self.assertContains(response, "mode=circl&amp;organization=" + str(self.a.pk))
        self.login(self.reader)
        self.assertNotContains(self.client.get(reverse("home")), "Review & notify contacts")
        self.login()
        self.assertContains(
            self.client.get(reverse("home")), "mode=company&amp;organization=" + str(self.a.pk)
        )

    def test_filter_sort_and_unknown_are_distinct(self):
        self.assertEqual(list(candidates(self.analyst, "circl", self.filters)), [self.finding])
        self.assertEqual(
            candidates(self.admin, "company", {**self.filters, "severity": "unknown"}).count(), 0
        )
        self.finding.analyst_applicability = "not_affected"
        self.finding.save()
        self.assertFalse(candidates(self.admin, "company", self.filters).exists())

    def test_operator_visibility_and_restricted_evidence_never_enter_outreach(self):
        self.finding.record.shareable = False
        self.finding.record.save(update_fields=["shareable"])
        for user in [self.admin, self.analyst, self.platform]:
            self.assertFalse(candidates(user, "circl", self.filters).exists())
        self.finding.record.shareable = True
        self.finding.record.save(update_fields=["shareable"])
        self.a.operator_visibility = False
        self.a.save()
        self.assertFalse(candidates(self.analyst, "circl", self.filters).exists())
        self.assertTrue(candidates(self.admin, "company", self.filters).exists())

    def test_reader_foreign_org_and_mode_injection_denied(self):
        for user, mode, filters in [
            (self.reader, "company", self.filters),
            (self.admin, "circl", self.filters),
            (self.admin, "company", {**self.filters, "organization": self.b.pk}),
        ]:
            with self.assertRaises(ValidationError):
                self.preview(user, mode, filters)
        with self.assertRaises(PermissionDenied):
            self.preview(self.admin, "arbitrary")
        self.assertFalse(NotificationBatch.objects.exists())

    def test_contact_readiness_dimensions_and_no_silent_skips(self):
        for field, value in [
            ("notification_enabled", False),
            ("reachable_at", None),
            ("reviewed_at", None),
            ("next_review", timezone.localdate()),
            ("invalid_delivery", True),
        ]:
            original = getattr(self.contact, field)
            setattr(self.contact, field, value)
            self.contact.save()
            self.assertFalse(eligible_contacts(self.a).exists())
            with self.assertRaisesMessage(ValidationError, "no opted-in contacts"):
                self.preview()
            setattr(self.contact, field, original)
            self.contact.save()
        self.assertFalse(NotificationBatch.objects.exists())
        # Availability has not been confirmed; it is not silently treated as email/role validation.
        self.assertIsNone(self.contact.availability_confirmed_at)
        self.assertEqual(self.preview().deliveries.count(), 1)

    def test_grouped_preview_contains_asset_context_and_no_delivery(self):
        second = Installation.objects.create(asset=self.asset, product=self.product, version="2")
        Finding.objects.create(
            organization=self.a,
            installation=second,
            record=self.finding.record,
            explanation="Second installation, applicability unknown",
        )
        batch = self.preview(self.analyst, "circl")
        d = batch.deliveries.get()
        self.assertEqual(len(d.snapshot["findings"]), 2)
        self.assertEqual(d.findings.count(), 2)
        for value in [
            "192.0.2.25/24",
            "mail.example.invalid",
            "EX-01",
            "U22",
            "source severity HIGH",
            "automated applicability: unknown",
            "CIRCL requests",
        ]:
            self.assertIn(value, d.body)
        self.assertFalse(list(Path(self.directory.name).iterdir()))
        self.assertTrue(AuditEvent.objects.filter(action="notification.preview").exists())

    def test_templates_allow_flat_variables_and_reject_execution(self):
        self.assertEqual(
            render_text("Hello {{ organization }}", {"organization": "<Alpha>"}), "Hello <Alpha>"
        )
        for text in [
            '{% include "x" %}',
            "{% debug %}",
            "{{ request.user }}",
            "{{ findings|safe }}",
            "{{ unknown }}",
            "{{ organization",
            "{{ organization }} }}",
        ]:
            with self.assertRaises(ValidationError):
                render_text(text, {})
        form = NotificationForm(
            self.admin,
            {
                "mode": "company",
                "organization": self.a.pk,
                "sort": "severity",
                "subject_template": "Hello\nBcc: x@example.invalid",
                "body_template": "{{ findings }}",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("subject_template", form.errors)

    def test_actual_http_preview_local_approval_company_inbox_ack(self):
        self.login(self.analyst)
        data = {
            "mode": "circl",
            "organization": self.a.pk,
            "sort": "severity",
            "severity": "high",
            "subject_template": DEFAULT_SUBJECT,
            "body_template": DEFAULT_BODY,
            "action": "preview",
        }
        response = self.client.post(reverse("notifications"), data)
        batch = NotificationBatch.objects.get()
        self.assertRedirects(response, reverse("notification-batch", args=[batch.pk]))
        d = batch.deliveries.get()
        self.assertContains(self.client.get(response.url), "mail.example.invalid")
        response = self.client.post(reverse("notification-approve", args=[batch.pk]), {"delivery": [d.pk]})
        self.assertEqual(response.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.status, "filed")
        self.assertEqual(len(list(Path(self.directory.name).iterdir())), 1)
        self.login()
        self.assertContains(self.client.get(reverse("notifications")), "Awaiting acknowledgment")
        self.assertEqual(self.client.post(reverse("notification-ack", args=[d.pk])).status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.acknowledged_by, self.admin)
        first = d.acknowledged_at
        self.client.post(reverse("notification-ack", args=[d.pk]))
        d.refresh_from_db()
        self.assertEqual(first, d.acknowledged_at)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, "new")

    def test_repeated_batch_and_identical_new_batch_do_not_duplicate(self):
        batch = self.preview()
        self.approve(batch)
        with self.assertRaisesMessage(ValidationError, "already approved"):
            self.approve(batch)
        other = self.preview()
        self.approve(other)
        self.assertEqual(other.deliveries.get().status, "duplicate")
        self.assertEqual(NotificationReceipt.objects.count(), 1)
        self.assertEqual(len(list(Path(self.directory.name).iterdir())), 1)

    def test_changed_evidence_inventory_assessment_and_email_invalidate_preview(self):
        changes = [
            (self.finding.record, "payload", {"changed": True}),
            (self.asset, "upstream_data", {}),
            (self.finding, "analyst_applicability", "affected"),
            (self.contact, "email", "changed@example.invalid"),
        ]
        for obj, field, value in changes:
            batch = self.preview()
            original = getattr(obj, field)
            setattr(obj, field, value)
            obj.save()
            with self.assertRaises(ValidationError):
                self.approve(batch)
            setattr(obj, field, original)
            obj.save()
        self.assertFalse(NotificationReceipt.objects.exists())

    def test_revoked_consent_and_resolved_finding_block_approval(self):
        batch = self.preview()
        self.contact.notification_enabled = False
        self.contact.save()
        with self.assertRaises(ValidationError):
            self.approve(batch)
        self.contact.notification_enabled = True
        self.contact.save()
        self.finding.status = "resolved"
        self.finding.save()
        with self.assertRaises(ValidationError):
            self.approve(batch)
        self.assertFalse(NotificationReceipt.objects.exists())

    def test_policy_revocation_hides_preview_and_delivered_snapshots(self):
        batch = self.preview(self.analyst, "circl")
        self.approve(batch, self.analyst)
        self.finding.record.shareable = False
        self.finding.record.save(update_fields=["shareable"])
        self.login(self.analyst)
        self.assertEqual(self.client.get(reverse("notification-batch", args=[batch.pk])).status_code, 404)
        self.login()
        response = self.client.get(reverse("notifications"))
        self.assertNotContains(response, "mail.example.invalid")
        self.assertEqual(response.context["inbox_page"].paginator.count, 0)
        self.assertEqual(
            self.client.post(reverse("notification-ack", args=[batch.deliveries.get().pk])).status_code, 404
        )

    def test_selection_must_belong_to_batch_and_creator(self):
        batch, other = self.preview(), self.preview()
        with self.assertRaises(ValidationError):
            approve_local(self.admin, batch.pk, {other.deliveries.get().pk})
        with self.assertRaises(PermissionDenied):
            self.approve(batch, self.editor)
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse("notification-batch", args=[batch.pk])).status_code, 404)
        self.assertFalse(NotificationReceipt.objects.exists())

    def test_file_failure_is_uncertain_and_never_retried(self):
        batch = self.preview()
        with patch("portal.notifications.EmailMessage.send", side_effect=OSError("disk unavailable")):
            self.approve(batch)
        self.assertEqual(batch.deliveries.get().status, "uncertain")
        before = list(Path(self.directory.name).iterdir())
        self.approve(self.preview())
        self.assertEqual(list(Path(self.directory.name).iterdir()), before)
        self.assertTrue(all(path.stat().st_size == 0 for path in before))
        self.assertEqual(NotificationReceipt.objects.count(), 1)

    def test_recipient_selection_excludes_unchecked_message(self):
        Contact.objects.create(
            organization=self.a,
            name="Second contact",
            email="second@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=30),
        )
        batch = self.preview()
        selected = batch.deliveries.order_by("pk").first()
        approve_local(self.admin, batch.pk, {selected.pk})
        self.assertEqual(batch.deliveries.filter(status="filed").count(), 1)
        self.assertEqual(batch.deliveries.filter(status="excluded").count(), 1)

    def test_cross_org_bulk_messages_keep_payloads_separate(self):
        self.b.operator_visibility = True
        self.b.save()
        product = Product.objects.create(organization=self.b, name="Example product")
        installation = Installation.objects.create(asset=self.other, product=product)
        from .services import persist_lookup

        persist_lookup(None, installation, "fixture://beta", "CVE-2021-44228", self.finding.record.payload)
        Contact.objects.create(
            organization=self.b,
            name="Beta security",
            email="beta@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=30),
        )
        batch = self.preview(self.analyst, "circl", {**self.filters, "organization": None})
        self.assertEqual(batch.deliveries.count(), 2)
        for d in batch.deliveries.all():
            self.assertIn(self.asset.name if d.organization_id == self.a.pk else self.other.name, d.body)
            self.assertNotIn(self.other.name if d.organization_id == self.a.pk else self.asset.name, d.body)

    def test_template_html_is_escaped_on_preview(self):
        self.asset.name = "<script>alert(1)</script>"
        self.asset.save()
        batch = self.preview()
        self.login()
        response = self.client.get(reverse("notification-batch", args=[batch.pk]))
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_fixture_is_explicit_idempotent_and_preserves_policy(self):
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("seed_notification_example")
        with override_settings(DEBUG=True):
            call_command("seed_notification_example")
            contact = Contact.objects.get(email="notifications-example-labs@example.invalid")
            contact.notification_enabled = False
            contact.save()
            call_command("seed_notification_example")
            contact.refresh_from_db()
            self.assertFalse(contact.notification_enabled)
            self.assertEqual(Contact.objects.filter(email=contact.email).count(), 1)

    def test_severity_sort_and_preview_limits_apply_to_complete_result(self):
        from .services import persist_lookup

        second = Installation.objects.create(asset=self.asset, product=self.product, version="other")
        critical = persist_lookup(
            None,
            second,
            "fixture://critical",
            "CVE-2021-45046",
            {"containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 10.0}}]}}},
        )
        filters = {**self.filters, "severity": ""}
        self.assertEqual(
            list(candidates(self.admin, "company", filters).values_list("pk", flat=True)),
            [critical.pk, self.finding.pk],
        )
        with patch("portal.notifications.candidates") as query:
            query.return_value.__getitem__.return_value = [self.finding] * 501
            with self.assertRaisesMessage(ValidationError, "More than 500"):
                self.preview()
        self.assertFalse(NotificationBatch.objects.exists())

    def test_recipient_and_policy_rechecked_after_attempt_claim_before_file_io(self):
        batch = self.preview()
        real_claim = claim_batch

        def change_policy(*args):
            ids = real_claim(*args)
            self.finding.record.shareable = False
            self.finding.record.save(update_fields=["shareable"])
            return ids

        with patch("portal.notifications.claim_batch", side_effect=change_policy):
            self.approve(batch)
        self.assertEqual(batch.deliveries.get().status, "uncertain")
        self.assertEqual(NotificationReceipt.objects.count(), 1)
        self.assertFalse(list(Path(self.directory.name).iterdir()))

    def test_operator_consent_revoked_and_company_role_downgraded_after_preview(self):
        batch = self.preview(self.analyst, "circl")
        self.a.operator_visibility = False
        self.a.save()
        with self.assertRaises(PermissionDenied):
            self.approve(batch, self.analyst)
        internal = self.preview()
        Membership.objects.filter(user=self.admin, organization=self.a).update(role="reader")
        with self.assertRaises(PermissionDenied):
            self.approve(internal)
        self.assertFalse(NotificationReceipt.objects.exists())


@skipUnless(connection.vendor == "postgresql", "PostgreSQL notification claim concurrency")
class ConcurrentNotificationTests(TransactionTestCase):
    def test_identical_previews_racing_claim_only_one_attempt(self):
        user = get_user_model().objects.create_user("concurrent-notifier")
        org = Organization.objects.create(name="Concurrent", slug="concurrent-notifications")
        Membership.objects.create(user=user, organization=org, role="admin")
        source = InventorySource.objects.create(organization=org, mode="development")
        asset = Asset.objects.create(
            organization=org, source=source, name="Concurrent synthetic machine", kind="server"
        )
        product = Product.objects.create(organization=org, name="Concurrent product")
        installation = Installation.objects.create(asset=asset, product=product)
        from .services import persist_lookup

        persist_lookup(None, installation, "fixture://concurrent", "CVE-2021-44228", {})
        Contact.objects.create(
            organization=org,
            name="Synthetic",
            email="test@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=30),
        )
        filters = {"organization": org.pk, "sort": "severity"}
        batches = [preview_batch(user, "company", filters, DEFAULT_SUBJECT, DEFAULT_BODY) for _ in range(2)]

        def claim(batch):
            close_old_connections()
            try:
                return claim_batch(user, batch.pk, set(batch.deliveries.values_list("pk", flat=True)))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(claim, batch) for batch in batches]
            results = [f.result(timeout=10) for f in futures]
        self.assertEqual(sum(len(result) for result in results), 1)
        self.assertEqual(NotificationReceipt.objects.count(), 1)
        self.assertEqual(NotificationDelivery.objects.filter(status="duplicate").count(), 1)

        # Independently running workers claim an approved queued delivery only once.
        queued = preview_batch(user, "company", filters, DEFAULT_SUBJECT, DEFAULT_BODY + " Worker exercise.")
        queue_campaign(user, queued.pk, set(queued.deliveries.values_list("pk", flat=True)))

        def dispatch():
            close_old_connections()
            try:
                return process_queued_notifications(1)
            finally:
                connections.close_all()

        with tempfile.TemporaryDirectory() as directory, override_settings(EMAIL_FILE_PATH=directory):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(dispatch) for _ in range(2)]
                self.assertEqual(sum(f.result(timeout=10) for f in futures), 1)
            self.assertEqual(queued.deliveries.get().status, "filed")
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
