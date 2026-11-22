"""Independent client/host/export status must remain visible without changing write policy."""

from datetime import timedelta
from unittest.mock import patch
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import AgentDevice, Asset, NetBoxInstance
from .inventory_status import synchronization_status


class InventoryStatusTests(Fixture):
    def setUp(self):
        self.instance = NetBoxInstance.objects.create(
            name="Synthetic status",
            organization=self.a,
            base_url="https://netbox.example.invalid",
            token_env_var="NETBOX_TEST_TOKEN",
            access_mode="read_write",
        )
        self.sa.mode, self.sa.instance, self.sa.tenant_id = "external", self.instance, 42
        self.sa.agent_managed = True
        self.sa.save()
        self.asset.external_id, self.asset.state = "9", "synced"
        self.asset.save()
        self.device = AgentDevice.objects.create(
            asset=self.asset,
            source=self.sa,
            organization=self.a,
            public_key="synthetic-ui-key",
            expires_at=timezone.now() + timedelta(days=1),
            last_observed_at=timezone.now(),
            applied_sequence=2,
        )

    def status(self):
        self.asset = Asset.objects.select_related("source__instance").get(pk=self.asset.pk)
        return synchronization_status(self.asset, self.device)

    def test_disabled_export_is_visible_even_while_host_and_reports_are_healthy(self):
        self.login(self.reader)
        with patch("portal.connectors.netbox.request_json") as api:
            response = self.client.get(self.url("asset", pk=self.asset.pk))
            api.assert_not_called()
        self.assertContains(response, "Inventory synchronization")
        self.assertContains(response, "Reports received")
        self.assertContains(response, "Host linked")
        self.assertContains(response, "Not activated")
        self.sa.refresh_from_db()
        self.assertFalse(self.sa.agent_export_policy)
        self.assertContains(response, "More asset actions")
        self.assertNotContains(response, "Record lifecycle issue")
        self.assertEqual(
            self.client.get(reverse("asset", args=[self.a.slug, self.other.pk])).status_code, 404
        )

    def test_readonly_disabled_and_revoked_states_do_not_claim_success(self):
        self.instance.access_mode = "read_only"
        self.instance.save()
        self.assertEqual(self.status()["export"]["label"], "Read-only connection")
        self.instance.enabled = False
        self.instance.save()
        self.assertEqual(self.status()["export"]["label"], "Connection disabled")
        self.device.enabled = False
        self.assertEqual(self.status()["client"]["label"], "Client inactive")

    def test_current_historical_pending_failed_and_inventory_only_receipts_are_distinct(self):
        self.sa.agent_export_policy = {"inventory": True, "vrf": 7}
        self.sa.save()
        self.device.netbox_export_receipt = {"sequence": 2, "network": "exported"}
        self.assertEqual(self.status()["export"]["label"], "Export confirmed")
        self.device.netbox_export_pending = True
        self.assertEqual(self.status()["export"]["label"], "Export queued")
        self.device.netbox_export_error = "Synthetic failure"
        self.assertEqual(self.status()["export"]["label"], "Export needs attention")
        self.device.netbox_export_pending = False
        self.device.netbox_export_error = ""
        self.device.netbox_export_receipt["network"] = "not_exported"
        self.assertEqual(self.status()["export"]["label"], "Software exported; network pending")
        self.sa.agent_export_policy["vrf"] = None
        self.sa.save()
        self.assertEqual(self.status()["export"]["label"], "Software inventory exported")
        self.device.netbox_export_receipt["sequence"] = 1
        self.assertEqual(self.status()["export"]["label"], "No confirmed export")

    def test_status_projection_has_no_queries_and_does_not_expose_a_mismatched_device_receipt(self):
        self.asset = Asset.objects.select_related("source__instance").get(pk=self.asset.pk)
        with CaptureQueriesContext(connection) as queries:
            synchronization_status(self.asset, self.device)
        self.assertEqual(len(queries), 0)
        self.device.source_id = self.sb.pk
        self.device.netbox_export_receipt = {"sequence": 2, "software": 12345}
        result = synchronization_status(self.asset, self.device)
        self.assertEqual(result["client"]["label"], "Client binding needs review")
        self.assertEqual(result["receipt"], {})

    def test_agent_routes_use_clients_navigation_and_optional_groups_open_for_active_destination(self):
        self.login(self.reader)
        response = self.client.get(reverse("agent-center", args=[self.a.slug]))
        self.assertEqual(response.context["workspace_area"], "clients")
        self.assertEqual(response.context["workflow_stage"], "inventory")
        groups = response.context["navigation_groups"]
        inventory = next(g for g in groups if g["label"] == "Inventory")
        clients = next(item for item in inventory["items"] if item["key"] == "clients")
        self.assertTrue(clients["active"])
        self.assertEqual(clients["url"], reverse("linux-client-downloads") + "?organization=" + self.a.slug)
        self.assertNotIn("Administration", [g["label"] for g in groups])
        self.assertEqual(
            [g["label"] for g in groups if not g["collapsible"]],
            ["Overview", "Inventory", "Security", "Response"],
        )
        self.assertNotContains(response, 'href="' + reverse("demo-explore") + '"')
        response = self.client.get(reverse("misp-connections"))
        group = next(g for g in response.context["navigation_groups"] if g["label"] == "My integrations")
        self.assertTrue(group["active"])
        self.assertContains(response, 'class="nav-group nav-disclosure" open')
