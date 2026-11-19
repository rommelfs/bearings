from django.test import TransactionTestCase
from django.db import connection, close_old_connections
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
import threading
import re
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import (
    Organization,
    Membership,
    OrganizationInvitation,
    InventorySource,
    Contact,
    Product,
    AuditEvent,
)
from .company_members import invite, accept, change_member
from .company_merge import plan, merge


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SERVICE_MAIL_TRANSPORT="file",
    PUBLIC_BASE_URL="https://example.invalid",
)
class CompanyMembersTests(Fixture):
    def issue(self, email="new@example.invalid", role="reader"):
        item = invite(self.admin, self.a, email, role)
        code = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)[1]
        return item, code

    def test_new_user_joins_exact_company_with_mail_proof_and_no_staff_privileges(self):
        count = Organization.objects.count()
        item, code = self.issue(role="admin")
        org = accept(
            AnonymousUser(),
            code,
            username="new",
            first_name="New",
            last_name="Member",
            password="A-long-fresh-password-762!",
        )
        user = get_user_model().objects.get(username="new")
        self.assertEqual(org, self.a)
        self.assertEqual(Organization.objects.count(), count)
        self.assertEqual(Membership.objects.get(user=user).role, "admin")
        self.assertFalse(user.is_staff or user.is_superuser or user.groups.exists())
        self.assertNotIn(code, str(list(AuditEvent.objects.values())))
        self.assertNotEqual(item.digest, code)
        with self.assertRaises(ValidationError):
            accept(user, code)

    def test_existing_account_requires_login_and_keeps_password_and_target_role(self):
        old = self.reader.password
        self.reader.email = "reader@example.invalid"
        self.reader.save()
        _, code = self.issue(self.reader.email, "admin")
        with self.assertRaises(ValidationError):
            accept(AnonymousUser(), code, username="another", password="anything")
        accept(self.reader, code)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.password, old)
        self.assertEqual(Membership.objects.get(user=self.reader, organization=self.a).role, "reader")

    def test_foreign_account_and_ambiguous_email_cannot_accept(self):
        _, code = self.issue()
        with self.assertRaises(PermissionDenied):
            accept(self.reader, code)
        get_user_model().objects.create_user("duplicate1", email="new@example.invalid")
        other = get_user_model().objects.create_user("duplicate2", email="new@example.invalid")
        with self.assertRaises(PermissionDenied):
            accept(other, code)

    def test_current_admin_revocation_expiry_and_reinvite(self):
        item, code = self.issue()
        item.expires_at = timezone.now() - timedelta(seconds=1)
        item.save()
        with self.assertRaises(ValidationError):
            accept(AnonymousUser(), code)
        item.created_at -= timedelta(minutes=6)
        item.save()
        newer, code2 = self.issue()
        item.refresh_from_db()
        self.assertIsNotNone(item.revoked_at)
        Membership.objects.filter(user=self.admin, organization=self.a).update(role="editor")
        with self.assertRaises(ValidationError):
            accept(AnonymousUser(), code2)
        self.assertNotEqual(newer.digest, item.digest)

    def test_only_company_admin_invites_and_cannot_grant_platform_role(self):
        for user in [self.editor, self.reader, self.analyst, self.platform]:
            with self.assertRaises(PermissionDenied):
                invite(user, self.a, "new@example.invalid", "reader")
        with self.assertRaises(ValidationError):
            invite(self.admin, self.a, "new@example.invalid", "superuser")
        with self.assertRaises(PermissionDenied):
            invite(self.admin, self.b, "new@example.invalid", "admin")

    def test_last_admin_and_foreign_member_guard(self):
        with self.assertRaises(ValidationError):
            change_member(
                self.admin, self.a, Membership.objects.get(user=self.admin, organization=self.a).pk, "remove"
            )
        reader = Membership.objects.get(user=self.reader, organization=self.a)
        change_member(self.admin, self.a, reader.pk, "admin")
        change_member(self.reader, self.a, reader.pk, "editor")
        with self.assertRaises(PermissionDenied):
            change_member(self.editor, self.a, reader.pk, "admin")

    def test_mail_failure_and_rate_limit_are_not_membership_success(self):
        with patch("portal.company_members.send_service_mail", side_effect=OSError):
            item = invite(self.admin, self.a, "new@example.invalid", "reader")
        self.assertTrue(item.mail_error)
        self.assertFalse(Membership.objects.filter(user__email="new@example.invalid").exists())
        with self.assertRaises(ValidationError):
            invite(self.admin, self.a, "new@example.invalid", "reader")

    def test_http_csrf_public_join_no_get_mutation_and_no_foreign_company_list(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        url = reverse("company-members", args=[self.a.slug])
        self.assertEqual(
            client.post(
                url, {"action": "invite", "email": "new@example.invalid", "role": "reader"}
            ).status_code,
            403,
        )
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("company-members", args=[self.b.slug])).status_code, 403)
        self.assertContains(self.client.get(url), "Invite a member")
        _, code = self.issue()
        self.client.logout()
        self.assertEqual(self.client.get(reverse("company-join") + "#token=" + code).status_code, 200)
        self.assertFalse(OrganizationInvitation.objects.get(email="new@example.invalid").consumed_at)
        response = self.client.post(
            reverse("company-join"),
            {
                "code": code,
                "confirmed": "on",
                "username": "web-new",
                "first_name": "Web",
                "last_name": "Member",
                "password1": "Unrelated-fresh-Password321!",
                "password2": "Unrelated-fresh-Password321!",
            },
        )
        self.assertContains(response, "You are now a member")
        self.assertNotContains(response, code)


class CompanyMergeTests(Fixture):
    def setUp(self):
        # Separate simple local companies, not connector-owned fixture inventories.
        self.source = Organization.objects.create(
            name="Duplicate", slug="duplicate", operator_visibility=False
        )
        self.target = Organization.objects.create(name="Keep", slug="keep", operator_visibility=True)
        self.ssource = InventorySource.objects.create(organization=self.source, mode="manual")
        InventorySource.objects.create(organization=self.target, mode="manual")
        Membership.objects.create(organization=self.source, user=self.admin, role="admin")
        Membership.objects.create(organization=self.target, user=self.admin, role="reader")
        Membership.objects.create(organization=self.target, user=self.reader, role="admin")

    def test_reviewed_merge_preserves_target_roles_and_history_archives_source(self):
        contact = Contact.objects.create(
            organization=self.source, name="Keep contact", email="contact@example.invalid"
        )
        AuditEvent.objects.create(organization=self.source, actor=self.admin, action="before")
        preview = plan(self.platform, self.source, self.target)
        self.assertEqual(preview["blockers"], [])
        merge(self.platform, preview["ticket"])
        contact.refresh_from_db()
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(contact.organization, self.target)
        self.assertEqual(self.source.merged_into, self.target)
        self.assertFalse(self.target.operator_visibility)
        self.assertEqual(Membership.objects.get(organization=self.target, user=self.admin).role, "reader")
        self.assertFalse(self.source.membership_set.exists())
        self.assertTrue(AuditEvent.objects.filter(organization=self.source, action="before").exists())
        with self.assertRaises(ValidationError):
            merge(self.platform, preview["ticket"])

    def test_changes_after_preview_refuse_atomic_merge(self):
        preview = plan(self.platform, self.source, self.target)
        Contact.objects.create(organization=self.source, name="New", email="new@example.invalid")
        with self.assertRaises(ValidationError):
            merge(self.platform, preview["ticket"])
        self.assertTrue(self.source.membership_set.exists())
        self.assertTrue(self.source.contacts.exists())

    def test_source_bindings_and_identity_collisions_block(self):
        self.ssource.mode = "external"
        self.ssource.save()
        self.assertTrue(plan(self.platform, self.source, self.target)["blockers"])
        self.ssource.mode = "manual"
        self.ssource.save()
        Product.objects.create(organization=self.source, name="Same", identifier="same")
        Product.objects.create(organization=self.target, name="Same", identifier="same")
        preview = plan(self.platform, self.source, self.target)
        self.assertTrue(preview["blockers"])
        with self.assertRaises(ValidationError):
            merge(self.platform, preview["ticket"])

    def test_empty_duplicate_can_join_existing_native_target_without_rebinding_it(self):
        target_source = InventorySource.objects.get(organization=self.target)
        target_source.mode = "central"
        target_source.save()
        self.assertFalse(plan(self.platform, self.source, self.target)["blockers"])
        merge(self.platform, plan(self.platform, self.source, self.target)["ticket"])
        target_source.refresh_from_db()
        self.assertEqual(target_source.mode, "central")
        self.assertEqual(target_source.organization, self.target)

    def test_manual_assets_cannot_enter_native_authoritative_target(self):
        from .models import Asset

        target_source = InventorySource.objects.get(organization=self.target)
        target_source.mode = "central"
        target_source.save()
        Asset.objects.create(organization=self.source, source=self.ssource, name="Manual", kind="server")
        preview = plan(self.platform, self.source, self.target)
        self.assertTrue(preview["blockers"])
        with self.assertRaises(ValidationError):
            merge(self.platform, preview["ticket"])

    def test_late_failure_rolls_back_all_data_and_membership_transfers(self):
        contact = Contact.objects.create(
            organization=self.source, name="Retained", email="retained@example.invalid"
        )
        ticket = plan(self.platform, self.source, self.target)["ticket"]
        with patch("portal.company_merge.audit", side_effect=RuntimeError("Synthetic late rollback")):
            with self.assertRaises(RuntimeError):
                merge(self.platform, ticket)
        contact.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(contact.organization, self.source)
        self.assertIsNone(self.source.merged_into)
        self.assertTrue(self.source.membership_set.exists())

    def test_merge_is_platform_only_and_tamper_protected(self):
        with self.assertRaises(PermissionDenied):
            plan(self.admin, self.source, self.target)
        with self.assertRaises(ValidationError):
            merge(self.platform, "tampered")
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.get(reverse("company-merge")).status_code, 403)
        self.client.force_login(self.platform)
        self.assertContains(self.client.get(reverse("company-merge")), "Merge organizations")

    def test_overlap_cannot_leave_merged_company_without_an_active_admin(self):
        Membership.objects.filter(organization=self.target, user=self.reader).delete()
        preview = plan(self.platform, self.source, self.target)
        self.assertTrue(any("active company administrator" in b for b in preview["blockers"]))

    def test_manual_asset_installation_and_evidence_identity_survive(self):
        from .models import Asset, Installation

        asset = Asset.objects.create(
            organization=self.source, source=self.ssource, name="Manual server", kind="server"
        )
        product = Product.objects.create(
            organization=self.source, name="Unique software", identifier="unique"
        )
        installation = Installation.objects.create(asset=asset, product=product, version="1.2")
        ticket = plan(self.platform, self.source, self.target)["ticket"]
        merge(self.platform, ticket)
        asset.refresh_from_db()
        product.refresh_from_db()
        installation.refresh_from_db()
        self.assertEqual(asset.organization, self.target)
        self.assertEqual(asset.source.organization, self.target)
        self.assertEqual(product.organization, self.target)
        self.assertEqual(installation.asset_id, asset.pk)


@skipUnless(connection.vendor == "postgresql", "Real row locking requires PostgreSQL")
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SERVICE_MAIL_TRANSPORT="file",
    PUBLIC_BASE_URL="https://example.invalid",
)
class MembershipConcurrencyTests(TransactionTestCase):
    def test_concurrent_invitation_redemption_creates_one_membership(self):
        user = get_user_model().objects.create_user("member", email="member@example.invalid")
        owner = get_user_model().objects.create_user("owner", email="owner@example.invalid")
        org = Organization.objects.create(name="One company", slug="one-company")
        Membership.objects.create(user=owner, organization=org, role="admin")
        invite(owner, org, user.email, "editor")
        code = re.search(r"#token=([A-Za-z0-9_-]+)", mail.outbox[-1].body)[1]
        barrier = threading.Barrier(2)

        def run():
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                try:
                    accept(actor, code)
                    return "accepted"
                except ValidationError:
                    return "replayed"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertCountEqual(results, ["accepted", "replayed"])
        self.assertEqual(Membership.objects.filter(user=user, organization=org).count(), 1)
