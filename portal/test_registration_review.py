"""Mailbox-bound private workspaces, separate CIRCL sharing, and periodic owner review mail."""

import re
from concurrent.futures import ThreadPoolExecutor
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from .models import Contact, InventoryReviewPolicy
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import (
    InfrastructureRegistration,
    InventoryReviewConfirmation,
    InventoryReviewDelivery,
    InventoryWrite,
    Membership,
    Organization,
)
from .inventory_review import (
    configure_review,
    confirm_review,
    deliver_review_reminder,
    queue_review_reminders,
    review_token,
    snapshot,
)
from .registration import decide_registration, issue_verification, verify_registration

PASSWORD = "Local-example-Only!6327"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SERVICE_MAIL_TRANSPORT="file",
    PUBLIC_BASE_URL="https://reporting.example.invalid",
)
class RegistrationReviewTests(Fixture):
    def setUp(self):
        self.data = {
            "username": "new-responsible",
            "company_name": "New reporting company",
            "contact_name": "Reporting owner",
            "email": "owner@example.invalid",
            "emergency_phone": "+352 123 456",
            "periodic_consent": "on",
            "updates_consent": "on",
            "networks": "192.0.2.0/24\n2001:db8::/48",
            "ips": "198.51.100.17",
            "domains": "EXAMPLE.invalid.",
            "review_days": 30,
            "email_reminders": "on",
            "consent": "on",
            "attestation": "on",
        }

    def signup(self):
        response = self.client.post(reverse("registration"), self.data)
        self.assertRedirects(response, reverse("registration-sent"))
        item = InfrastructureRegistration.objects.get()
        code = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body)[1]
        return item, code

    def workspace(self):
        item, code = self.signup()
        result = verify_registration(code, PASSWORD)
        self.assertTrue(result)
        item.refresh_from_db()
        return item, item.organization

    def make_due(self, org):
        policy = org.inventory_review_policy
        policy.next_due = timezone.localdate() - timedelta(days=1)
        policy.next_reminder_at = timezone.now() - timedelta(hours=1)
        policy.save()
        return policy

    def test_email_proof_opens_private_workspace_and_circl_approval_is_separate(self):
        item, code = self.signup()
        self.assertFalse(item.user.is_active)
        self.assertFalse(item.user.has_usable_password())
        with self.assertRaises(PermissionDenied):
            decide_registration(self.analyst, item.pk, "reject", "Premature decision")
        self.assertEqual(Organization.objects.count(), 2)
        response = self.client.get(reverse("registration-verify"))
        self.assertFalse(InfrastructureRegistration.objects.get().email_verified_at)
        response = self.client.post(
            reverse("registration-verify"),
            {"code": code, "password1": PASSWORD, "password2": PASSWORD, "requested": "on"},
        )
        self.assertContains(response, "private organization area is ready")
        item.refresh_from_db()
        user = get_user_model().objects.get(pk=item.user_id)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff or user.is_superuser or user.groups.exists())
        self.assertFalse(item.organization.operator_visibility)
        self.assertEqual(Membership.objects.filter(user=user).count(), 1)
        self.assertEqual(item.organization.inventory_source.mode, "manual")
        self.assertTrue(self.client.login(username=user.username, password=PASSWORD))
        self.assertEqual(
            self.client.get(reverse("organization", args=[item.organization.slug])).status_code, 200
        )
        self.assertEqual(self.client.get(self.url("organization")).status_code, 404)
        self.login(self.analyst)
        self.assertEqual(
            self.client.get(reverse("organization", args=[item.organization.slug])).status_code, 404
        )
        decide_registration(self.analyst, item.pk, "approve", "Checked application")
        item.refresh_from_db()
        self.assertTrue(item.organization.operator_visibility)
        self.assertEqual(
            self.client.get(reverse("organization", args=[item.organization.slug])).status_code, 200
        )
        self.assertFalse(item.organization.claims.exists())
        self.assertEqual(Membership.objects.filter(user=user).count(), 1)

    def test_registration_defers_scope_and_rejects_duplicate_email(self):
        response = self.client.get(reverse("registration"))
        self.assertNotIn("networks", response.context["form"].fields)
        self.assertNotIn("ips", response.context["form"].fields)
        self.assertNotIn("domains", response.context["form"].fields)
        self.assertIn("pgp_public_key", response.context["form"].fields)
        self.assertIn("smime_certificate", response.context["form"].fields)
        item, _ = self.signup()
        self.assertEqual(item.scopes, [])
        duplicate = self.client.post(
            reverse("registration"), {**self.data, "username": "another", "email": "OWNER@EXAMPLE.INVALID"}
        )
        self.assertTrue(duplicate.context["form"].errors)
        self.assertEqual(InfrastructureRegistration.objects.count(), 1)

    def test_one_scheduler_pass_queues_and_sends_due_review_email(self):
        item, org = self.workspace()
        self.make_due(org)
        mail.outbox.clear()
        call_command("remind_inventory")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/review/", mail.outbox[0].body)
        self.assertEqual(InventoryReviewDelivery.objects.get().status, "sent")

    def test_optional_team_mailbox_is_separate_verified_and_notification_eligible(self):
        from .registration import prepare_team_verification
        from .inventory_review import reminder_recipients
        from .services import redeem_contact_token

        self.data["notification_email"] = "SECURITY@EXAMPLE.INVALID"
        item, org = self.workspace()
        self.assertEqual(item.notification_email, "security@example.invalid")
        team = item.notification_contact
        self.assertEqual(team.email, "security@example.invalid")
        self.assertIsNone(team.reachable_at)
        self.assertIsNone(team.reviewed_at)
        self.assertIsNone(team.availability_confirmed_at)
        self.assertNotIn(team.email, reminder_recipients(org.inventory_review_policy))
        self.assertTrue(prepare_team_verification(item))
        self.assertEqual(mail.outbox[-1].to, [team.email])
        self.assertFalse(prepare_team_verification(item))
        token = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body)[1]
        self.assertEqual(self.client.get(reverse("verify-contact")).status_code, 200)
        team.refresh_from_db()
        self.assertIsNone(team.reachable_at)
        self.assertTrue(redeem_contact_token(token))
        self.assertFalse(redeem_contact_token(token))
        self.assertIn(team.email, reminder_recipients(org.inventory_review_policy))
        team.refresh_from_db()
        self.assertIsNone(team.reviewed_at)
        self.assertIsNone(team.availability_confirmed_at)
        self.assertEqual(get_user_model().objects.filter(email=team.email).count(), 0)

    def test_team_verification_failure_keeps_primary_workspace_usable(self):
        self.data["notification_email"] = "noc@example.invalid"
        item, code = self.signup()
        with patch("portal.service_mail.send_service_mail", side_effect=OSError("private SMTP detail")):
            response = self.client.post(
                reverse("registration-verify"),
                {"code": code, "password1": PASSWORD, "password2": PASSWORD, "requested": "on"},
            )
        self.assertContains(response, "team mailbox verification could not be prepared")
        item.refresh_from_db()
        self.assertTrue(item.user.is_active)
        self.assertIsNotNone(item.organization)
        self.assertIsNone(item.notification_contact.reachable_at)
        self.assertNotContains(response, "private SMTP detail")
        self.assertTrue(self.client.login(username=item.user.username, password=PASSWORD))

    def test_team_email_validation_same_address_dedup_and_confirmation_cooldown(self):
        from .registration import prepare_team_verification

        self.data["notification_email"] = "invalid email"
        response = self.client.post(reverse("registration"), self.data)
        self.assertIn("notification_email", response.context["form"].errors)
        self.data["notification_email"] = self.data["email"].upper()
        item, org = self.workspace()
        self.assertIsNone(item.notification_contact_id)
        self.assertEqual(org.contacts.count(), 1)
        self.assertTrue(prepare_team_verification(item))

    def test_optional_company_address_persists_and_remains_scoped(self):
        address = "12 Example Road\nL-1234 Exampletown\nLuxembourg"
        self.data["company_address"] = address
        item, org = self.workspace()
        self.assertEqual(item.company_address, address)
        self.assertEqual(org.postal_address, address)
        self.login(item.user)
        self.assertContains(self.client.get(reverse("organization", args=[org.slug])), "L-1234 Exampletown")
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse("organization", args=[org.slug])).status_code, 404)
        self.login(self.analyst)
        self.assertEqual(self.client.get(reverse("organization", args=[org.slug])).status_code, 404)
        self.assertContains(
            self.client.get(reverse("registration-application", args=[item.pk])), "L-1234 Exampletown"
        )
        decide_registration(self.analyst, item.pk, "approve", "Reviewed")
        self.assertContains(self.client.get(reverse("organization", args=[org.slug])), "L-1234 Exampletown")
        self.assertEqual(
            self.client.post(
                reverse("company-address", args=[org.slug]), {"postal_address": "Changed"}
            ).status_code,
            403,
        )

    def test_address_can_be_corrected_without_changing_registration_or_sharing(self):
        from .models import AuditEvent

        self.data["company_address"] = "Original address"
        item, org = self.workspace()
        policy = org.inventory_review_policy
        token = review_token(item.user, policy, snapshot(org)[0])
        self.login(item.user)
        url = reverse("company-address", args=[org.slug])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.post(
                url, {"postal_address": "New address", "operator_visibility": "on", "name": "Forged"}
            ).status_code,
            302,
        )
        org.refresh_from_db()
        self.assertEqual(org.postal_address, "New address")
        self.assertFalse(org.operator_visibility)
        self.assertEqual(org.name, self.data["company_name"])
        item.refresh_from_db()
        self.assertEqual(item.company_address, "Original address")
        with self.assertRaises(ValidationError):
            confirm_review(item.user, org, token)
        event = AuditEvent.objects.get(action="organization.address_updated")
        self.assertNotIn("New address", str(event.details))
        self.assertEqual(self.client.post(url, {"postal_address": "x" * 1001}).status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.postal_address, "New address")
        self.assertEqual(self.client.post(url, {"postal_address": ""}).status_code, 302)
        org.refresh_from_db()
        self.assertEqual(org.postal_address, "")
        Membership.objects.filter(user=item.user, organization=org).update(role="editor")
        self.assertEqual(self.client.post(url, {"postal_address": "Editor address"}).status_code, 403)

    def test_company_address_is_optional_bounded_and_escaped(self):
        self.data["company_address"] = "x" * 1001
        response = self.client.post(reverse("registration"), self.data)
        self.assertIn("company_address", response.context["form"].errors)
        self.assertFalse(InfrastructureRegistration.objects.exists())
        self.data["company_address"] = '<script>alert("address")</script>'
        item, org = self.workspace()
        self.login(item.user)
        response = self.client.get(reverse("organization", args=[org.slug]))
        self.assertNotContains(response, '<script>alert("address")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.login(self.analyst)
        response = self.client.get(reverse("registration-application", args=[item.pk]))
        self.assertNotContains(response, '<script>alert("address")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_phone_and_each_participation_commitment_are_required(self):
        for field in ["emergency_phone", "consent", "attestation", "periodic_consent", "updates_consent"]:
            with self.subTest(field=field):
                response = self.client.post(reverse("registration"), {**self.data, field: ""})
                self.assertIn(field, response.context["form"].errors)
                self.assertFalse(InfrastructureRegistration.objects.exists())
        for phone in ["123", "not a telephone", "+0001234567", "+352123456789012345"]:
            response = self.client.post(reverse("registration"), {**self.data, "emergency_phone": phone})
            self.assertIn("emergency_phone", response.context["form"].errors)
        item, _ = self.signup()
        self.assertEqual(item.emergency_phone, "+352123456")
        self.assertEqual(item.commitments_version, "2026-11-18")
        self.assertIsNotNone(item.authority_attested_at)
        self.assertIsNotNone(item.periodic_review_consented_at)
        self.assertIsNotNone(item.updates_committed_at)

    def test_signup_cannot_choose_interval_or_disable_required_mail(self):
        response = self.client.get(reverse("registration"))
        self.assertContains(response, "Register your organization")
        self.assertNotContains(response, 'name="review_days"')
        self.assertNotContains(response, 'name="email_reminders"')
        self.data.update(review_days=365, email_reminders="")
        item, org = self.workspace()
        self.assertEqual(item.review_days, 90)
        self.assertTrue(item.email_reminders)
        self.assertEqual(org.inventory_review_policy.interval_days, 90)
        self.assertTrue(org.inventory_review_policy.email_enabled)
        self.assertEqual(org.contacts.get().emergency_phone, "+352123456")
        self.assertIsNone(org.contacts.get().availability_confirmed_at)
        self.assertFalse(org.claims.exists())

    def test_schedule_is_platform_or_current_shared_circl_only_and_mail_is_required(self):
        item, org = self.workspace()
        url = reverse("inventory-review", args=[org.slug])
        data = {"action": "settings", "interval_days": 14, "reminder_days": 2, "email_enabled": ""}
        self.login(item.user)
        page = self.client.get(url)
        self.assertNotContains(page, 'name="interval_days"')
        self.assertEqual(self.client.post(url, data).status_code, 403)
        with self.assertRaises(PermissionDenied):
            configure_review(item.user, org, data)
        self.login(self.analyst)
        self.assertEqual(self.client.post(url, data).status_code, 404)
        # An unrelated ordinary membership does not grant CIRCL schedule authority.
        Membership.objects.create(user=self.analyst, organization=org, role="reader")
        self.assertEqual(self.client.post(url, data).status_code, 403)
        decide_registration(self.analyst, item.pk, "approve", "Checked")
        response = self.client.get(url)
        self.assertContains(response, 'name="interval_days"')
        self.assertNotContains(response, 'name="email_enabled"')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        policy = org.inventory_review_policy
        policy.refresh_from_db()
        self.assertEqual(policy.interval_days, 14)
        self.assertTrue(policy.email_enabled)
        # Service-layer authorization must read current visibility even with a stale org object.
        org.operator_visibility = True
        Organization.objects.filter(pk=org.pk).update(operator_visibility=False)
        with self.assertRaises(PermissionDenied):
            configure_review(self.analyst, org, data)
        self.login(self.platform)
        self.assertEqual(self.client.post(url, data).status_code, 302)

    def test_legacy_registration_does_not_gain_retrospective_commitments(self):
        item, org = self.workspace()
        InfrastructureRegistration.objects.filter(pk=item.pk).update(
            authority_attested_at=None,
            periodic_review_consented_at=None,
            updates_committed_at=None,
            commitments_version="",
            emergency_phone="",
        )
        self.login(self.analyst)
        response = self.client.get(reverse("registration-application", args=[item.pk]))
        self.assertContains(response, "Legacy application")
        self.assertContains(response, "No retrospective agreement")
        item.refresh_from_db()
        self.assertIsNone(item.periodic_review_consented_at)

    def test_codes_expire_cannot_be_replayed_and_no_preselected_password_survives(self):
        item, code = self.signup()
        item.verification_expires = timezone.now() - timedelta(seconds=1)
        item.save()
        self.assertFalse(verify_registration(code, PASSWORD))
        item.verification_attempted_at = timezone.now() - timedelta(hours=1)
        item.save()
        self.assertTrue(issue_verification(item.pk))
        new = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body)[1]
        self.assertNotEqual(code, new)
        self.assertFalse(verify_registration(code, PASSWORD))
        self.assertTrue(verify_registration(new, PASSWORD))
        self.assertFalse(verify_registration(new, "attacker-other-pass"))
        self.assertTrue(get_user_model().objects.get(pk=item.user_id).check_password(PASSWORD))

    def test_rejection_retains_private_access_and_participants_cannot_approve(self):
        item, org = self.workspace()
        self.login(item.user)
        self.assertEqual(self.client.get(reverse("registration-applications")).status_code, 403)
        with self.assertRaises(PermissionDenied):
            decide_registration(item.user, item.pk, "approve", "")
        decide_registration(self.analyst, item.pk, "reject", "Scope needs further clarification")
        org.refresh_from_db()
        item.user.refresh_from_db()
        self.assertFalse(org.operator_visibility)
        self.assertTrue(item.user.is_active)
        self.assertEqual(self.client.get(reverse("organization", args=[org.slug])).status_code, 200)

    def test_registration_never_grants_existing_company_access_and_rate_limit_is_enforced(self):
        self.data["company_name"] = self.a.name
        item, org = self.workspace()
        self.assertNotEqual(org.pk, self.a.pk)
        self.assertFalse(Membership.objects.filter(user=item.user, organization=self.a).exists())
        with override_settings(PUBLIC_REGISTRATION_LIMIT=1):
            response = self.client.post(reverse("registration-resend"), {"email": item.email})
        self.assertEqual(response.status_code, 200)
        with override_settings(PUBLIC_REGISTRATION_LIMIT=1):
            response = self.client.post(
                reverse("registration"),
                {**self.data, "username": "another", "email": "different@example.invalid"},
            )
        self.assertEqual(response.status_code, 429)

    def test_manual_inventory_records_assets_and_versions_without_connector_jobs(self):
        item, org = self.workspace()
        self.login(item.user)
        with patch("portal.connectors.netbox.write_asset") as remote:
            response = self.client.post(
                reverse("create-asset", args=[org.slug]),
                {
                    "name": "Reported server",
                    "kind": "server",
                    "criticality": "normal",
                    "lifecycle": "active",
                    "responsible_team": "Owner team",
                },
            )
            remote.assert_not_called()
        asset = org.assets.get()
        self.assertEqual(asset.state, "recorded")
        self.assertEqual(InventoryWrite.objects.filter(asset=asset).count(), 0)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("create-installation", args=[org.slug, asset.pk]),
            {
                "product_name": "Owner product",
                "product_identifier": "owner:product",
                "version": "3.4.5",
                "component_type": "software",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(asset.installations.get().version, "3.4.5")

    def test_owner_confirmation_signed_data_snapshot_due_date_and_no_authority_upgrade(self):
        item, org = self.workspace()
        digest, counts = snapshot(org)
        policy = org.inventory_review_policy
        code = review_token(item.user, policy, digest)
        confirmation = confirm_review(item.user, org, code)
        policy.refresh_from_db()
        self.assertEqual(policy.next_due, timezone.localdate() + timedelta(days=90))
        self.assertEqual(confirmation.counts, counts)
        self.assertEqual(org.claims.filter(status="verified").count(), 0)
        self.assertIsNone(org.contacts.get().reviewed_at)
        with self.assertRaises(ValidationError):
            confirm_review(item.user, org, code)
        policy.refresh_from_db()
        code = review_token(item.user, policy, snapshot(org)[0])
        org.contacts.update(phone="new recorded number")
        with self.assertRaises(ValidationError):
            confirm_review(item.user, org, code)
        self.assertEqual(InventoryReviewConfirmation.objects.count(), 1)
        policy.refresh_from_db()
        code = review_token(item.user, policy, snapshot(org)[0])
        org.contacts.update(emergency_phone="+352654321")
        with self.assertRaises(ValidationError):
            confirm_review(item.user, org, code)

    def test_reminders_are_deduplicated_repeated_and_stopped_by_confirmation(self):
        item, org = self.workspace()
        policy = self.make_due(org)
        mail.outbox.clear()
        self.assertEqual(queue_review_reminders(policy.pk), 1)
        self.assertEqual(queue_review_reminders(policy.pk), 0)
        call_command("remind_inventory")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("review/", mail.outbox[0].body)
        self.assertNotIn("192.0.2", mail.outbox[0].body)
        self.assertEqual(InventoryReviewDelivery.objects.get().status, "sent")
        call_command("remind_inventory")
        self.assertEqual(len(mail.outbox), 1)
        policy.refresh_from_db()
        policy.next_reminder_at = timezone.now() - timedelta(days=8)
        policy.save()
        # Same-day repeat remains deduplicated even if a scheduler runs twice.
        self.assertEqual(queue_review_reminders(policy.pk), 0)
        policy.refresh_from_db()
        confirm_review(item.user, org, review_token(item.user, policy, snapshot(org)[0]))
        policy.refresh_from_db()
        self.assertGreater(policy.next_due, timezone.localdate())
        self.assertEqual(queue_review_reminders(policy.pk), 0)

    def test_mail_failure_is_retried_and_current_optout_or_review_suppresses_delivery(self):
        item, org = self.workspace()
        policy = self.make_due(org)
        queue_review_reminders(policy.pk)
        job = InventoryReviewDelivery.objects.get()
        with patch("portal.inventory_review.send_service_mail", side_effect=OSError("private SMTP response")):
            deliver_review_reminder(job.pk)
        job.refresh_from_db()
        self.assertEqual((job.status, job.attempts), ("error", 1))
        self.assertNotIn("private SMTP", job.error)
        job.next_attempt = timezone.now() - timedelta(seconds=1)
        job.save()
        policy.email_enabled = False
        policy.save()
        deliver_review_reminder(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "suppressed")

    def test_scope_correction_expires_old_proof_without_verifying_replacement(self):
        item, org = self.workspace()
        from .models import InfrastructureClaim
        claim = InfrastructureClaim.objects.create(organization=org, kind="ip", value="198.51.100.17")
        claim.status = "verified"
        claim.method = "Synthetic old operator check"
        claim.save()
        self.login(item.user)
        response = self.client.post(
            reverse("correct-scope", args=[org.slug, claim.pk]),
            {
                "kind": "ip",
                "value": "198.51.100.99",
                "network_context": "",
                "valid_from": timezone.now().isoformat(),
                "valid_until": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "expired")
        replacement = org.claims.get(value="198.51.100.99")
        self.assertEqual(replacement.status, "declared")
        self.assertEqual(replacement.method, "")

    def test_review_and_schedule_changes_require_current_company_admin(self):
        item, org = self.workspace()
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse("inventory-review", args=[org.slug])).status_code, 404)
        self.login(item.user)
        response = self.client.get(reverse("inventory-review", args=[org.slug]))
        self.assertContains(response, "Review infrastructure data")
        Membership.objects.filter(user=item.user, organization=org).update(role="reader")
        response = self.client.post(
            reverse("inventory-review", args=[org.slug]),
            {"action": "settings", "interval_days": 7, "reminder_days": 1, "email_enabled": "on"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(org.inventory_review_policy.interval_days, 90)

    def test_email_uses_operator_origin_and_mail_error_does_not_activate_user(self):
        with patch("portal.registration.send_service_mail", side_effect=OSError("private provider response")):
            response = self.client.post(reverse("registration"), self.data, HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 302)
        item = InfrastructureRegistration.objects.get()
        self.assertTrue(item.verification_error)
        self.assertFalse(item.user.is_active)
        self.assertFalse(item.user.has_usable_password())
        self.assertNotIn("private provider", str(item.verification_error))

    def test_csrf_registration_disabled_and_anonymous_verification_get_are_safe(self):
        csrf = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf.post(reverse("registration"), self.data).status_code, 403)
        with override_settings(PUBLIC_REGISTRATION_ENABLED=False):
            self.assertEqual(self.client.get(reverse("registration")).status_code, 403)
        self.assertEqual(self.client.get(reverse("registration-verify")).status_code, 200)
        self.assertEqual(InfrastructureRegistration.objects.count(), 0)

    def test_manual_inventory_freshness_follows_owner_review(self):
        from .circl import dashboard
        from .overview import company_states

        item, org = self.workspace()
        decide_registration(self.analyst, item.pk, "approve", "Checked application")
        self.assertEqual(dashboard(self.analyst)["sources"]["stale"], 1)
        self.assertTrue(company_states(item.user, [org])[0]["source_stale"])
        policy = org.inventory_review_policy
        confirm_review(item.user, org, review_token(item.user, policy, snapshot(org)[0]))
        org = Organization.objects.get(pk=org.pk)
        self.assertEqual(dashboard(self.analyst)["sources"]["stale"], 0)
        self.assertFalse(company_states(item.user, [org])[0]["source_stale"])

    def test_service_smtp_selection_and_pinned_origin(self):
        from .service_mail import public_base, send_service_mail
        from django.core.exceptions import ImproperlyConfigured

        with (
            override_settings(SERVICE_MAIL_TRANSPORT="smtp"),
            patch("portal.service_mail.get_connection") as connection,
            patch("portal.service_mail.EmailMessage") as message,
        ):
            message.return_value.send.return_value = 1
            send_service_mail("Review data", "Portal link only", "owner@example.invalid")
            connection.assert_called_once_with(backend="django.core.mail.backends.smtp.EmailBackend")
            message.return_value.send.assert_called_once_with(fail_silently=False)
        for origin in [
            "http://external.example.invalid",
            "https://user:pass@example.invalid",
            "https://example.invalid/path",
            "https://example.invalid/?token=private",
        ]:
            with override_settings(PUBLIC_BASE_URL=origin), self.assertRaises(ImproperlyConfigured):
                public_base()

    def test_schedule_is_configurable_without_postponing_unreviewed_data(self):
        item, org = self.workspace()
        self.login(self.platform)
        url = reverse("inventory-review", args=[org.slug])
        response = self.client.post(
            url, {"action": "settings", "interval_days": 14, "reminder_days": 2, "email_enabled": "on"}
        )
        self.assertEqual(response.status_code, 302)
        policy = org.inventory_review_policy
        self.assertEqual((policy.interval_days, policy.reminder_days), (14, 2))
        self.assertEqual(policy.next_due, timezone.localdate())
        confirm_review(item.user, org, review_token(item.user, policy, snapshot(org)[0]))
        configure_review(self.platform, org, {"interval_days": 7, "reminder_days": 1, "email_enabled": False})
        policy.refresh_from_db()
        self.assertEqual(policy.next_due, timezone.localdate() + timedelta(days=7))
        self.assertTrue(policy.email_enabled)
        response = self.client.post(url, {"action": "settings", "interval_days": 0, "reminder_days": 0})
        self.assertEqual(response.status_code, 200)
        policy.refresh_from_db()
        self.assertEqual(policy.interval_days, 7)

    def test_overdue_reminders_repeat_at_configured_interval_and_revocation_is_rechecked(self):
        item, org = self.workspace()
        policy = self.make_due(org)
        policy.reminder_days = 2
        policy.save()
        self.assertEqual(queue_review_reminders(policy.pk), 1)
        future = timezone.now() + timedelta(days=3)
        with patch("portal.inventory_review.timezone.now", return_value=future):
            self.assertEqual(queue_review_reminders(policy.pk), 1)
        self.assertEqual(InventoryReviewDelivery.objects.count(), 2)
        org.contacts.update(notification_enabled=False)
        Membership.objects.filter(user=item.user, organization=org).update(role="reader")
        for job in InventoryReviewDelivery.objects.all():
            with patch("portal.inventory_review.send_service_mail") as send:
                deliver_review_reminder(job.pk)
                send.assert_not_called()
            job.refresh_from_db()
            self.assertEqual(job.status, "suppressed")

    def test_forged_or_other_actor_review_token_does_not_confirm(self):
        item, org = self.workspace()
        policy = org.inventory_review_policy
        code = review_token(item.user, policy, snapshot(org)[0])
        with self.assertRaises(ValidationError):
            confirm_review(self.platform, org, code)
        with self.assertRaises(ValidationError):
            confirm_review(item.user, org, code + "invalid")
        self.assertEqual(InventoryReviewConfirmation.objects.count(), 0)


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentReviewQueueTests(TransactionTestCase):
    def test_two_schedulers_create_one_delivery_per_recipient(self):
        org = Organization.objects.create(name="Concurrent reporting", slug="concurrent-reporting")
        Contact.objects.create(
            organization=org,
            name="Synthetic owner",
            email="owner@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
        )
        policy = InventoryReviewPolicy.objects.create(
            organization=org,
            next_due=timezone.localdate(),
            next_reminder_at=timezone.now() - timedelta(minutes=1),
        )

        def queue():
            close_old_connections()
            try:
                return queue_review_reminders(policy.pk)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: queue(), range(2)))
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(InventoryReviewDelivery.objects.count(), 1)
