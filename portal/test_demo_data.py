"""Synthetic ownership, safe cleanup, preview consistency and durable removal."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Event
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections, transaction, IntegrityError
from django.test import TransactionTestCase

from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from . import demo_data, issues, tests
from .demo_showcase import seed
from .models import (
    Asset,
    AssetIssue,
    AuditEvent,
    Contact,
    DemoDataset,
    DemoObject,
    FlowIntelCase,
    Organization,
    PlumSnapshot,
    RTTicket,
)


@override_settings(DEBUG=True)
class DemoDataTests(tests.Fixture):
    def seed(self):
        with patch(
            "portal.connectors.http.request_json", side_effect=AssertionError("No network in synthetic seed")
        ):
            dataset, created = seed(self.platform, companies=2, assets_per_company=6)
        return dataset, created

    def remove(self, dataset):
        plan, _ = demo_data.removal_plan(dataset)
        self.assertEqual(plan["blockers"], [])
        return demo_data.purge(self.platform, dataset.key, plan["fingerprint"])

    def test_rich_offline_dataset_and_repeat_preserve_review_decisions(self):
        dataset, created = self.seed()
        self.assertTrue(created)
        self.assertEqual(Organization.objects.filter(slug__startswith="demo-explore-").count(), 2)
        self.assertEqual(PlumSnapshot.objects.count(), 36)
        self.assertEqual(AssetIssue.objects.filter(kind="exposure").count(), 12)
        self.assertTrue(RTTicket.objects.filter(role="incident", instance__enabled=False).exists())
        self.assertTrue(FlowIntelCase.objects.filter(instance__enabled=False).exists())
        issue = AssetIssue.objects.filter(source_label="SYNTHETIC contract and lifecycle evidence").first()
        issue.status = "accepted_risk"
        issue.save(update_fields=["status"])
        count = dataset.entries.count()
        again, created = self.seed()
        self.assertFalse(created)
        self.assertEqual(count, again.entries.count())
        issue.refresh_from_db()
        self.assertEqual(issue.status, "accepted_risk")
        self.assertTrue(
            any(
                ".example.invalid" in asset.upstream_data.get("primary_ip4_dns_name", "")
                for asset in Asset.objects.filter(organization__slug__startswith="demo-explore-")
            )
        )

    def test_purge_preserves_real_data_users_and_audit_then_blocks_automatic_reseed(self):
        dataset, _ = self.seed()
        password = self.platform.password
        # Even a misleading name is never adopted as synthetic provenance.
        real = Organization.objects.create(
            name="SYNTHETIC looking actual organization", slug="real-preserved"
        )
        self.remove(dataset)
        self.assertTrue(Organization.objects.filter(pk=real.pk).exists())
        self.assertTrue(Asset.objects.filter(pk=self.asset.pk).exists())
        self.platform.refresh_from_db()
        self.assertEqual(self.platform.password, password)
        self.assertEqual(DemoObject.objects.count(), 0)
        self.assertTrue(AuditEvent.objects.filter(action="demo.purged", organization=None).exists())
        dataset, created = self.seed()
        self.assertFalse(created)
        self.assertEqual(dataset.state, "removed")
        self.assertFalse(Organization.objects.filter(slug__startswith="demo-explore-").exists())

    def test_unowned_real_dependents_block_atomic_cleanup(self):
        dataset, _ = self.seed()
        org = Organization.objects.get(slug="demo-explore-01")
        contact = Contact.objects.create(
            organization=org, name="Actual stakeholder", email="actual@example.invalid"
        )
        plan, _ = demo_data.removal_plan(dataset)
        self.assertTrue(any("Contact" in row for row in plan["blockers"]))
        with self.assertRaises(ValidationError):
            demo_data.purge(self.platform, dataset.key, plan["fingerprint"])
        self.assertTrue(Contact.objects.filter(pk=contact.pk).exists())
        self.assertTrue(Organization.objects.filter(pk=org.pk).exists())
        dataset.refresh_from_db()
        self.assertEqual(dataset.state, "active")

    def test_demo_review_history_is_removable_and_changed_preview_is_rejected(self):
        dataset, _ = self.seed()
        old, _ = demo_data.removal_plan(dataset)
        issue = AssetIssue.objects.filter(kind="support").first()
        issues.save_issue(
            self.platform, issue, {"status": "under_review"}, "Synthetic review during exploration"
        )
        with self.assertRaises(ValidationError):
            demo_data.purge(self.platform, dataset.key, old["fingerprint"])
        self.remove(dataset)
        self.assertFalse(AssetIssue.objects.filter(pk=issue.pk).exists())

    def test_exported_backend_identity_requires_separate_review(self):
        dataset, _ = self.seed()
        row = RTTicket.objects.filter(role="incident").first()
        row.remote_id = 123
        row.save(update_fields=["remote_id"])
        plan, _ = demo_data.removal_plan(dataset)
        self.assertTrue(any("exported backend" in row for row in plan["blockers"]))
        with self.assertRaises(ValidationError):
            demo_data.purge(self.platform, dataset.key, plan["fingerprint"])

    def test_only_platform_admin_can_preview_or_purge(self):
        dataset, _ = self.seed()
        self.login(self.analyst)
        self.assertEqual(self.client.get(reverse("demo-data")).status_code, 403)
        with self.assertRaises(PermissionDenied):
            demo_data.purge(self.analyst, dataset.key, "invalid")
        self.login(self.platform)
        self.assertContains(self.client.get(reverse("demo-data")), "Remove tracked synthetic data")
        plan, _ = demo_data.removal_plan(dataset)
        response = self.client.post(
            reverse("demo-data"),
            {"confirmation": "REMOVE SYNTHETIC DATA", "fingerprint": plan["fingerprint"]},
        )
        self.assertEqual(response.status_code, 302)
        dataset.refresh_from_db()
        self.assertEqual(dataset.state, "removed")

    def test_seeding_requires_debug_but_preproduction_cleanup_does_not(self):
        dataset, _ = self.seed()
        with override_settings(DEBUG=False):
            with self.assertRaises(ValidationError):
                seed(self.platform)
            self.remove(dataset)

    def test_conflicting_slug_rolls_back_and_explicit_restore_is_available(self):
        conflict = Organization.objects.create(slug="demo-explore-01", name="Real organization — preserved")
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.seed()
        self.assertFalse(DemoDataset.objects.exists())
        self.assertEqual(Organization.objects.get(pk=conflict.pk).name, "Real organization — preserved")
        conflict.delete()
        dataset, _ = self.seed()
        self.remove(dataset)
        dataset, created = seed(self.platform, companies=1, assets_per_company=2, restore=True)
        self.assertTrue(created)
        self.assertEqual(dataset.state, "active")

    def test_promoted_connector_and_real_source_grant_block_cleanup(self):
        dataset, _ = self.seed()
        from .models import RTInstance, PlumInstance

        rt = RTInstance.objects.get(name="SYNTHETIC offline RTIR previews")
        rt.enabled = True
        rt.save(update_fields=["enabled"])
        plan, _ = demo_data.removal_plan(dataset)
        self.assertTrue(any("enabled live connector" in row for row in plan["blockers"]))
        rt.enabled = False
        rt.save(update_fields=["enabled"])
        source = PlumInstance.objects.get(name="SYNTHETIC exploration exposure history")
        source.organizations.add(self.a)
        plan, _ = demo_data.removal_plan(dataset)
        self.assertTrue(any("unowned M2M endpoints" in row for row in plan["blockers"]))
        with self.assertRaises(ValidationError):
            demo_data.purge(self.platform, dataset.key, plan["fingerprint"])
        self.assertTrue(source.organizations.filter(pk=self.a.pk).exists())

    def test_default_scale_can_be_removed_without_touching_real_inventory(self):
        with patch("portal.connectors.http.request_json", side_effect=AssertionError("No seed network")):
            dataset, _ = seed(self.platform)
        self.assertEqual(Asset.objects.filter(organization__slug__startswith="demo-explore-").count(), 300)
        self.assertEqual(
            AssetIssue.objects.filter(organization__slug__startswith="demo-explore-").count(), 960
        )
        self.assertEqual(PlumSnapshot.objects.count(), 180)
        self.remove(dataset)
        self.assertTrue(Asset.objects.filter(pk=self.asset.pk).exists())
        self.assertEqual(DemoObject.objects.count(), 0)

    def test_exploration_scopes_companies_and_command_check_reports_legacy(self):
        dataset, _ = seed(self.platform, companies=5, assets_per_company=2)
        self.login(self.analyst)
        response = self.client.get(reverse("demo-explore"))
        self.assertContains(response, "Aster Finance (SYNTHETIC)")
        self.assertContains(response, "Rendered message examples")
        self.assertContains(response, "SYNTHETIC PREVIEW ONLY")
        self.assertNotContains(response, "Ember Manufacturing (SYNTHETIC)")
        from django.core.management import call_command, CommandError
        from io import StringIO

        with self.assertRaises(CommandError):
            call_command("demo_data", "check", stdout=StringIO())
        self.remove(dataset)
        # An unrelated old fixture is reported but never deleted by its label.
        old = Organization.objects.create(name="Legacy fixture review needed", slug="example-labs")
        self.assertEqual(demo_data.unmanaged_fixtures()["legacy_organizations"], 1)
        self.assertTrue(Organization.objects.filter(pk=old.pk).exists())

    def test_changed_recipient_and_live_address_are_not_silently_deleted(self):
        dataset, _ = self.seed()
        contact = Contact.objects.filter(organization__slug="demo-explore-01").first()
        contact.email = "stakeholder@actual.example.com"
        contact.save(update_fields=["email"])
        asset = Asset.objects.filter(organization__slug="demo-explore-01").first()
        asset.upstream_data["primary_ip4"] = "8.8.8.8/32"
        asset.save(update_fields=["upstream_data"])
        plan, _ = demo_data.removal_plan(dataset)
        self.assertTrue(any("non-synthetic recipient" in row for row in plan["blockers"]))
        self.assertTrue(any("non-documentation address" in row for row in plan["blockers"]))
        with self.assertRaises(ValidationError):
            demo_data.purge(self.platform, dataset.key, plan["fingerprint"])
        self.assertTrue(Contact.objects.filter(pk=contact.pk).exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL FK row locking")
@override_settings(DEBUG=True)
class DemoCleanupConcurrencyTests(TransactionTestCase):
    def test_concurrent_real_reference_cannot_slip_into_a_purge(self):
        actor = get_user_model().objects.create_superuser(
            "demo-operator", "operator@example.invalid", "local-test-only"
        )
        dataset, _ = seed(actor, companies=1, assets_per_company=2)
        organization = Organization.objects.get(slug="demo-explore-01")
        plan, _ = demo_data.removal_plan(dataset)
        locked, release, writer_started = Event(), Event(), Event()
        original = demo_data.removal_plan

        def locked_plan(dataset, **kwargs):
            result = original(dataset, **kwargs)
            if kwargs.get("lock"):
                locked.set()
                if not release.wait(10):
                    raise AssertionError("Timed out waiting for test writer")
            return result

        def cleanup():
            close_old_connections()
            try:
                return demo_data.purge(actor, dataset.key, plan["fingerprint"])
            finally:
                connections.close_all()

        def write_real_reference():
            close_old_connections()
            writer_started.set()
            try:
                with transaction.atomic():
                    Contact.objects.create(
                        organization_id=organization.pk,
                        name="Concurrent real contact",
                        email="actual@example.invalid",
                    )
            except IntegrityError:
                return "rejected"
            finally:
                connections.close_all()
            return "inserted"

        with (
            patch("portal.demo_data.removal_plan", side_effect=locked_plan),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            remove = pool.submit(cleanup)
            self.assertTrue(locked.wait(10))
            writer = pool.submit(write_real_reference)
            self.assertTrue(writer_started.wait(10))
            try:
                with self.assertRaises(FutureTimeout):
                    writer.result(timeout=0.2)
            finally:
                release.set()
            remove.result(timeout=10)
            self.assertEqual(writer.result(timeout=10), "rejected")
        self.assertFalse(Contact.objects.filter(name="Concurrent real contact").exists())
