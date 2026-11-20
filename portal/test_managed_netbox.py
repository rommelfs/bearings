"""Managed admission is explicit; UUID reconciliation and read-only/revoked boundaries survive retries."""

import base64
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.management import call_command, CommandError
from django.test import Client, override_settings
from django.utils import timezone
from .tests import Fixture
from . import agent_fleets, test_agent_fleets as fleet_tests
from .models import Asset, AgentDevice, AgentEnrollment, InventoryWrite, NetBoxInstance
from .services import process_write
from .connectors.http import ConnectorError
from .connectors.netbox import write_asset


@override_settings(PUBLIC_BASE_URL="https://testserver")
class ManagedFleetTests(Fixture):
    post = fleet_tests.FleetTests.post
    bootstrap = fleet_tests.FleetTests.bootstrap

    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.key.public_key().public_bytes_raw()).decode()
        self.machine = Client(enforce_csrf_checks=True)
        self.request_id = str(uuid.uuid4())
        self.nb = NetBoxInstance.objects.create(
            name="Synthetic native",
            base_url="https://netbox.example.invalid",
            organization=self.a,
            token_env_var="NETBOX_TEST_TOKEN",
            access_mode="read_only",
            virtualization_tags={"lxc": 7},
        )
        self.sa.mode, self.sa.instance, self.sa.tenant_id = "central", self.nb, 42
        self.sa.save()

    def redeem(self, result):
        return self.post(
            "/api/v1/agent/enroll/",
            {
                "schema": "bearings.agent.enroll.v1",
                "request_id": str(uuid.uuid4()),
                "host": {"hostname": "synthetic-new-vm.example.invalid", "addresses": []},
            },
            token=result["grant"],
            identity="enroll:" + result["grant"].split(".")[0],
        )

    def enable(self):
        self.nb.access_mode = "read_write"
        self.nb.save()
        self.sa.agent_managed = True
        self.sa.save(update_fields=["agent_managed"])

    def test_managed_fleet_creates_vm_tag_and_guarded_job_without_client_protocol_change(self):
        self.enable()
        self.fleet, self.token = agent_fleets.create(
            self.admin, self.a, "Managed", "vm", 1, 24, virtualization_type="lxc"
        )
        response = self.bootstrap()
        self.assertEqual(response.status_code, 200)
        result = self.redeem(response.json())
        self.assertEqual(result.status_code, 200, result.content)
        device = AgentDevice.objects.get(pk=result.json()["device_id"])
        self.assertEqual((device.asset.kind, device.asset.virtualization_type), ("vm", "lxc"))
        self.assertTrue(InventoryWrite.objects.get(asset=device.asset).agent_managed)
        self.assertEqual(self.fleet.inventory_mode, "managed")
        self.sa.agent_managed = False
        self.sa.save(update_fields=["agent_managed"])
        with patch("portal.services.write_asset") as api:
            process_write(InventoryWrite.objects.get(asset=device.asset).pk, force=True)
            api.assert_not_called()
        self.assertFalse(
            agent_fleets.active(
                type(self.fleet)
                .objects.select_related("source__instance", "organization", "created_by")
                .get(pk=self.fleet.pk)
            )
        )

    def test_existing_observed_code_is_not_upgraded_and_pending_managed_grant_is_revocable(self):
        self.fleet, self.token = agent_fleets.create(self.admin, self.a, "Observed", "vm", 1, 24)
        self.enable()
        first = self.bootstrap()
        self.assertEqual(first.status_code, 200)
        result = self.redeem(first.json())
        self.assertEqual(result.status_code, 200)
        device = AgentDevice.objects.get(pk=result.json()["device_id"])
        self.assertEqual(device.asset.object_type, "bearings.agent_host")
        self.assertFalse(InventoryWrite.objects.filter(asset=device.asset).exists())
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.key.public_key().public_bytes_raw()).decode()
        self.request_id = str(uuid.uuid4())
        self.fleet, self.token = agent_fleets.create(
            self.admin, self.a, "Managed pending", "vm", 1, 24, virtualization_type="lxc"
        )
        first = self.bootstrap()
        self.assertEqual(first.status_code, 200)
        self.nb.access_mode = "read_only"
        self.nb.save(update_fields=["access_mode"])
        self.assertEqual(self.redeem(first.json()).status_code, 403)
        self.assertIsNone(AgentEnrollment.objects.get(pk=first.json()["grant"].split(".")[0]).asset_id)

    def test_declared_tag_does_not_overwrite_other_netbox_tags_and_lost_ack_reconciles(self):
        self.enable()
        self.nb.access_mode = "read_write"
        self.nb.save()
        self.asset.kind = "vm"
        self.asset.virtualization_type = "lxc"
        self.asset.save()
        record = {
            "id": 9,
            "tenant": {"id": 42},
            "custom_fields": {"bearings_id": str(self.asset.pk)},
            "tags": [{"id": 8}],
        }
        patched = {**record, "tags": [{"id": 8}, {"id": 7}]}
        with (
            patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic-only"}),
            patch("portal.connectors.netbox.approved_base", return_value=self.nb.base_url),
            patch(
                "portal.connectors.netbox.request_json",
                side_effect=[{"count": 1, "results": [record], "next": None}, patched],
            ) as api,
        ):
            self.assertEqual(write_asset(self.asset), ("virtualization.virtualmachine", "9"))
            self.assertEqual([c.args[0] for c in api.call_args_list], ["GET", "PATCH"])
            self.assertEqual(api.call_args_list[-1].kwargs["json"], {"tags": [8, 7]})
        with (
            patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic-only"}),
            patch("portal.connectors.netbox.approved_base", return_value=self.nb.base_url),
            patch(
                "portal.connectors.netbox.request_json",
                return_value={"count": 1, "results": [patched], "next": None},
            ) as api,
        ):
            write_asset(self.asset)
            self.assertEqual(api.call_count, 1)
        foreign = {**record, "tenant": {"id": 43}}
        with (
            patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic-only"}),
            patch("portal.connectors.netbox.approved_base", return_value=self.nb.base_url),
            patch(
                "portal.connectors.netbox.request_json",
                return_value={"count": 1, "results": [foreign], "next": None},
            ) as api,
        ):
            with self.assertRaises(ConnectorError):
                write_asset(self.asset)
            self.assertEqual(api.call_count, 1)

    def test_known_external_identity_cannot_be_replaced_when_uuid_binding_changes(self):
        self.enable()
        self.asset.kind = "vm"
        self.asset.virtualization_type = "lxc"
        self.asset.external_id = "9"
        self.asset.save()
        changed = {
            "id": 10,
            "tenant": {"id": 42},
            "custom_fields": {"bearings_id": str(self.asset.pk)},
            "tags": [{"id": 7}],
        }
        for rows in ([], [changed]):
            with (
                self.subTest(rows=bool(rows)),
                patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic-only"}),
                patch("portal.connectors.netbox.approved_base", return_value=self.nb.base_url),
                patch(
                    "portal.connectors.netbox.request_json",
                    return_value={"count": len(rows), "results": rows, "next": None},
                ) as api,
            ):
                with self.assertRaises(ConnectorError):
                    write_asset(self.asset)
                self.assertEqual([call.args[0] for call in api.call_args_list], ["GET"])


class ManagedNativeCommandTests(Fixture):
    def setUp(self):
        self.key = uuid.uuid4().hex
        self.nb = NetBoxInstance.objects.create(
            name="native-circl-" + self.key,
            base_url="https://netbox.bearings.circl.lu",
            organization=self.a,
            token_env_var="NETBOX_NATIVE_CIRCL_TOKEN",
            auth_scheme="Bearer",
        )
        self.sa.mode, self.sa.instance, self.sa.tenant_id = "central", self.nb, 42
        self.sa.save()
        self.asset.object_type = "bearings.agent_host"
        self.asset.name = "synthetic-managed.example.invalid"
        self.asset.save()
        AgentDevice.objects.create(
            organization=self.a,
            asset=self.asset,
            source=self.sa,
            public_key=base64.b64encode(
                Ed25519PrivateKey.generate().public_key().public_bytes_raw()
            ).decode(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.data = {
            "key": self.key,
            "tenant": 42,
            "defaults": {"site": 1, "role": 2, "device_type": 3, "virtualization_tags": {"lxc": 7}},
        }

    def invoke(self, **kwargs):
        out = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(self.data))):
            call_command(
                "native_managed_netbox",
                actor=self.platform.username,
                host=self.asset.name,
                kind="vm",
                virtualization="lxc",
                stdout=out,
                **kwargs,
            )
        return json.loads(out.getvalue())

    def test_plan_is_read_only_and_non_admin_cannot_enable_managed_inventory(self):
        self.assertFalse(self.invoke()["managed"])
        self.assertFalse(InventoryWrite.objects.exists())
        self.sa.refresh_from_db()
        self.assertFalse(self.sa.agent_managed)
        self.platform.is_superuser = False
        self.platform.save()
        with self.assertRaises(CommandError):
            self.invoke(apply=True)

    def test_apply_and_verify_preserve_asset_and_device_identity(self):
        record = {
            "id": 9,
            "tenant": {"id": 42},
            "custom_fields": {"bearings_id": str(self.asset.pk)},
            "tags": [{"id": 7}],
        }
        row = {"external_id": "9", "object_type": "virtualization.virtualmachine", "record": record}

        def imported(pk):
            Asset.objects.filter(pk=self.asset.pk).update(inventory_seen_at=timezone.now())

        with (
            patch.dict("os.environ", {"NETBOX_NATIVE_CIRCL_TOKEN": "synthetic-only"}),
            patch("portal.connectors.netbox.approved_base", return_value=self.nb.base_url),
            patch(
                "portal.connectors.netbox.request_json",
                side_effect=[{"count": 0, "results": [], "next": None}, record],
            ) as api,
            patch("portal.management.commands.native_managed_netbox.query_objects", return_value=[row]),
            patch("portal.management.commands.native_managed_netbox.refresh_inventory", side_effect=imported),
        ):
            result = self.invoke(apply=True)
            self.assertTrue(result["agent_software_reviews_preserved"])
            self.assertEqual(result["external_id"], "9")
            self.assertEqual(api.call_args_list[-1].kwargs["json"]["tags"], [7])
            verified = self.invoke(verify=True)
            self.assertTrue(verified["import_match"])
            self.assertEqual(api.call_count, 2)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.virtualization_type, "lxc")
        self.assertEqual(self.asset.agent_devices.count(), 1)
        self.assertEqual(InventoryWrite.objects.count(), 1)
