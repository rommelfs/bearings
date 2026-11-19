"""Administrative activation never forges mailbox proof or grants operator privileges."""

import hashlib
import re
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .registration_forms import InfrastructureRegistrationForm
from .registration import (
    submit_registration,
    activate_registration_override,
    issue_verification,
    verify_registration,
    decide_registration,
)
from .models import AuditEvent, Membership, Organization


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SERVICE_MAIL_TRANSPORT="file",
    PUBLIC_BASE_URL="https://example.invalid",
)
class RegistrationOverrideTests(Fixture):
    def pending(self):
        form = InfrastructureRegistrationForm(
            {
                "username": "pending-owner",
                "company_name": "Synthetic Pending",
                "first_name": "Synthetic",
                "last_name": "Owner",
                "job_title": "System administrator",
                "email": "owner@example.invalid",
                "emergency_phone": "+352123456",
                "consent": "on",
                "attestation": "on",
                "periodic_consent": "on",
                "updates_consent": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        return submit_registration(form)

    def test_override_creates_private_access_without_mailbox_proof_then_owner_sets_password(self):
        item = self.pending()
        issue_verification(item.pk)
        old = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body)[1]
        count = len(mail.outbox)
        item, link = activate_registration_override(
            self.platform, item.pk, "Local lab mailbox delivery unavailable"
        )
        token = link.split("#token=")[1]
        item.refresh_from_db()
        item.user.refresh_from_db()
        self.assertTrue(item.user.is_active)
        self.assertFalse(item.user.has_usable_password())
        self.assertEqual(item.status, "awaiting_review")
        self.assertEqual((item.user.first_name, item.user.last_name), ("Synthetic", "Owner"))
        self.assertEqual(item.organization.contacts.get().name, "Synthetic Owner")
        self.assertEqual(item.organization.contacts.get().role, "System administrator")
        self.assertIsNone(item.email_verified_at)
        self.assertFalse(item.organization.operator_visibility)
        self.assertIsNone(item.organization.contacts.get().reachable_at)
        self.assertEqual(item.manually_activated_by, self.platform)
        self.assertEqual(len(mail.outbox), count)
        self.assertFalse(verify_registration(old, "Synthetic-owner-Only!872"))
        self.assertEqual(item.verification_digest, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(list(AuditEvent.objects.values("details"))))
        verified = verify_registration(token, "Synthetic-owner-Only!872")
        self.assertTrue(verified)
        verified.user.refresh_from_db()
        self.assertTrue(verified.user.check_password("Synthetic-owner-Only!872"))
        self.assertIsNone(verified.email_verified_at)
        self.assertFalse(verify_registration(token, "Another-owner-Only!872"))
        self.assertEqual(Membership.objects.filter(user=verified.user).count(), 1)
        self.assertFalse(
            verified.user.is_staff or verified.user.is_superuser or verified.user.groups.exists()
        )
        decide_registration(self.analyst, item.pk, "approve", "Separate CIRCL sharing review")
        item.organization.refresh_from_db()
        self.assertTrue(item.organization.operator_visibility)

    def test_only_platform_can_override_and_existing_privileges_or_password_are_preserved(self):
        item = self.pending()
        for actor in [self.admin, self.analyst, self.editor]:
            with self.assertRaises(PermissionDenied):
                activate_registration_override(actor, item.pk, "Denied override")
        user = item.user
        for attribute in ["is_staff", "is_superuser", "is_active"]:
            setattr(user, attribute, True)
            user.save()
            with self.assertRaises(PermissionDenied):
                activate_registration_override(self.platform, item.pk, "Preserve changed account")
            setattr(user, attribute, False)
            user.save()
        user.set_password("Existing-local-password!872")
        user.save()
        with self.assertRaises(PermissionDenied):
            activate_registration_override(self.platform, item.pk, "Cannot overwrite a password")
        self.assertEqual(Organization.objects.count(), 2)
        self.assertFalse(item.organization_id)

    def test_reissue_invalidates_previous_link_and_cannot_reset_an_activated_password(self):
        item = self.pending()
        item, first = activate_registration_override(self.platform, item.pk, "Synthetic first override")
        _, second = activate_registration_override(self.platform, item.pk, "Synthetic reissue")
        self.assertFalse(verify_registration(first.split("#token=")[1], "Synthetic-owner-Only!872"))
        token = second.split("#token=")[1]
        item.verification_expires = timezone.now() - timedelta(seconds=1)
        item.save(update_fields=["verification_expires"])
        self.assertFalse(verify_registration(token, "Synthetic-owner-Only!872"))
        _, third = activate_registration_override(self.platform, item.pk, "New link after expiry")
        self.assertTrue(verify_registration(third.split("#token=")[1], "Synthetic-owner-Only!872"))
        with self.assertRaises(PermissionDenied):
            activate_registration_override(self.platform, item.pk, "Password reset is not this action")
        self.assertEqual(Membership.objects.filter(user=item.user).count(), 1)

    def test_staff_membership_and_group_changes_refuse_token_and_override_atomically(self):
        item = self.pending()
        Membership.objects.create(user=item.user, organization=self.a, role="reader")
        with self.assertRaises(PermissionDenied):
            activate_registration_override(self.platform, item.pk, "Changed grants")
        Membership.objects.filter(user=item.user).delete()
        item, link = activate_registration_override(self.platform, item.pk, "Synthetic admin override")
        item.user.groups.add(Group.objects.create(name="Unexpected later role"))
        self.assertFalse(verify_registration(link.split("#token=")[1], "Synthetic-owner-Only!872"))
        self.assertFalse(item.user.has_usable_password())

    def test_portal_override_requires_reason_checkbox_and_csrf_and_admin_backend_lists_registrations(self):
        item = self.pending()
        url = reverse("registration-application", args=[item.pk])
        self.login(self.platform)
        response = self.client.get(reverse("admin:portal_infrastructureregistration_changelist"))
        self.assertContains(response, "Synthetic Pending")
        self.assertContains(self.client.get(url), "Administrative activation override")
        self.client.post(url, {"action": "override", "note": "", "checked": "on"})
        item.refresh_from_db()
        self.assertEqual(item.status, "awaiting_email")
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.platform)
        self.assertEqual(
            strict.post(url, {"action": "override", "note": "Synthetic", "checked": "on"}).status_code, 403
        )
        response = self.client.post(
            url, {"action": "override", "note": "Synthetic lab activation", "checked": "on"}
        )
        self.assertContains(response, "Administrative activation prepared")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        token = response.context["activation_url"].split("#token=")[1]
        # GET link scanners do not consume administrative activation.
        self.client.get(reverse("registration-verify"))
        item.refresh_from_db()
        self.assertEqual(item.verification_digest, hashlib.sha256(token.encode()).hexdigest())
        owner = Client()
        response = owner.post(
            reverse("registration-verify"),
            {
                "code": token,
                "password1": "Synthetic-owner-Only!872",
                "password2": "Synthetic-owner-Only!872",
                "requested": "on",
            },
        )
        self.assertContains(response, "email address remains unconfirmed")
        self.assertNotContains(response, "Email confirmed and password set")
        self.assertTrue(owner.login(username="pending-owner", password="Synthetic-owner-Only!872"))

    def test_operator_retry_surfaces_failure_and_rotates_link_without_public_cooldown_bypass(self):
        item = self.pending()
        self.assertTrue(issue_verification(item.pk))
        self.assertFalse(issue_verification(item.pk))
        with self.assertRaises(PermissionDenied):
            issue_verification(item.pk, actor=self.analyst)
        self.login(self.platform)
        url = reverse("registration-application", args=[item.pk])
        with patch("portal.registration.send_service_mail", side_effect=OSError("Private relay error")):
            response = self.client.post(url, {"action": "retry_email", "checked": "on"}, follow=True)
        self.assertContains(response, "Last verification send failed")
        self.assertNotContains(response, "Private relay error")
        item.refresh_from_db()
        self.assertTrue(item.verification_error)
        response = self.client.post(url, {"action": "retry_email", "checked": "on"}, follow=True)
        self.assertContains(response, "saved to the local outbox")
        item.refresh_from_db()
        self.assertFalse(item.verification_error)
        self.assertFalse(item.user.is_active)

    def test_local_mail_ui_is_admin_only_bounded_escaped_and_not_an_arbitrary_file_reader(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(EMAIL_FILE_PATH=directory):
            file = Path(directory) / "20261118-message.log"
            file.write_text(
                "To: synthetic@example.invalid\n<script>alert(1)</script>\n#token=synthetic-token"
            )
            (Path(directory) / "ignored.txt").write_text("Do not expose")
            (Path(directory) / "linked.log").symlink_to(file)
            url = reverse("service-mail")
            for user in [self.admin, self.analyst, self.reader]:
                self.login(user)
                self.assertEqual(self.client.get(url).status_code, 403)
            self.login(self.platform)
            self.assertContains(self.client.get(url), "Local delivery is active")
            key = hashlib.sha256(file.name.encode()).hexdigest()
            response = self.client.get(reverse("service-mail-message", args=[key]))
            self.assertContains(response, "&lt;script&gt;", html=False)
            self.assertNotContains(response, "<script>alert(1)</script>")
            self.assertContains(response, "#token=synthetic-token")
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual(len(response.context["rows"]), 1)
            self.assertEqual(
                self.client.get(reverse("service-mail-message", args=["unknown"])).status_code, 404
            )
            with override_settings(SERVICE_MAIL_TRANSPORT="smtp", EMAIL_HOST="relay.example.invalid"):
                response = self.client.get(url)
                self.assertContains(response, "SMTP delivery is configured")
                self.assertNotContains(response, "synthetic-token")
                self.assertEqual(
                    self.client.get(reverse("service-mail-message", args=[key])).status_code, 404
                )
