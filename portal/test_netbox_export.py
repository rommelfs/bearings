"""Customer-specific managed export, conflicts, provenance, retries and revocation."""

import io
import json
import uuid
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.utils import timezone
from .tests import Fixture
from .models import AgentDevice, AgentReport, AgentComponent, NetBoxInstance
from . import netbox_export as exports
from .connectors.http import ConnectorError


class ExportTests(Fixture):
    def setUp(self):
        self.nb = NetBoxInstance.objects.create(
            name="Synthetic customer NetBox",
            base_url="https://netbox.example.invalid",
            organization=self.a,
            token_env_var="NETBOX_TEST_TOKEN",
            access_mode="read_write",
        )
        self.sa.instance = self.nb
        self.sa.mode = "external"
        self.sa.tenant_id = 42
        self.sa.agent_managed = True
        self.sa.agent_export_policy = {"inventory": True, "vrf": 7}
        self.sa.save()
        self.asset.kind = "vm"
        self.asset.object_type = "virtualization.virtualmachine"
        self.asset.external_id = "9"
        self.asset.state = "synced"
        self.asset.save()
        now = timezone.now()
        self.device = AgentDevice.objects.create(
            organization=self.a,
            asset=self.asset,
            source=self.sa,
            public_key="synthetic-export-key",
            expires_at=now + timedelta(days=1),
            last_observed_at=now,
            network_observed_at=now,
            applied_sequence=1,
            netbox_export_pending=True,
            reported_network={
                "hostname": "synthetic.example.invalid",
                "addresses": [{"interface": "eth0", "address": "10.20.30.40/24"}],
            },
            os={"id": "ubuntu", "version": "24.04"},
        )
        report = AgentReport.objects.create(
            id=uuid.uuid4(),
            device=self.device,
            sequence=1,
            observed_at=now,
            body=b"{}",
            body_hash="a" * 64,
            component_count=1,
            status="applied",
        )
        AgentComponent.objects.create(
            device=self.device,
            key="dpkg:nginx:amd64",
            manager="dpkg",
            name="nginx",
            architecture="amd64",
            version="1.24.0-2ubuntu7.21",
            observed_at=now,
            last_report=report,
        )
        self.host = {"id": 9, "tenant": {"id": 42}, "custom_fields": {"bearings_id": str(self.asset.pk)}}
        self.interfaces = []
        self.addresses = []
        self.calls = []

    def api(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/vrfs/7/"):
            return {"id": 7, "tenant": {"id": 42}, "enforce_unique": True}
        if url.endswith("/virtual-machines/9/"):
            if method == "PATCH":
                self.host["custom_fields"].update(kwargs["json"]["custom_fields"])
            return deepcopy(self.host)
        rows = self.interfaces if "/interfaces/" in url else self.addresses
        if method == "GET":
            return {"count": len(rows), "results": deepcopy(rows), "next": None}
        if method == "POST":
            row = {"id": 123, **kwargs["json"]}
            if "tenant" in row:
                row["tenant"] = {"id": row["tenant"]}
            rows.append(row)
            return deepcopy(row)
        raise AssertionError("Unexpected call")

    def run_export(self):
        with (
            patch("portal.netbox_export.connection", return_value=(self.nb, self.nb.base_url, {})),
            patch("portal.netbox_export.request_json", side_effect=self.api),
        ):
            exports.process(self.device.pk)
        self.device.refresh_from_db()

    def test_native_network_and_full_software_snapshot_are_idempotent_and_preserve_other_fields(self):
        self.host["custom_fields"]["operator_owned"] = "preserve"
        self.run_export()
        self.assertFalse(self.device.netbox_export_pending, self.device.netbox_export_error)
        self.assertEqual(self.device.netbox_export_receipt["addresses"], 1)
        inventory = self.host["custom_fields"]["bearings_inventory"]
        self.assertEqual(inventory["software"][0]["version"], "1.24.0-2ubuntu7.21")
        self.assertEqual(inventory["device_id"], str(self.device.pk))
        self.assertEqual(self.host["custom_fields"]["operator_owned"], "preserve")
        self.device.netbox_export_pending = True
        self.device.save()
        self.run_export()
        self.assertEqual((len(self.interfaces), len(self.addresses)), (1, 1))
        self.assertEqual(sum(c[0] == "POST" for c in self.calls), 2)
        self.assertFalse(any(c[0] == "DELETE" for c in self.calls))

    def test_existing_unowned_interface_is_not_adopted_and_failure_is_visible(self):
        self.interfaces.append({"id": 44, "name": "eth0", "virtual_machine": 9, "custom_fields": {}})
        self.run_export()
        self.assertTrue(self.device.netbox_export_pending)
        self.assertTrue(self.device.netbox_export_error)
        self.assertFalse(self.addresses)
        self.assertFalse(any(c[0] in {"PATCH", "POST", "DELETE"} for c in self.calls))

    def test_foreign_or_reassigned_ip_is_not_overwritten(self):
        self.addresses.append(
            {
                "id": 55,
                "address": "10.20.30.40/24",
                "vrf": 7,
                "tenant": 43,
                "custom_fields": {"bearings_id": exports.marker(self.asset, "address:eth0:10.20.30.40")},
                "assigned_object_id": 999,
                "assigned_object_type": "virtualization.vminterface",
            }
        )
        self.run_export()
        self.assertTrue(self.device.netbox_export_error)
        self.assertFalse(any(c[0] == "PATCH" for c in self.calls))

    def test_revoked_readonly_or_disabled_policy_prevents_writes(self):
        for changed in ("revoked", "readonly", "disabled"):
            with self.subTest(changed=changed):
                self.device.netbox_export_after = timezone.now()
                self.device.enabled = changed != "revoked"
                self.device.save()
                self.sa.agent_export_policy = {} if changed == "disabled" else {"inventory": True, "vrf": 7}
                self.sa.save()
                self.nb.access_mode = "read_only" if changed == "readonly" else "read_write"
                self.nb.save()
                with (
                    patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic-only"}),
                    patch("portal.connectors.netbox.approved_base", return_value=self.nb.base_url),
                    patch("portal.netbox_export.request_json") as api,
                ):
                    exports.process(self.device.pk)
                    api.assert_not_called()
                self.device.refresh_from_db()
                self.assertTrue(self.device.netbox_export_pending)

    def test_inventory_only_and_stale_network_do_not_allocate_ips(self):
        self.sa.agent_export_policy = {"inventory": True, "vrf": None}
        self.sa.save()
        self.run_export()
        self.assertFalse(self.interfaces)
        self.assertFalse(self.addresses)
        self.assertEqual(self.device.netbox_export_receipt["network"], "not_exported")
        self.assertEqual(self.device.netbox_export_receipt["software"], 1)

    def test_per_customer_configuration_requires_platform_role_and_preserves_binding(self):
        with self.assertRaises(CommandError):
            call_command(
                "configure_netbox_export",
                actor=self.admin.username,
                source=str(self.sa.pk),
                inventory_only=True,
                apply=True,
            )
        out = io.StringIO()
        call_command(
            "configure_netbox_export",
            actor=self.platform.username,
            source=str(self.sa.pk),
            inventory_only=True,
            stdout=out,
        )
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.agent_export_policy["vrf"], 7)
        self.assertFalse(json.loads(out.getvalue())["applied"])
        call_command(
            "configure_netbox_export",
            actor=self.platform.username,
            source=str(self.sa.pk),
            disable=True,
            apply=True,
            stdout=io.StringIO(),
        )
        self.sa.refresh_from_db()
        self.assertFalse(self.sa.agent_export_policy)
        self.assertEqual(self.sa.instance_id, self.nb.pk)
        self.assertEqual(self.sa.tenant_id, 42)

    def test_stale_network_still_exports_software_without_allocating_addresses(self):
        self.device.network_observed_at = timezone.now() - timedelta(days=1)
        self.device.save()
        self.run_export()
        self.assertFalse(self.device.netbox_export_pending)
        self.assertFalse(self.addresses)
        self.assertEqual(self.device.netbox_export_receipt["software"], 1)
        self.assertEqual(self.device.netbox_export_receipt["network"], "not_exported")

    def test_lost_ip_ack_recovers_without_duplicate_or_deletion(self):
        def lost_ack(method, url, **kwargs):
            row = self.api(method, url, **kwargs)
            if method == "POST" and "/ip-addresses/" in url:
                raise ConnectorError("Synthetic lost acknowledgement")
            return row

        with (
            patch("portal.netbox_export.connection", return_value=(self.nb, self.nb.base_url, {})),
            patch("portal.netbox_export.request_json", side_effect=lost_ack),
        ):
            exports.process(self.device.pk)
        self.device.refresh_from_db()
        self.assertTrue(self.device.netbox_export_pending)
        self.assertEqual(len(self.addresses), 1)
        self.device.netbox_export_after = timezone.now()
        self.device.save()
        self.run_export()
        self.assertFalse(self.device.netbox_export_pending)
        self.assertEqual((len(self.interfaces), len(self.addresses)), (1, 1))

    def test_explicit_existing_host_binding_preserves_native_id_and_other_fields(self):
        self.host["custom_fields"] = {"operator_owned": "preserve"}
        with (
            patch(
                "portal.management.commands.configure_netbox_export.connection",
                return_value=(self.nb, self.nb.base_url, {}),
            ),
            patch("portal.management.commands.configure_netbox_export.request_json", side_effect=self.api),
        ):
            call_command(
                "configure_netbox_export",
                actor=self.platform.username,
                source=str(self.sa.pk),
                inventory_only=True,
                bind_asset=str(self.asset.pk),
                apply=True,
                stdout=io.StringIO(),
            )
        self.assertEqual(self.host["custom_fields"]["bearings_id"], str(self.asset.pk))
        self.assertEqual(self.host["custom_fields"]["operator_owned"], "preserve")
        self.assertEqual(self.host["id"], 9)
        self.assertFalse(any(c[0] in {"POST", "DELETE"} for c in self.calls))

    def test_explicit_binding_cannot_replace_another_uuid(self):
        self.host["custom_fields"]["bearings_id"] = str(uuid.uuid4())
        with (
            patch(
                "portal.management.commands.configure_netbox_export.connection",
                return_value=(self.nb, self.nb.base_url, {}),
            ),
            patch("portal.management.commands.configure_netbox_export.request_json", side_effect=self.api),
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "configure_netbox_export",
                    actor=self.platform.username,
                    source=str(self.sa.pk),
                    inventory_only=True,
                    bind_asset=str(self.asset.pk),
                    apply=True,
                    stdout=io.StringIO(),
                )
        self.assertFalse(any(c[0] != "GET" for c in self.calls))

    def test_configuration_queues_after_source_transaction_to_preserve_lock_order(self):
        self.device.netbox_export_pending = False
        self.device.save()
        with (
            self.captureOnCommitCallbacks(execute=True) as callbacks,
            patch(
                "portal.management.commands.configure_netbox_export.connection",
                return_value=(self.nb, self.nb.base_url, {}),
            ),
        ):
            call_command(
                "configure_netbox_export",
                actor=self.platform.username,
                source=str(self.sa.pk),
                inventory_only=True,
                apply=True,
                stdout=io.StringIO(),
            )
            self.device.refresh_from_db()
            self.assertFalse(self.device.netbox_export_pending)
        self.assertEqual(len(callbacks), 1)
        self.device.refresh_from_db()
        self.assertTrue(self.device.netbox_export_pending)
