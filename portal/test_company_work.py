"""Adoption, action and response flows preserve source ownership, current access and evidence."""

from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from .tests import Fixture
from .models import (
    Asset,
    Installation,
    InventoryWrite,
    InfrastructureClaim,
    InventoryReviewPolicy,
    InventoryReviewDelivery,
)
from . import inventory_csv, issues
from .inventory_review import (
    reminder_recipients,
    deliver_review_reminder,
    confirm_review,
    snapshot,
    review_token,
)
from .review_followup import preview_token, queue_followup, record_feedback, deliveries_for, delivery_label

CSV = b"asset_key,name,kind,ip,domain,software,version,software_key\nweb-1,New CSV server,server,192.0.2.4,web.example.invalid,Apache Log4j,2.14.1,log4j\n"


class CSVTests(Fixture):
    def setUp(self):
        self.sa.mode = "manual"
        self.sa.save()

    def test_preview_then_explicit_atomic_commit_and_repeat_do_not_duplicate_or_submit_jobs(self):
        before = Asset.objects.count()
        batch = inventory_csv.preview(self.admin, self.a, CSV)
        self.assertFalse(batch.errors)
        self.assertEqual(Asset.objects.count(), before)
        result = inventory_csv.commit(self.admin, self.a, batch.pk)
        self.assertEqual(result.result["created"], 1)
        self.assertEqual(Asset.objects.count(), before + 1)
        inventory_csv.commit(self.admin, self.a, batch.pk)
        second = inventory_csv.preview(self.admin, self.a, CSV)
        self.assertFalse(second.errors)
        inventory_csv.commit(self.admin, self.a, second.pk)
        self.assertEqual(Asset.objects.count(), before + 1)
        self.assertEqual(Installation.objects.filter(asset__csv_binding__key="web-1").count(), 1)
        self.assertFalse(InventoryWrite.objects.exists())

    def test_rows_errors_duplicates_and_limits_do_not_change_inventory(self):
        for raw in [b"name\nOnly name\n", b"asset_key,asset_key,name\na,a,n\n", b"\xff", b"x" * 1_000_001]:
            with self.assertRaises(ValidationError):
                inventory_csv.preview(self.admin, self.a, raw)
        wrong = CSV.replace(b"192.0.2.4", b"bad-ip")
        batch = inventory_csv.preview(self.admin, self.a, wrong)
        self.assertTrue(batch.errors)
        with self.assertRaises(ValidationError):
            inventory_csv.commit(self.admin, self.a, batch.pk)
        double = inventory_csv.preview(self.admin, self.a, CSV + CSV.splitlines()[1] + b"\n")
        self.assertTrue(double.errors)

    def test_local_edits_stale_preview_source_change_and_revoked_access_are_preserved(self):
        batch = inventory_csv.preview(self.admin, self.a, CSV)
        inventory_csv.commit(self.admin, self.a, batch.pk)
        again = inventory_csv.preview(self.admin, self.a, CSV)
        asset = Asset.objects.get(csv_binding__key="web-1")
        asset.name = "Local correction"
        asset.save()
        with self.assertRaises(ValidationError):
            inventory_csv.commit(self.admin, self.a, again.pk)
        self.assertTrue(inventory_csv.preview(self.admin, self.a, CSV).errors)
        self.sa.mode = "development"
        self.sa.save()
        with self.assertRaises(PermissionDenied):
            inventory_csv.commit(self.admin, self.a, again.pk)
        self.sa.mode = "manual"
        self.sa.save()
        self.a.membership_set.filter(user=self.admin).delete()
        with self.assertRaises(PermissionDenied):
            inventory_csv.commit(self.admin, self.a, again.pk)
        asset.refresh_from_db()
        self.assertEqual(asset.name, "Local correction")

    def test_software_local_edits_are_not_silently_overwritten_and_unknown_versions_are_explicit(self):
        batch = inventory_csv.preview(self.admin, self.a, CSV.replace(b"2.14.1", b""))
        inventory_csv.commit(self.admin, self.a, batch.pk)
        installed = Installation.objects.get(asset__csv_binding__key="web-1")
        self.assertEqual(installed.version, "")
        installed.version = "local-build"
        installed.save()
        self.assertTrue(inventory_csv.preview(self.admin, self.a, CSV).errors)

    def test_expiry_and_late_validation_failure_roll_back_the_entire_batch(self):
        raw = (
            CSV
            + CSV.splitlines()[1].replace(b"web-1", b"web-2").replace(b"New CSV server", b"Second CSV server")
            + b"\n"
        )
        batch = inventory_csv.preview(self.admin, self.a, raw)
        before = Asset.objects.count()
        with patch(
            "portal.models.Asset.full_clean", side_effect=[None, ValidationError("Synthetic late failure")]
        ):
            with self.assertRaises(ValidationError):
                inventory_csv.commit(self.admin, self.a, batch.pk)
        self.assertEqual(Asset.objects.count(), before)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "preview")
        batch.expires_at = timezone.now() - timedelta(seconds=1)
        batch.save()
        with self.assertRaises(ValidationError):
            inventory_csv.commit(self.admin, self.a, batch.pk)

    def test_supported_500_row_batch_is_atomic_and_repeatable(self):
        raw = (
            "asset_key,name,software,version\n"
            + "".join(f"host-{i},CSV batch server {i},Unknown product,\n" for i in range(500))
        ).encode()
        batch = inventory_csv.preview(self.admin, self.a, raw)
        self.assertFalse(batch.errors)
        result = inventory_csv.commit(self.admin, self.a, batch.pk)
        self.assertEqual(result.result["created"], 500)
        self.assertEqual(Installation.objects.filter(asset__csv_binding__source=self.sa).count(), 500)
        with self.assertRaises(ValidationError):
            inventory_csv.preview(self.admin, self.a, raw + b"overflow,Too many rows,,,\n")

    def test_view_requires_own_authorized_actor_csrf_and_confirmation(self):
        self.login(self.admin)
        url = f"/organizations/{self.a.slug}/import-csv/"
        response = self.client.post(url, {"file": SimpleUploadedFile("inventory.csv", CSV)})
        self.assertEqual(response.status_code, 302)
        preview_url = response.url
        self.assertEqual(self.client.post(preview_url, {}).status_code, 403)
        self.assertEqual(self.client.post(preview_url, {"confirmed": "on"}).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url).status_code, 403)
        self.login(self.reader)
        self.assertEqual(self.client.get(preview_url).status_code, 403)
        self.login(self.editor)
        self.assertEqual(self.client.get(preview_url).status_code, 404)

    def test_blank_or_differently_named_existing_assets_are_not_adopted_and_missing_rows_not_deleted(self):
        raw = CSV.replace(b"New CSV server", self.asset.name.encode())
        self.assertTrue(inventory_csv.preview(self.admin, self.a, raw).errors)
        batch = inventory_csv.preview(self.admin, self.a, CSV)
        inventory_csv.commit(self.admin, self.a, batch.pk)
        smaller = inventory_csv.preview(self.admin, self.a, b"asset_key,name\nother,Other CSV server\n")
        inventory_csv.commit(self.admin, self.a, smaller.pk)
        self.assertTrue(Asset.objects.filter(csv_binding__key="web-1").exists())

    def test_quick_start_is_additive_and_does_not_claim_verification_or_complete_all_sections(self):
        self.login(self.admin)
        url = f"/organizations/{self.a.slug}/start-small/"
        self.assertEqual(self.client.post(url, {"scope": "example.invalid"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"scope": "example.invalid"}).status_code, 302)
        claim = InfrastructureClaim.objects.get(organization=self.a, kind="domain", value="example.invalid")
        self.assertEqual(claim.status, "declared")
        self.assertFalse(self.a.configuration_sections.filter(reviewed=True).exists())
        self.login(self.reader)
        self.assertEqual(self.client.get(url).status_code, 403)


class ActionTests(Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.issue = issues.ensure_vulnerability_issue(self.finding)

    def test_grouped_actions_hide_restricted_reviews_and_keep_critical_first(self):
        self.finding.record.source_severity = "critical"
        self.finding.record.save(update_fields=["source_severity"])
        self.login(self.admin)
        response = self.client.get("/actions/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.finding.record.shareable = False
        self.finding.record.save()
        self.assertNotContains(self.client.get("/actions/"), self.product.name)
        self.login(self.analyst)
        self.assertContains(self.client.get("/actions/"), self.product.name)
        self.a.operator_visibility = False
        self.a.save()
        self.assertNotContains(self.client.get("/actions/"), self.product.name)

    def test_acknowledgment_assignment_and_evidence_preserve_applicability_and_do_not_auto_resolve(self):
        self.login(self.admin)
        url = f"/organizations/{self.a.slug}/issues/{self.issue.pk}/action/"
        page = self.client.get(url)
        token = page.context["form"]["token"].value()
        response = self.client.post(
            url,
            {
                "operation": "acknowledge",
                "owner_team": "Security team",
                "action_due": "2030-01-01",
                "note": "Starting investigation",
                "token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.finding.refresh_from_db()
        self.issue.refresh_from_db()
        self.assertEqual(self.finding.status, "under_review")
        self.assertEqual(self.finding.analyst_applicability, "unassessed")
        self.assertEqual(self.issue.owner_team, "Security team")
        token = self.client.get(url).context["form"]["token"].value()
        self.assertEqual(
            self.client.post(
                url,
                {
                    "operation": "evidence",
                    "owner_team": "Security team",
                    "note": "Patch installation log reviewed; applicability still to verify",
                    "token": token,
                },
            ).status_code,
            302,
        )
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, "under_review")
        self.assertTrue(self.issue.history.filter(reason__icontains="Patch installation").exists())

    def test_stale_form_and_restricted_or_readonly_actions_do_not_mutate(self):
        self.login(self.admin)
        url = f"/organizations/{self.a.slug}/issues/{self.issue.pk}/action/"
        token = self.client.get(url).context["form"]["token"].value()
        issues.save_issue(self.admin, self.issue, {"owner_team": "Changed elsewhere"}, "New owner")
        response = self.client.post(url, {"operation": "assign", "note": "Old form", "token": token})
        self.assertContains(response, "issue changed")
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.owner_team, "Changed elsewhere")
        self.login(self.reader)
        self.assertEqual(self.client.get(url).status_code, 403)


@override_settings(
    PUBLIC_BASE_URL="https://bearings.example.invalid",
    SERVICE_MAIL_TRANSPORT="file",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class FollowupTests(Fixture):
    def setUp(self):
        self.policy = InventoryReviewPolicy.objects.create(
            organization=self.a, next_due=timezone.localdate() - timedelta(days=1)
        )
        self.contact.reachable_at = timezone.now()
        self.contact.notification_enabled = True
        self.contact.save()

    def test_preview_does_not_send_confirmation_queues_once_and_cooldown_holds(self):
        token = preview_token(self.analyst, self.policy, self.contact.email)
        self.assertFalse(InventoryReviewDelivery.objects.exists())
        item = queue_followup(self.analyst, self.policy.pk, token)
        self.assertEqual(item.requested_by, self.analyst)
        with self.assertRaises(ValidationError):
            queue_followup(self.analyst, self.policy.pk, token)
        self.assertEqual(InventoryReviewDelivery.objects.count(), 1)
        deliver_review_reminder(item.pk)
        item = deliveries_for(self.policy).get(pk=item.pk)
        self.assertEqual(item.transport, "file")
        self.assertIn("response outstanding", delivery_label(item))
        self.assertFalse(item.acknowledged)

    def test_recipient_revocation_completed_review_and_visibility_change_block_followup(self):
        token = preview_token(self.analyst, self.policy, self.contact.email)
        self.contact.notification_enabled = False
        self.contact.save()
        with self.assertRaises(ValidationError):
            queue_followup(self.analyst, self.policy.pk, token)
        self.contact.notification_enabled = True
        self.contact.save()
        self.a.operator_visibility = False
        self.a.save()
        with self.assertRaises(PermissionDenied):
            queue_followup(self.analyst, self.policy.pk, token)
        self.a.operator_visibility = True
        self.a.save()
        proof = review_token(self.admin, self.policy, snapshot(self.a)[0])
        confirm_review(self.admin, self.a, proof)
        with self.assertRaises(ValidationError):
            queue_followup(self.analyst, self.policy.pk, token)

    def test_smtp_acceptance_bounce_and_recovery_do_not_forge_owner_response_or_contact_review(self):
        item = InventoryReviewDelivery.objects.create(
            policy=self.policy,
            due_date=self.policy.next_due,
            recipient=self.contact.email,
            fingerprint="synthetic-feedback",
            status="sent",
            transport="smtp",
        )
        record_feedback(self.analyst, item.pk, "bounced", "Provider report manually checked")
        self.assertNotIn(self.contact.email, reminder_recipients(self.policy))
        item = deliveries_for(self.policy).get(pk=item.pk)
        self.assertFalse(item.acknowledged)
        self.assertIn("Bounce reported", delivery_label(item))
        record_feedback(self.analyst, item.pk, "delivered", "Provider recovery evidence checked")
        self.assertIn(self.contact.email, reminder_recipients(self.policy))
        self.contact.refresh_from_db()
        self.assertIsNone(self.contact.reviewed_at)
        proof = review_token(self.admin, self.policy, snapshot(self.a)[0])
        confirm_review(self.admin, self.a, proof)
        item = deliveries_for(self.policy).get(pk=item.pk)
        self.assertTrue(item.acknowledged)
        self.assertEqual(delivery_label(item), "Data review completed")

    def test_company_cannot_configure_feedback_queue_or_dpo_escalation(self):
        self.login(self.admin)
        self.assertEqual(self.client.get("/circl/review-followups/").status_code, 403)
        self.assertEqual(self.client.get(f"/organizations/{self.a.slug}/review/followup/").status_code, 403)
        self.contact.function = "dpo"
        self.contact.save()
        with self.assertRaises(ValidationError):
            preview_token(self.analyst, self.policy, self.contact.email)
        self.login(self.analyst)
        response = self.client.get("/circl/review-followups/")
        self.assertContains(response, self.a.name)
        self.assertNotContains(response, self.b.name)


class CSVConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_commits_of_one_preview_create_one_inventory_projection(self):
        import threading
        from django.contrib.auth import get_user_model
        from django.db import connection, close_old_connections
        from .models import Organization, Membership, InventorySource

        user = get_user_model().objects.create_user("csv-owner")
        org = Organization.objects.create(name="Synthetic concurrent CSV", slug="concurrent-csv")
        Membership.objects.create(user=user, organization=org, role="admin")
        InventorySource.objects.create(organization=org, mode="manual")
        batch = inventory_csv.preview(user, org, CSV)
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def run():
            close_old_connections()
            try:
                barrier.wait(5)
                results.append(inventory_csv.commit(user, org, batch.pk).status)
            except Exception as error:
                errors.append(type(error).__name__)
            finally:
                connection.close()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(results, ["committed", "committed"])
        self.assertEqual(Asset.objects.filter(organization=org).count(), 1)
        self.assertEqual(Installation.objects.filter(asset__organization=org).count(), 1)
