"""Bounded rollout admission, key proof, source ownership and replay/cancellation."""

import base64
import json
import uuid
from datetime import timedelta
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.exceptions import PermissionDenied
from django.test import Client, override_settings
from django.utils import timezone
from .tests import Fixture
from .test_agents import signed
from . import agent_fleets, agents
from .models import (
    NetBoxInstance,
    AgentDevice,
    AgentEnrollment,
    AgentFleet,
    AgentFleetRegistration,
    Asset,
    InventoryWrite,
)


@override_settings(PUBLIC_BASE_URL="https://testserver")
class FleetTests(Fixture):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.key.public_key().public_bytes_raw()).decode()
        self.fleet, self.token = agent_fleets.create(self.admin, self.a, "Synthetic rollout", "server", 2, 24)
        self.machine = Client(enforce_csrf_checks=True)
        self.request_id = str(uuid.uuid4())

    def post(self, path, data, token=None, identity=None, key=None, secure=True):
        raw, headers = signed(
            key or self.key,
            identity or "fleet:" + str(self.fleet.pk),
            path,
            data,
            headers={"Authorization": "Bearer " + (token or self.token)},
        )
        return self.machine.post(
            path,
            raw,
            content_type="application/json",
            secure=secure,
            headers={k: v for k, v in headers.items() if k != "Content-Type"},
        )

    def bootstrap(self, **kwargs):
        data = {
            "schema": "bearings.agent.bootstrap.v1",
            "public_key": self.public,
            "request_id": self.request_id,
        }
        return self.post("/api/v1/agent/bootstrap/", data, **kwargs)

    def redeem(self, result):
        return self.post(
            "/api/v1/agent/enroll/",
            {
                "schema": "bearings.agent.enroll.v1",
                "request_id": str(uuid.uuid4()),
                "host": {
                    "hostname": self.asset.name,
                    "addresses": [{"interface": "eth0", "address": "192.0.2.3/32"}],
                },
            },
            token=result["grant"],
            identity="enroll:" + result["grant"].split(".")[0],
        )

    def test_exact_retry_and_quota(self):
        first = self.bootstrap()
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(self.bootstrap().json(), first.json())
        self.fleet.refresh_from_db()
        self.assertEqual(self.fleet.issued_devices, 1)
        self.assertNotIn(self.token.split(".")[1], json.dumps(list(AgentFleet.objects.values()), default=str))
        self.request_id = str(uuid.uuid4())
        self.assertEqual(self.bootstrap().status_code, 403)
        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
        agent_fleets.issue(self.fleet.pk, self.token.split(".")[1], public, str(uuid.uuid4()))
        third = Ed25519PrivateKey.generate()
        with self.assertRaises(ValueError):
            agent_fleets.issue(
                self.fleet.pk,
                self.token.split(".")[1],
                base64.b64encode(third.public_key().public_bytes_raw()).decode(),
                str(uuid.uuid4()),
            )
        self.assertEqual(AgentFleetRegistration.objects.count(), 2)

    def test_observed_host_never_takes_existing_name_or_writes_read_only_source(self):
        self.sa.instance = NetBoxInstance.objects.create(
            name="Synthetic read-only", base_url="https://netbox.example.invalid", access_mode="read_only"
        )
        self.sa.mode = "central"
        self.sa.tenant_id = 1
        self.sa.save(update_fields=["mode", "instance", "tenant_id"])
        self.fleet, self.token = agent_fleets.create(self.admin, self.a, "Read-only rollout", "server", 2, 24)
        first = self.bootstrap()
        self.assertEqual(first.status_code, 200, first.content)
        response = self.redeem(first.json())
        self.assertEqual(response.status_code, 200, response.content)
        device = AgentDevice.objects.get(pk=response.json()["device_id"])
        self.assertNotEqual(device.asset_id, self.asset.pk)
        self.assertEqual(device.source_id, self.sa.pk)
        self.assertTrue(device.asset.upstream_data["agent_observed_only"])
        self.assertEqual(device.asset.state, "recorded")
        self.assertEqual(device.asset.object_type, "bearings.agent_host")
        self.assertFalse(InventoryWrite.objects.exists())
        self.assertEqual(Asset.objects.filter(name=self.asset.name).count(), 2)
        # A lost bootstrap response still describes the original NEW-host grant after redemption.
        self.assertEqual(self.bootstrap().json(), first.json())
        agent_fleets.revoke(self.admin, self.a, self.fleet.pk)
        device.refresh_from_db()
        self.assertTrue(agents.current(device))

    def test_wrong_bearer_key_transport_and_schema_fail_closed(self):
        for kwargs in (
            {"token": str(self.fleet.pk) + "." + "x" * 43},
            {"key": Ed25519PrivateKey.generate()},
            {"secure": False},
        ):
            self.assertEqual(self.bootstrap(**kwargs).status_code, 403)
        response = self.machine.post(
            "/api/v1/agent/bootstrap/", "[]", content_type="application/json", secure=True
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AgentEnrollment.objects.count(), 0)

    def test_revocation_expiry_and_current_creator_permission(self):
        result = self.bootstrap().json()
        agent_fleets.revoke(self.admin, self.a, self.fleet.pk)
        self.assertEqual(self.bootstrap().status_code, 403)
        self.assertEqual(self.redeem(result).status_code, 403)
        self.fleet.enabled = True
        self.fleet.save(update_fields=["enabled"])
        agents.cancel_enrollment(self.admin, self.a, result["grant"].split(".")[0])
        self.assertEqual(self.bootstrap().status_code, 403)
        self.assertEqual(self.redeem(result).status_code, 403)
        self.assertEqual(AgentEnrollment.objects.count(), 1)
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.assertEqual(self.bootstrap().status_code, 403)

    def test_source_repoint_and_rollout_expiry_invalidate_pending(self):
        result = self.bootstrap().json()
        self.sa.mode = "manual"
        self.sa.save(update_fields=["mode"])
        self.assertEqual(self.redeem(result).status_code, 403)
        self.assertEqual(self.bootstrap().status_code, 403)
        self.sa.mode = "development"
        self.sa.save(update_fields=["mode"])
        AgentFleet.objects.filter(pk=self.fleet.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.redeem(result).status_code, 403)
        self.assertEqual(self.bootstrap().status_code, 403)

    def test_ui_company_roles_csrf_and_invalid_revoke(self):
        path = "/organizations/alpha/agents/fleet/"
        self.login(self.reader)
        self.assertEqual(self.client.get(path).status_code, 403)
        with self.assertRaises(PermissionDenied):
            agent_fleets.create(self.admin, self.b, "Foreign", "server")
        self.login()
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(path, {"action": "revoke", "fleet": "bad"}).status_code, 404)
        self.machine.force_login(self.admin)
        self.assertEqual(
            self.machine.post(path, {"action": "revoke", "fleet": str(self.fleet.pk)}).status_code, 403
        )
        response = self.client.post(
            path,
            {
                "action": "create",
                "name": "Second",
                "new_asset_kind": "server",
                "hours": 24,
                "max_devices": 5,
                "acknowledged": "on",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, "Copy the rollout key now")
        self.assertNotContains(self.client.get(path), "Copy the rollout key now")

    def test_bounds_origin_and_disabled_connection(self):
        from django.core.exceptions import ValidationError

        for limit, hours in ((0, 1), (100001, 1), (1, 0), (1, 169)):
            with self.assertRaises(ValidationError):
                agent_fleets.create(self.admin, self.a, "Bad limits", "server", limit, hours)
        with override_settings(PUBLIC_BASE_URL="http://insecure.example.invalid"):
            with self.assertRaises(ValidationError):
                agent_fleets.create(self.admin, self.a, "Bad origin", "server")
        self.sa.instance = NetBoxInstance.objects.create(
            name="Disabled fixture", base_url="https://netbox.example.invalid", enabled=False
        )
        self.sa.save(update_fields=["instance"])
        with self.assertRaises(ValidationError):
            agent_fleets.create(self.admin, self.a, "Disabled source", "server")
        self.assertEqual(self.bootstrap().status_code, 403)
        self.assertEqual(AgentEnrollment.objects.count(), 0)


@override_settings(PUBLIC_BASE_URL="https://testserver")
class FleetDependencyTests(Fixture):
    def setUp(self):
        self.sa.mode = "central"
        self.sa.tenant_id = 1
        self.sa.agent_managed = True
        self.sa.instance = NetBoxInstance.objects.create(
            name="Scoped virtualization choices",
            base_url="https://netbox.example.invalid",
            access_mode="read_write",
            virtualization_tags={"lxc": 7, "vmware": 8},
        )
        self.sa.save()
        self.client.force_login(self.admin)

    def data(self, kind="vm", virtualization="lxc"):
        return {
            "action": "create",
            "organization": "alpha",
            "name": "Dependent rollout",
            "new_asset_kind": kind,
            "virtualization_type": virtualization,
            "max_devices": 3,
            "hours": 24,
            "acknowledged": "on",
        }

    def test_managed_vm_rollout_offers_only_configured_types(self):
        path = self.url("agent-fleets")
        for entry in (path, "/downloads/rollout/?organization=alpha"):
            response = self.client.get(entry, follow=True)
            choices = dict(response.context["form"].fields["virtualization_type"].choices)
            self.assertEqual(set(choices), {"", "lxc", "vmware"})
            self.assertContains(response, "data-rollout-virtualization")
            self.assertContains(response, "portal/rollout-form.js")
            response = self.client.post(path, self.data())
            self.assertTrue(response.context["fleet_token"])
        self.assertEqual(
            AgentFleet.objects.filter(virtualization_type="lxc", inventory_mode="managed").count(), 2
        )

    def test_host_type_change_drops_stale_virtualization(self):
        for kind in ("server", "desktop", "laptop"):
            response = self.client.post("/downloads/linux/", self.data(kind))
            self.assertTrue(response.context["fleet_token"])
        self.assertEqual(AgentFleet.objects.filter(virtualization_type="").count(), 3)

    def test_unconfigured_virtualization_is_a_field_error_and_does_not_create(self):
        response = self.client.post("/downloads/linux/", self.data(virtualization="incus"))
        self.assertIn("virtualization_type", response.context["form"].errors)
        self.assertIsNone(response.context["fleet_token"])
        self.assertFalse(AgentFleet.objects.exists())

    def test_read_only_and_unconfigured_sources_hide_and_ignore_virtualization(self):
        for changes in (
            {"access_mode": "read_only"},
            {"access_mode": "read_write", "virtualization_tags": {}},
        ):
            for field, value in changes.items():
                setattr(self.sa.instance, field, value)
            self.sa.instance.save()
            response = self.client.post("/downloads/linux/", self.data())
            self.assertTrue(response.context["fleet_token"])
            self.assertNotContains(response, "data-rollout-virtualization")
        self.assertFalse(AgentFleet.objects.exclude(virtualization_type="").exists())
