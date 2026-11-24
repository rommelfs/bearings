"""Synthetic mailbox verification, scoped reusable codes and concurrent acceptance quotas."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import domain_membership as domain
from .company_members import accept, invite
from .models import Membership, Organization, OrganizationInvitation, OrganizationDomainCode, AuditEvent
from .tests import Fixture

SETTINGS = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SERVICE_MAIL_TRANSPORT="file",
    PUBLIC_BASE_URL="https://example.invalid",
)


@override_settings(**SETTINGS)
class DomainCodeTests(Fixture):
    def issue(self, **kwargs):
        return domain.create(self.admin, self.a, "@EXAMPLE.INVALID", **kwargs)

    def challenge(self, raw, email="new@example.invalid"):
        self.assertTrue(domain.request_invitation(raw, email))
        return re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)[1]

    def join(self, raw, username="domain-new"):
        return accept(
            AnonymousUser(),
            raw,
            username=username,
            first_name="Synthetic",
            last_name="Member",
            password="Synthetic-local-Only!76248",
        )

    def test_domain_code_is_not_a_membership_or_mailbox_proof(self):
        item, raw = self.issue(role="editor")
        self.assertEqual(item.domain, "example.invalid")
        with self.assertRaises(ValidationError):
            self.join(raw)
        count = Membership.objects.count()
        personal = self.challenge(raw)
        self.assertEqual(Membership.objects.count(), count)
        self.assertNotEqual(personal, raw)
        self.assertEqual(self.join(personal), self.a)
        user = get_user_model().objects.get(username="domain-new")
        self.assertEqual(Membership.objects.get(user=user).role, "editor")
        self.assertFalse(user.is_staff or user.is_superuser or user.groups.exists())
        self.assertNotIn(raw, str(list(AuditEvent.objects.values())))
        with self.assertRaises(ValidationError):
            self.join(personal)
        self.assertTrue(
            OrganizationInvitation.objects.filter(domain_code=item, consumed_at__isnull=False).exists()
        )

    def test_exact_domain_only_and_opaque_public_responses(self):
        _, raw = self.issue()
        path = reverse("company-domain-join")
        bodies = []
        for email, code in [
            ("user@sub.example.invalid", raw),
            ("user@notexample.invalid", raw),
            ("user@example.invalid.attacker.invalid", raw),
            ("user@example.invalid", "bad-code"),
        ]:
            response = self.client.post(path, {"code": code, "email": email})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "No access has been granted yet")
            self.assertIn("no-store", response.headers["Cache-Control"])
            bodies.append(response.content)
        self.assertEqual(len(set(bodies)), 1)
        self.assertFalse(OrganizationInvitation.objects.exists())
        self.assertTrue(domain.request_invitation(raw, "NEW@EXAMPLE.INVALID"))

    def test_revoke_expire_quota_and_creator_changes_rechecked_after_mail(self):
        for change in ["revoke", "expire", "quota", "creator", "archive", "role"]:
            with self.subTest(change=change):
                item, raw = self.issue()
                personal = self.challenge(raw, change + "@example.invalid")
                if change == "revoke":
                    domain.revoke(self.admin, self.a, item.pk)
                elif change == "expire":
                    OrganizationDomainCode.objects.filter(pk=item.pk).update(
                        expires_at=timezone.now() - timedelta(seconds=1)
                    )
                elif change == "quota":
                    OrganizationDomainCode.objects.filter(pk=item.pk).update(max_acceptances=0)
                elif change == "creator":
                    Membership.objects.filter(organization=self.a, user=self.admin).update(role="reader")
                elif change == "archive":
                    Organization.objects.filter(pk=self.a.pk).update(merged_into=self.b)
                else:
                    OrganizationInvitation.objects.filter(domain_code=item).update(role="admin")
                with self.assertRaises(ValidationError):
                    self.join(personal, username=change)
                Membership.objects.filter(organization=self.a, user=self.admin).update(role="admin")
                Organization.objects.filter(pk=self.a.pk).update(merged_into=None)
                self.a.refresh_from_db()

    def test_default_reader_quota_and_existing_account_protection(self):
        _, raw = self.issue(max_acceptances=1)
        personal = self.challenge(raw)
        self.join(personal)
        self.assertEqual(Membership.objects.get(user__username="domain-new").role, "reader")
        self.assertFalse(domain.request_invitation(raw, "another@example.invalid"))
        self.reader.email = "reader@example.invalid"
        self.reader.save()
        _, other = self.issue(role="editor")
        personal = self.challenge(other, self.reader.email)
        with self.assertRaises(ValidationError):
            self.join(personal)
        password = self.reader.password
        accept(self.reader, personal)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.password, password)
        self.assertEqual(Membership.objects.get(user=self.reader, organization=self.a).role, "reader")

    def test_domain_request_cannot_revoke_a_personal_invitation(self):
        personal = invite(self.admin, self.a, "separate@example.invalid", "admin")
        OrganizationInvitation.objects.filter(pk=personal.pk).update(
            created_at=timezone.now() - timedelta(minutes=6)
        )
        _, raw = self.issue()
        self.challenge(raw, "separate@example.invalid")
        personal.refresh_from_db()
        self.assertIsNone(personal.revoked_at)
        self.assertEqual(
            OrganizationInvitation.objects.filter(email=personal.email, revoked_at=None).count(), 2
        )

    def test_admin_scope_limited_roles_secret_once_csrf_and_mail_errors(self):
        for user in [self.reader, self.editor, self.analyst, self.platform]:
            with self.assertRaises(PermissionDenied):
                domain.create(user, self.a, "example.invalid")
        for value in [
            "*.example.invalid",
            "https://example.invalid",
            "example.invalid.",
            "user@example.invalid",
        ]:
            with self.assertRaises(ValidationError):
                domain.domain_name(value)
        with self.assertRaises(ValidationError):
            self.issue(role="admin")
        self.login(self.admin)
        url = reverse("company-members", args=[self.a.slug])
        response = self.client.post(
            url,
            {
                "action": "domain-create",
                "domain-domain": "example.invalid",
                "domain-role": "reader",
                "domain-days": 30,
                "domain-max_acceptances": 100,
            },
        )
        self.assertEqual(response.status_code, 200)
        raw = response.context["created_code"]
        self.assertEqual(len(raw), 43)
        self.assertContains(response, raw)
        self.assertNotContains(self.client.get(url), raw)
        item = OrganizationDomainCode.objects.get()
        with self.assertRaises(PermissionDenied):
            domain.revoke(self.admin, self.b, item.pk)
        with patch("portal.company_members.send_service_mail", side_effect=OSError):
            self.assertFalse(domain.request_invitation(raw, "mailerror@example.invalid"))
        self.assertTrue(OrganizationInvitation.objects.get(domain_code=item).mail_error)
        self.assertEqual(
            Client(enforce_csrf_checks=True)
            .post(reverse("company-domain-join"), {"code": raw, "email": "csrf@example.invalid"})
            .status_code,
            403,
        )
        with patch("portal.member_views.permit_public_attempt", return_value=False):
            self.assertContains(
                self.client.post(
                    reverse("company-domain-join"), {"code": raw, "email": "rate@example.invalid"}
                ),
                "Too many attempts",
            )


@skipUnless(connection.vendor == "postgresql", "Concurrent quota validation requires PostgreSQL")
@override_settings(**SETTINGS)
class ConcurrentDomainCodeTests(TransactionTestCase):
    def test_last_acceptance_slot_cannot_be_claimed_twice(self):
        org = Organization.objects.create(name="Synthetic domain quota", slug="synthetic-domain-quota")
        user = get_user_model().objects.create_user("domain-owner")
        Membership.objects.create(user=user, organization=org, role="admin")
        item, raw = domain.create(user, org, "example.invalid", max_acceptances=1)
        codes = []
        for i in range(2):
            self.assertTrue(domain.request_invitation(raw, f"parallel{i}@example.invalid"))
            codes.append(re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)[1])

        def join(pair):
            i, code = pair
            try:
                accept(
                    AnonymousUser(),
                    code,
                    username=f"parallel{i}",
                    first_name="Synthetic",
                    last_name="Quota",
                    password="Synthetic-local-Only!76248",
                )
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(join, enumerate(codes))), 1)
        self.assertEqual(
            OrganizationInvitation.objects.filter(domain_code=item, consumed_at__isnull=False).count(), 1
        )
        self.assertEqual(Membership.objects.filter(organization=org).count(), 2)
