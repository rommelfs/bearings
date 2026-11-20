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


@override_settings(SECRET_KEY="synthetic-merge-credential-key-which-is-long-enough")
class PersonalMISPMergeTests(Fixture):
    def setUp(self):
        CompanyMergeTests.setUp(self)
        import uuid
        from .models import MISPServer, MISPInstance, MISPEvent
        from .misp_credentials import encrypt

        self.server = MISPServer.objects.create(
            name="Merge fixture", base_url="https://misp.example.invalid", enabled=True
        )
        self.misp = MISPInstance(
            organization=self.source,
            owner=self.admin,
            server=self.server,
            name="Personal merge fixture",
            credential_kind="encrypted",
            enabled=True,
            misp_user_id=42,
            base_url=self.server.base_url,
            token_env_var="MISP_MERGE_FIXTURE_TOKEN",
            last_success=timezone.now(),
        )
        self.misp.credential_ciphertext = encrypt(self.misp, "synthetic-personal-key")
        self.misp.save()
        self.event = MISPEvent.objects.create(
            source=self.misp,
            event_uuid=uuid.uuid4(),
            remote_id=1,
            timestamp=1,
            info="Private synthetic event",
            digest="a" * 64,
            payload={"synthetic": True},
        )

    def test_explicit_retirement_keeps_key_cache_and_native_target_identity(self):
        from .misp_credentials import decrypt
        from .misp import visible_events

        self.assertTrue(plan(self.platform, self.source, self.target)["blockers"])
        target_inventory = self.target.inventory_source
        target_inventory.mode = "central"
        target_inventory.save()
        ciphertext = self.misp.credential_ciphertext
        preview = plan(self.platform, self.source, self.target, retire_personal_misp=True)
        self.assertFalse(preview["blockers"])
        merge(self.platform, preview["ticket"])
        self.misp.refresh_from_db()
        self.event.refresh_from_db()
        target_inventory.refresh_from_db()
        self.assertFalse(self.misp.enabled)
        self.assertEqual(self.misp.organization_id, self.source.pk)
        self.assertEqual(self.misp.credential_ciphertext, ciphertext)
        self.assertEqual(decrypt(self.misp), "synthetic-personal-key")
        self.assertEqual(self.event.source_id, self.misp.pk)
        self.assertEqual(target_inventory.mode, "central")
        self.assertEqual(target_inventory.organization_id, self.target.pk)
        self.assertFalse(visible_events(self.admin).filter(pk=self.event.pk).exists())
        self.assertTrue(Membership.objects.filter(organization=self.target, user=self.admin).exists())
        self.assertEqual(
            AuditEvent.objects.get(action="organization.merged").details["retired_personal_misp"],
            [self.misp.pk],
        )

    def test_active_refresh_and_nonpersonal_source_still_block(self):
        self.misp.syncing_until = timezone.now() + timedelta(minutes=1)
        self.misp.save()
        preview = plan(self.platform, self.source, self.target, retire_personal_misp=True)
        self.assertTrue(any("refresh is in progress" in b for b in preview["blockers"]))
        self.misp.syncing_until = None
        self.misp.credential_kind = "environment"
        self.misp.save()
        self.assertTrue(plan(self.platform, self.source, self.target, retire_personal_misp=True)["blockers"])

    def test_retirement_is_fingerprinted_and_late_failure_rolls_it_back(self):
        preview = plan(self.platform, self.source, self.target, retire_personal_misp=True)
        with patch("portal.company_merge.audit", side_effect=RuntimeError("Rollback fixture")):
            with self.assertRaises(RuntimeError):
                merge(self.platform, preview["ticket"])
        self.misp.refresh_from_db()
        self.source.refresh_from_db()
        self.assertTrue(self.misp.enabled)
        self.assertIsNone(self.source.merged_into_id)
        self.misp.enabled = False
        self.misp.save()
        with self.assertRaises(ValidationError):
            merge(self.platform, preview["ticket"])

    def test_browser_form_retirement_requires_preview_and_keeps_credentials_out_of_html(self):
        self.client.force_login(self.platform)
        response = self.client.post(
            reverse("company-merge"),
            {
                "action": "preview",
                "source": self.source.pk,
                "target": self.target.pk,
                "retire_personal_misp": "on",
            },
        )
        self.assertContains(response, "Confirm reviewed merge")
        self.assertNotContains(response, self.misp.credential_ciphertext)
        self.assertNotContains(response, "synthetic-personal-key")
        ticket = response.context["preview"]["ticket"]
        result = self.client.post(
            reverse("company-merge"), {"action": "commit", "ticket": ticket, "confirmed": "yes"}
        )
        self.assertRedirects(result, reverse("organization", args=[self.target.slug]))
        from .workspace_views import SESSION_COMPANY

        self.assertEqual(self.client.session[SESSION_COMPANY], self.target.pk)
        self.misp.refresh_from_db()
        self.assertFalse(self.misp.enabled)


class MergedReviewScheduleTests(Fixture):
    def setUp(self):
        CompanyMergeTests.setUp(self)

    def test_registered_duplicate_keeps_mandatory_review_on_bare_native_target(self):
        from .models import InventoryReviewPolicy, InfrastructureRegistration
        from .inventory_review import mandatory_review_mail, reminder_recipients, queue_review_reminders

        self.admin.email = "merge-review@example.invalid"
        self.admin.save()
        Membership.objects.filter(organization=self.target, user=self.admin).update(role="admin")
        InfrastructureRegistration.objects.create(
            user=self.admin,
            organization=self.source,
            company_name=self.source.name,
            contact_name="Review owner",
            email=self.admin.email,
            status="approved",
            email_verified_at=timezone.now(),
            periodic_review_consented_at=timezone.now(),
            verification_expires=timezone.now() + timedelta(days=1),
        )
        original = InventoryReviewPolicy.objects.create(
            organization=self.source,
            interval_days=37,
            reminder_days=4,
            email_enabled=True,
            last_reviewed_at=timezone.now(),
        )
        merge(self.platform, plan(self.platform, self.source, self.target)["ticket"])
        policy = self.target.inventory_review_policy
        self.assertEqual(policy.interval_days, 37)
        self.assertEqual(policy.reminder_days, 4)
        self.assertTrue(policy.email_enabled)
        self.assertIsNone(policy.last_reviewed_at)
        self.assertTrue(mandatory_review_mail(self.target))
        self.assertIn(self.admin.email, reminder_recipients(policy))
        self.assertEqual(queue_review_reminders(original.pk), 0)
        self.assertFalse(reminder_recipients(original))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock validation")
class MergeBusySourceTests(TransactionTestCase):
    def test_busy_inventory_refuses_merge_without_waiting_or_partial_changes(self):
        actor = get_user_model().objects.create_superuser(username="merge-lock-actor", password="synthetic")
        source = Organization.objects.create(name="Lock source", slug="merge-lock-source")
        target = Organization.objects.create(name="Lock target", slug="merge-lock-target")
        inventory = InventorySource.objects.create(organization=source, mode="manual")
        InventorySource.objects.create(organization=target, mode="manual")
        Membership.objects.create(organization=source, user=actor, role="admin")
        ticket = plan(actor, source, target)["ticket"]
        acquired, release = threading.Event(), threading.Event()

        def hold():
            from django.db import transaction

            close_old_connections()
            try:
                with transaction.atomic():
                    InventorySource.objects.select_for_update().get(pk=inventory.pk)
                    acquired.set()
                    release.wait(5)
            finally:
                close_old_connections()

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        try:
            self.assertTrue(acquired.wait(3))
            with self.assertRaisesMessage(ValidationError, "currently changing"):
                merge(actor, ticket)
            source.refresh_from_db()
            self.assertIsNone(source.merged_into_id)
            self.assertTrue(source.membership_set.exists())
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
