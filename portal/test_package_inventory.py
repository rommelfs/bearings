"""Automatic exact package identities and separate installations; no name-based takeover."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from .tests import Fixture
from . import test_agents as legacy
from . import agents, package_inventory
from .models import AgentComponent, AgentDevice, AgentReport, Installation, ProductWatch


class AutomaticPackageTests(Fixture):
    legacy_manual_projection = False
    setUp = legacy.AgentTests.setUp
    post = legacy.AgentTests.post
    enroll = legacy.AgentTests.enroll
    data = legacy.AgentTests.data
    send = legacy.AgentTests.send
    relax = legacy.AgentTests.relax

    def test_default_inventory_updates_without_clicks_preserves_manual_and_other_company(self):
        self.enroll()
        self.assertTrue(self.device.auto_software)
        self.send()
        agents.process_pending()
        c = AgentComponent.objects.get()
        self.assertTrue(c.automatic_installation)
        self.assertEqual(c.installation.product.identifier, "pkg:deb/ubuntu/nginx?arch=amd64")
        self.assertEqual(
            c.package_identity["purl"],
            "pkg:deb/ubuntu/nginx@1:1.24.0-2ubuntu7.5?arch=amd64&distro=ubuntu-24.04",
        )
        original = c.installation_id
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "")
        self.assertFalse(Installation.objects.filter(asset=self.other).exists())
        self.assertFalse(ProductWatch.objects.exists())
        self.relax()
        self.send(self.data(sequence=2, version="1:1.24.0-2ubuntu7.6"))
        agents.process_pending()
        c.refresh_from_db()
        self.assertEqual(c.installation_id, original)
        self.assertEqual(c.installation.version, "1:1.24.0-2ubuntu7.6")
        self.assertEqual(Installation.objects.filter(asset=self.asset).count(), 2)
        self.login()
        response = self.client.get(f"/organizations/alpha/agents/?device={self.device.pk}")
        self.assertContains(response, "Automatically inventoried")
        self.assertContains(response, "Open installed software")

    def test_backfill_already_applied_report_idempotent_and_uses_original_os(self):
        self.enroll()
        AgentDevice.objects.filter(pk=self.device.pk).update(auto_software=False)
        self.send()
        agents.process_pending()
        self.assertIsNone(AgentComponent.objects.get().installation_id)
        # Model upgrade/backfill queues prior processed facts without resending a report.
        AgentDevice.objects.filter(pk=self.device.pk).update(
            auto_software=True, software_sync_pending=True, os={"id": "debian", "version": "13"}
        )
        agents.process_pending()
        c = AgentComponent.objects.get()
        self.assertEqual(c.package_identity["distribution"], "ubuntu")
        self.assertEqual(c.installation.product.identifier, "pkg:deb/ubuntu/nginx?arch=amd64")
        agents.process_pending()
        self.assertEqual(Installation.objects.filter(asset=self.asset).count(), 2)

    def test_missing_partial_and_release_preserve_records_without_rebinding(self):
        self.enroll()
        self.send()
        agents.process_pending()
        old = AgentComponent.objects.get()
        old_install = old.installation_id
        agents.detach(self.admin, self.a, old.pk)
        self.relax()
        self.send(self.data(sequence=2))
        agents.process_pending()
        old.refresh_from_db()
        self.assertIsNone(old.installation_id)
        self.assertTrue(old.inventory_excluded)
        self.assertTrue(Installation.objects.filter(pk=old_install).exists())
        self.relax()
        data = self.data(sequence=3)
        data["components"][0].update(key="dpkg:curl:amd64", name="curl")
        data["complete"] = False
        data["scope"] = "selected-packages"
        self.send(data)
        agents.process_pending()
        old.refresh_from_db()
        self.assertIsNone(old.missing_since)
        self.relax()
        data["report_id"] = str(uuid.uuid4())
        data["sequence"] = 4
        data["complete"] = True
        data["scope"] = "system-packages"
        self.send(data)
        agents.process_pending()
        old.refresh_from_db()
        self.assertIsNotNone(old.missing_since)
        self.assertTrue(Installation.objects.filter(pk=old_install).exists())

    def test_native_rpm_evr_and_installonly_kernels_have_distinct_slots(self):
        self.enroll()
        data = self.data()
        data["os"].update(id="rhel", version="9.5")
        data["components"] = [
            {
                "key": "rpm:kernel:x86_64@" + v,
                "manager": "rpm",
                "name": "kernel",
                "version": v,
                "architecture": "x86_64",
            }
            for v in ["0:5.14.0-503.el9", "0:5.14.0-504.el9"]
        ]
        self.assertEqual(self.send(data).status_code, 202)
        agents.process_pending()
        rows = list(AgentComponent.objects.select_related("installation__product").order_by("version"))
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0].installation_id, rows[1].installation_id)
        self.assertEqual(rows[0].installation.product_id, rows[1].installation.product_id)
        self.assertEqual(rows[0].installation.product.identifier, "pkg:rpm/redhat/kernel?arch=x86_64")
        self.assertIn("epoch=0", rows[0].package_identity["purl"])
        self.assertIn("distro=rhel-9.5", rows[0].package_identity["purl"])
        self.assertEqual(rows[0].installation.version, "0:5.14.0-503.el9")

    def test_1000_new_packages_are_batched_and_retries_do_not_duplicate(self):
        self.enroll()
        data = self.data()
        data["components"] = [
            {
                "key": f"dpkg:test-{i}:amd64",
                "manager": "dpkg",
                "name": f"test-{i}",
                "version": "1.0",
                "architecture": "amd64",
            }
            for i in range(1000)
        ]
        self.send(data)
        with CaptureQueriesContext(connection) as queries:
            agents.process_pending()
        self.assertLess(len(queries), 60)
        self.assertEqual(Installation.objects.filter(asset=self.asset).count(), 1001)
        agents.process_pending()
        self.assertEqual(Installation.objects.filter(asset=self.asset).count(), 1001)

    def test_disabled_expired_and_stale_devices_do_not_backfill(self):
        self.enroll()
        AgentDevice.objects.filter(pk=self.device.pk).update(auto_software=False)
        self.send()
        agents.process_pending()
        for changes in (
            {"enabled": False},
            {"expires_at": timezone.now() - timedelta(seconds=1)},
            {"last_observed_at": timezone.now() - timedelta(days=1)},
        ):
            AgentDevice.objects.filter(pk=self.device.pk).update(
                auto_software=True, software_sync_pending=True, **changes
            )
            agents.process_pending()
            self.assertIsNone(AgentComponent.objects.get().installation_id)
            AgentDevice.objects.filter(pk=self.device.pk).update(
                enabled=True, expires_at=timezone.now() + timedelta(days=1), last_observed_at=timezone.now()
            )

    def test_policy_is_scoped_csrf_protected_and_works_for_current_device(self):
        self.enroll()
        path = "/organizations/alpha/agents/"
        self.login(self.reader)
        self.assertEqual(
            self.client.post(path, {"action": "software-policy", "device": str(self.device.pk)}).status_code,
            403,
        )
        self.login()
        self.assertEqual(
            self.client.post(path, {"action": "software-policy", "device": str(self.device.pk)}).status_code,
            302,
        )
        self.device.refresh_from_db()
        self.assertFalse(self.device.auto_software)
        self.machine.force_login(self.admin)
        self.assertEqual(
            self.machine.post(
                path, {"action": "software-policy", "device": str(self.device.pk), "enabled": "on"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/organizations/beta/agents/",
                {"action": "software-policy", "device": str(self.device.pk), "enabled": "on"},
            ).status_code,
            404,
        )

    def test_package_identity_quoting_debian_case_and_rpm_case(self):
        c = SimpleNamespace(manager="dpkg", name="libFoo++", architecture="arm64", version="2:1.0+deb12u1")
        d = package_inventory.identity(c, {"id": "debian", "version": "12"})
        self.assertEqual(d["product"], "pkg:deb/debian/libfoo%2B%2B?arch=arm64")
        self.assertIn("@2:1.0%2Bdeb12u1", d["purl"])
        c.manager = "rpm"
        c.version = "1:2.0-3.el9"
        c.name = "NetworkManager"
        self.assertIn(
            "/NetworkManager?", package_inventory.identity(c, {"id": "rhel", "version": "9"})["product"]
        )
        self.assertEqual(package_inventory.identity(c, {"id": "unknown", "version": "unknown"}), {})

    def test_large_installed_software_views_are_paged_and_searchable(self):
        self.enroll()
        data = self.data()
        data["components"] = [
            {
                "key": f"dpkg:package-{i:04d}:amd64",
                "manager": "dpkg",
                "name": f"package-{i:04d}",
                "version": "1.0",
                "architecture": "amd64",
            }
            for i in range(150)
        ]
        self.send(data)
        agents.process_pending()
        self.login()
        # Resolve the route rather than depending on its spelling.
        from django.urls import reverse

        path = reverse("asset", args=[self.a.slug, self.asset.pk])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["software_page"]), 100)
        self.assertLess(len(queries), 25)
        self.assertContains(response, f"?device={self.device.pk}")
        response = self.client.get(path, {"software_q": "package-0149"})
        self.assertEqual(response.context["software_page"].paginator.count, 1)
        self.assertContains(response, "package-0149")
        company = self.client.get(reverse("organization", args=[self.a.slug]))
        asset = next(a for a in company.context["inventory_page"] if a.pk == self.asset.pk)
        self.assertEqual(len(asset.software_preview), 10)
        self.assertEqual(asset.software_count, 151)

    def test_source_identity_changes_do_not_retarget_bound_packages(self):
        self.enroll()
        self.send()
        agents.process_pending()
        original = AgentComponent.objects.get().installation
        self.relax()
        data = self.data(sequence=2, version="1.9-new")
        data["os"]["id"] = "debian"
        self.send(data)
        agents.process_pending()
        self.assertEqual(AgentReport.objects.order_by("-sequence").first().status, "rejected")
        original.refresh_from_db()
        self.assertEqual(original.version, "1:1.24.0-2ubuntu7.5")

    def test_distro_packages_never_guess_upstream_watch_from_display_name(self):
        from .product_matching import enroll_products

        self.product.name = "Log4j"
        self.product.identifier = "pkg:deb/ubuntu/log4j?arch=all"
        self.product.save()
        self.assertEqual(enroll_products(), 0)
        self.assertFalse(ProductWatch.objects.exists())

    def test_backfill_continues_in_bounded_batches(self):
        from unittest.mock import patch

        self.enroll()
        AgentDevice.objects.filter(pk=self.device.pk).update(auto_software=False)
        data = self.data()
        data["components"] = [
            {
                "key": f"dpkg:batch-{i}:amd64",
                "manager": "dpkg",
                "name": f"batch-{i}",
                "version": "1.0",
                "architecture": "amd64",
            }
            for i in range(5)
        ]
        self.send(data)
        agents.process_pending()
        AgentDevice.objects.filter(pk=self.device.pk).update(auto_software=True, software_sync_pending=True)
        with patch("portal.package_inventory.MAX_AUTO_PACKAGES", 2):
            for expected in [2, 4, 5]:
                agents.process_pending()
                self.assertEqual(AgentComponent.objects.filter(installation__isnull=False).count(), expected)
                self.device.refresh_from_db()
                self.assertEqual(self.device.software_sync_pending, expected < 5)

    def test_unknown_distribution_is_not_fabricated_and_new_report_can_resolve_it(self):
        self.enroll()
        data = self.data()
        data["os"]["id"] = "unknown"
        self.send(data)
        agents.process_pending()
        c = AgentComponent.objects.get()
        self.assertIsNone(c.installation_id)
        self.assertTrue(c.package_identity["unsupported"])
        self.device.refresh_from_db()
        self.assertFalse(self.device.software_sync_pending)
        self.relax()
        self.send(self.data(sequence=2))
        agents.process_pending()
        c.refresh_from_db()
        self.assertTrue(c.automatic_installation)

    def test_upgrade_respects_historical_release_in_its_own_company(self):
        import importlib
        from django.apps import apps
        from .models import AuditEvent

        self.enroll()
        AgentDevice.objects.filter(pk=self.device.pk).update(auto_software=False)
        self.send()
        agents.process_pending()
        component = AgentComponent.objects.get()
        AuditEvent.objects.create(
            organization=self.b, action="agent.software_detached", target=str(component.pk)
        )
        migration = importlib.import_module("portal.migrations.0059_automatic_package_inventory")
        migration.preserve_released_slots(apps, SimpleNamespace(connection=connection))
        component.refresh_from_db()
        self.assertFalse(component.inventory_excluded)
        AuditEvent.objects.create(
            organization=self.a, action="agent.software_detached", target=str(component.pk)
        )
        migration.preserve_released_slots(apps, SimpleNamespace(connection=connection))
        component.refresh_from_db()
        self.assertTrue(component.inventory_excluded)
        AgentDevice.objects.filter(pk=self.device.pk).update(auto_software=True, software_sync_pending=True)
        agents.process_pending()
        component.refresh_from_db()
        self.assertIsNone(component.installation_id)
