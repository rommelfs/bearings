"""Authenticated source identity, exact-once admission, publication ownership and retained uncertainty."""

import base64
import hashlib
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client
from django.utils import timezone
from http_message_signatures import HTTPMessageSigner, HTTPSignatureKeyResolver, algorithms
from .tests import Fixture
from . import agents
from .agent_protocol import COVERED, TAG
from .models import (
    AgentDevice,
    AgentReport,
    AgentComponent,
    AgentEnrollment,
    Installation,
    Finding,
)


class Keys(HTTPSignatureKeyResolver):
    def __init__(self, key):
        self.key = key

    def resolve_private_key(self, key_id):
        return self.key


def signed(key, identity, path, data, *, headers=None, covered=COVERED, created=None):
    raw = json.dumps(data, separators=(",", ":")).encode()
    hs = {
        "Content-Type": "application/json",
        "Content-Digest": "sha-256=:" + base64.b64encode(hashlib.sha256(raw).digest()).decode() + ":",
        "X-Bearings-Key": identity,
    }
    if headers:
        hs.update(headers)
    msg = SimpleNamespace(method="POST", url="https://testserver" + path, headers=hs)
    created = created or timezone.now()
    HTTPMessageSigner(signature_algorithm=algorithms.ED25519, key_resolver=Keys(key)).sign(
        msg,
        key_id=identity,
        created=created,
        expires=created + timedelta(minutes=5),
        nonce=str(uuid.uuid4()),
        tag=TAG,
        label="bearings",
        covered_component_ids=covered,
    )
    return raw, hs


class AgentTests(Fixture):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.key.public_key().public_bytes_raw()).decode()
        self.machine = Client(enforce_csrf_checks=True)

    def post(self, path, data, key=None, identity=None, **kwargs):
        raw, headers = signed(
            key or self.key, identity or "device:" + str(self.device.pk), path, data, **kwargs
        )
        return self.machine.post(
            path,
            raw,
            content_type="application/json",
            secure=True,
            headers={k: v for k, v in headers.items() if k != "Content-Type"},
        )

    def enroll(self):
        grant, token = agents.create_enrollment(self.admin, self.a, self.asset, self.public)
        self.grant = grant
        self.token = token
        data = {"schema": "bearings.agent.enroll.v1", "request_id": str(uuid.uuid4())}
        r = self.post(
            "/api/v1/agent/enroll/",
            data,
            identity="enroll:" + str(grant.pk),
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.device = AgentDevice.objects.get(pk=r.json()["device_id"])
        return data

    def data(self, sequence=1, version="1:1.24.0-2ubuntu7.5", scope="system-packages"):
        return {
            "schema": TAG,
            "report_id": str(uuid.uuid4()),
            "sequence": sequence,
            "observed_at": timezone.now().isoformat(),
            "scope": scope,
            "complete": True,
            "os": {
                "id": "ubuntu",
                "version": "24.04",
                "architecture": "x86_64",
                "kernel": "6.8.0-example",
                "reboot_hint": "not_observed",
            },
            "components": [
                {
                    "key": "dpkg:nginx:amd64",
                    "manager": "dpkg",
                    "name": "nginx",
                    "version": version,
                    "architecture": "amd64",
                }
            ],
            "services": [{"name": "nginx", "state": "different_executable", "coverage": "main_process_only"}],
        }

    def send(self, data=None):
        return self.post("/api/v1/agent/reports/", data or self.data())

    def relax(self):
        AgentDevice.objects.filter(pk=self.device.pk).update(
            last_received_at=timezone.now() - timedelta(seconds=11)
        )

    def test_public_key_bound_one_use_enrollment_and_lost_ack(self):
        data = self.enroll()
        r = self.post(
            "/api/v1/agent/enroll/",
            data,
            identity="enroll:" + str(self.grant.pk),
            headers={"Authorization": "Bearer " + self.token},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AgentDevice.objects.count(), 1)
        data["request_id"] = str(uuid.uuid4())
        self.assertEqual(
            self.post(
                "/api/v1/agent/enroll/",
                data,
                identity="enroll:" + str(self.grant.pk),
                headers={"Authorization": "Bearer " + self.token},
            ).status_code,
            403,
        )

    def test_wrong_key_expired_grant_and_unapproved_person_cannot_enroll(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            agents.create_enrollment(self.editor, self.a, self.asset, self.public)
        with self.assertRaises(PermissionDenied):
            agents.create_enrollment(self.analyst, self.a, self.asset, self.public)
        with self.assertRaises(PermissionDenied):
            agents.create_enrollment(self.admin, self.a, self.other, self.public)
        grant, token = agents.create_enrollment(self.admin, self.a, self.asset, self.public)
        data = {"schema": "bearings.agent.enroll.v1", "request_id": str(uuid.uuid4())}
        r = self.post(
            "/api/v1/agent/enroll/",
            data,
            key=Ed25519PrivateKey.generate(),
            identity="enroll:" + str(grant.pk),
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(r.status_code, 403)
        AgentEnrollment.objects.filter(pk=grant.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(
            self.post(
                "/api/v1/agent/enroll/",
                data,
                identity="enroll:" + str(grant.pk),
                headers={"Authorization": "Bearer " + token},
            ).status_code,
            403,
        )
        self.assertFalse(AgentDevice.objects.exists())

    def test_duplicate_is_exactly_once_and_different_bytes_or_old_sequence_rejected(self):
        self.enroll()
        data = self.data()
        r = self.send(data)
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(self.send(data).json()["report_id"], data["report_id"])
        data["components"][0]["version"] = "changed"
        self.assertEqual(self.send(data).status_code, 403)
        self.assertEqual(self.send(self.data()).status_code, 403)
        self.assertEqual(AgentReport.objects.count(), 1)

    def test_body_method_target_and_signature_coverage_are_authenticated(self):
        self.enroll()
        data = self.data()
        path = "/api/v1/agent/reports/"
        raw, headers = signed(self.key, "device:" + str(self.device.pk), path, data)
        self.assertEqual(
            self.machine.post(
                path,
                raw + b" ",
                content_type="application/json",
                secure=True,
                headers={k: v for k, v in headers.items() if k != "Content-Type"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.machine.post(
                "/api/v1/agent/status/",
                raw,
                content_type="application/json",
                secure=True,
                headers={k: v for k, v in headers.items() if k != "Content-Type"},
            ).status_code,
            403,
        )
        self.assertEqual(self.post(path, data, covered=("@method", "@path")).status_code, 403)
        self.assertEqual(
            self.post(path, data, created=timezone.now() - timedelta(minutes=10)).status_code, 403
        )
        self.assertEqual(
            self.post(path, data, created=timezone.now() + timedelta(minutes=2)).status_code, 403
        )
        self.assertFalse(AgentReport.objects.exists())

    def test_browser_session_or_plain_http_does_not_authenticate_machine(self):
        self.enroll()
        self.login()
        self.assertEqual(
            self.client.post(
                "/api/v1/agent/reports/", self.data(), content_type="application/json", secure=True
            ).status_code,
            403,
        )
        raw, headers = signed(
            self.key, "device:" + str(self.device.pk), "/api/v1/agent/reports/", self.data()
        )
        self.assertEqual(
            self.machine.post(
                "/api/v1/agent/reports/",
                raw,
                content_type="application/json",
                headers={k: v for k, v in headers.items() if k != "Content-Type"},
            ).status_code,
            403,
        )

    def test_only_explicit_version_binding_projects_and_never_resolves_findings(self):
        self.enroll()
        finding = self.record_finding()
        before = finding.status
        data = self.data()
        self.assertEqual(self.send(data).status_code, 202)
        agents.process_pending()
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "")
        c = AgentComponent.objects.get(device=self.device)
        agents.bind(self.admin, self.a, c.pk, self.installation.pk)
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, data["components"][0]["version"])
        self.relax()
        self.send(self.data(2, "1:1.24.0-2ubuntu7.6"))
        agents.process_pending()
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "1:1.24.0-2ubuntu7.6")
        finding.refresh_from_db()
        self.assertEqual(finding.status, before)
        self.device.refresh_from_db()
        self.assertEqual(self.device.services[0]["state"], "different_executable")
        self.login()
        r = self.client.get("/organizations/alpha/assets/" + str(self.asset.pk) + "/")
        self.assertContains(r, "Device-reported version")
        self.assertEqual(
            self.client.get(
                "/organizations/alpha/software/" + str(self.installation.pk) + "/version/"
            ).status_code,
            302,
        )

    def test_foreign_installation_and_editor_binding_refused(self):
        self.enroll()
        self.send()
        agents.process_pending()
        c = AgentComponent.objects.get()
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            agents.bind(self.editor, self.a, c.pk, self.installation.pk)
        p = self.product.__class__.objects.create(organization=self.b, name="foreign")
        other = Installation.objects.create(asset=self.other, product=p, version="private")
        with self.assertRaises(Installation.DoesNotExist):
            agents.bind(self.admin, self.a, c.pk, other.pk)
        self.login(self.reader)
        self.assertEqual(
            self.client.post(
                "/organizations/alpha/agents/", {"action": "revoke", "device": self.device.pk}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/organizations/beta/agents/").status_code, 404)

    def test_revoked_expired_and_source_changed_devices_cannot_publish_queued_reports(self):
        self.enroll()
        self.send()
        agents.revoke(self.admin, self.a, self.device.pk)
        agents.process_pending()
        self.assertEqual(AgentReport.objects.get().status, "rejected")
        self.assertEqual(self.send().status_code, 403)
        AgentDevice.objects.filter(pk=self.device.pk).update(
            enabled=True, expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.send().status_code, 403)

    def test_incomplete_or_invalid_scope_cannot_remove_packages(self):
        self.enroll()
        self.send()
        agents.process_pending()
        c = AgentComponent.objects.get()
        agents.bind(self.admin, self.a, c.pk, self.installation.pk)
        self.relax()
        data = self.data(2)
        data["complete"] = False
        data["components"][0].update(key="dpkg:curl:amd64", name="curl")
        self.assertEqual(self.send(data).status_code, 202)
        agents.process_pending()
        c.refresh_from_db()
        self.assertIsNone(c.missing_since)
        self.relax()
        data = self.data(3)
        data["components"][0].update(key="dpkg:curl:amd64", name="curl")
        self.send(data)
        agents.process_pending()
        c.refresh_from_db()
        self.assertIsNotNone(c.missing_since)
        self.installation.refresh_from_db()
        self.assertNotEqual(self.installation.version, "")
        self.assertTrue(Finding.objects.count() == 0)

    def test_late_facts_remain_stale_and_cannot_overwrite_bound_version(self):
        self.enroll()
        data = self.data()
        data["observed_at"] = (timezone.now() - timedelta(days=2)).isoformat()
        self.send(data)
        agents.process_pending()
        self.device.refresh_from_db()
        self.assertTrue(self.device.stale)
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            agents.bind(self.admin, self.a, AgentComponent.objects.get().pk, self.installation.pk)

    def test_out_of_order_publication_rejects_superseded_input(self):
        self.enroll()
        first = self.data()
        self.send(first)
        self.relax()
        second = self.data(2, "2.0")
        self.send(second)
        agents.process_one(self.device.pk, second["report_id"])
        agents.process_one(self.device.pk, first["report_id"])
        self.assertEqual(AgentReport.objects.get(pk=first["report_id"]).status, "superseded")
        self.assertEqual(AgentComponent.objects.get().version, "2.0")

    def test_atomic_failure_preserves_pending_input_and_old_projection(self):
        self.enroll()
        self.send()
        with patch(
            "portal.agents.AgentComponent.objects.bulk_create", side_effect=RuntimeError("synthetic failure")
        ):
            with self.assertRaises(RuntimeError):
                agents.process_pending()
        self.assertEqual(AgentReport.objects.get().status, "pending")
        self.assertFalse(AgentComponent.objects.exists())
        agents.process_pending()
        self.assertEqual(AgentReport.objects.get().status, "applied")

    def test_receipts_are_scoped_and_observations_do_not_grant_circl_sharing(self):
        self.enroll()
        data = self.data()
        self.send(data)
        r = self.post(
            "/api/v1/agent/status/", {"schema": "bearings.agent.status.v1", "report_id": data["report_id"]}
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("components", r.json())
        self.assertEqual(
            self.post(
                "/api/v1/agent/status/",
                {"schema": "bearings.agent.status.v1", "report_id": str(uuid.uuid4())},
            ).status_code,
            403,
        )
        self.a.refresh_from_db()
        self.assertTrue(self.a.operator_visibility)
        self.login(self.analyst)
        self.assertNotContains(self.client.get("/organizations/alpha/agents/"), "enrollment grant")

    def test_cancel_pending_or_redeemed_grant_is_audited_and_revokes_access(self):
        self.enroll()
        agents.cancel_enrollment(self.admin, self.a, self.grant.pk)
        self.assertEqual(self.send().status_code, 403)
        self.device.refresh_from_db()
        self.assertFalse(self.device.enabled)

    def test_source_reassignment_after_admission_preserves_last_known_software(self):
        self.enroll()
        self.send()
        from .models import Asset

        Asset.objects.filter(pk=self.asset.pk).update(source=self.sb)
        agents.process_pending()
        self.assertEqual(AgentReport.objects.get().status, "rejected")
        self.assertFalse(AgentComponent.objects.exists())
        self.assertEqual(self.send().status_code, 403)

    def test_strict_schema_scope_and_package_slot_validation(self):
        self.enroll()
        mutations = [
            lambda d: d.update(organization="other"),
            lambda d: d.update(report_id=42),
            lambda d: d.update(report_id={}),
            lambda d: d.update(report_id=None),
            lambda d: d.update(complete="true"),
            lambda d: d.update(components=d["components"] * 2),
            lambda d: d["components"][0].update(version="x" * 121),
            lambda d: d.update(scope="unknown"),
            lambda d: d.update(scope="selected-packages"),
            lambda d: d.update(services=[{"name": "shell", "state": "unknown", "coverage": "unavailable"}]),
        ]
        for mutate in mutations:
            data = self.data()
            mutate(data)
            self.assertEqual(self.send(data).status_code, 403)
        self.assertFalse(AgentReport.objects.exists())
        data = self.data()
        c = data["components"][0]
        c.update(
            manager="rpm",
            name="kernel-core",
            version="0:5.14.0-1.el9",
            architecture="x86_64",
            key="rpm:kernel-core:x86_64@0:5.14.0-1.el9",
        )
        self.assertEqual(self.send(data).status_code, 202)

    def test_authenticated_delivery_throttle_does_not_reject_idempotent_retry(self):
        self.enroll()
        data = self.data()
        self.send(data)
        self.assertEqual(self.send(data).status_code, 202)
        self.assertEqual(self.send(self.data(2)).status_code, 429)
        self.assertEqual(AgentReport.objects.count(), 1)

    def test_newer_stale_report_does_not_overwrite_current_bound_version(self):
        self.enroll()
        self.send()
        agents.process_pending()
        component = AgentComponent.objects.get()
        agents.bind(self.admin, self.a, component.pk, self.installation.pk)
        self.relax()
        data = self.data(2, "old-delayed")
        data["observed_at"] = (timezone.now() - timedelta(days=2)).isoformat()
        self.send(data)
        agents.process_pending()
        self.assertEqual(AgentReport.objects.get(sequence=2).status, "rejected")
        self.installation.refresh_from_db()
        self.assertNotEqual(self.installation.version, "old-delayed")

    def test_partial_reports_do_not_refresh_other_components_or_full_coverage(self):
        self.enroll()
        data = self.data()
        data["observed_at"] = (timezone.now() - timedelta(days=2)).isoformat()
        self.send(data)
        agents.process_pending()
        old = AgentComponent.objects.get()
        self.assertTrue(old.stale)
        self.relax()
        new = self.data(2)
        new.update(scope="selected-packages", complete=False, services=[])
        new["components"][0].update(key="dpkg:bash:amd64", name="bash")
        self.send(new)
        agents.process_pending()
        self.device.refresh_from_db()
        old.refresh_from_db()
        self.assertFalse(self.device.stale)
        self.assertTrue(old.stale)
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            agents.bind(self.admin, self.a, old.pk, self.installation.pk)
        self.assertLess(self.device.last_complete_at, timezone.now() - timedelta(days=1))
        self.assertEqual(self.device.runtime_services[0]["state"], "different_executable")
        self.assertTrue(self.device.runtime_services[0]["stale"])

    def test_device_daily_budget_and_wrong_signing_key(self):
        self.enroll()
        self.assertEqual(
            self.post("/api/v1/agent/reports/", self.data(), key=Ed25519PrivateKey.generate()).status_code,
            403,
        )
        AgentDevice.objects.filter(pk=self.device.pk).update(
            last_received_at=timezone.now() - timedelta(minutes=1), daily_bytes=32 * 1024 * 1024
        )
        self.assertEqual(self.send().status_code, 429)
        self.assertFalse(AgentReport.objects.exists())

    def test_malformed_private_management_ids_fail_without_server_error(self):
        self.login()
        self.assertEqual(self.client.get("/organizations/alpha/agents/?device=not-a-uuid").status_code, 404)

    def test_json_duplicate_keys_and_excessive_nesting_are_rejected(self):
        from .agent_protocol import decode

        for raw in [b'{"sequence":1,"sequence":2}', b'{"n":NaN}', b"[" * 1500 + b"0" + b"]" * 1500]:
            with self.assertRaises(ValueError):
                decode(raw)

    def test_explicit_new_host_registration_is_key_bound_and_never_verifies_ip_authority(self):
        from .models import Asset, InfrastructureClaim, InventoryWrite

        self.sa.mode = "manual"
        self.sa.save(update_fields=["mode"])
        grant, token = agents.create_enrollment(self.admin, self.a, None, self.public, new_asset_kind="vm")
        data = {
            "schema": "bearings.agent.enroll.v1",
            "request_id": str(uuid.uuid4()),
            "host": {
                "hostname": "synthetic-new-linux",
                "addresses": [
                    {"interface": "eth0", "address": "198.51.100.21/32"},
                    {"interface": "eth0", "address": "2001:db8::21/64"},
                ],
            },
        }
        r = self.post(
            "/api/v1/agent/enroll/",
            data,
            identity="enroll:" + str(grant.pk),
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(r.status_code, 200, r.content)
        device = AgentDevice.objects.get(pk=r.json()["device_id"])
        self.assertEqual(device.asset.kind, "vm")
        self.assertEqual(device.asset.state, "recorded")
        self.assertEqual(device.asset.name, "synthetic-new-linux")
        self.assertEqual(device.reported_network, data["host"])
        grant.refresh_from_db()
        self.assertEqual(json.loads(bytes(grant.signed_body))["host"], data["host"])
        self.assertTrue(grant.signature_input)
        self.assertTrue(grant.signature)
        self.assertNotIn(token.encode(), bytes(grant.signed_body))
        self.assertFalse(InfrastructureClaim.objects.filter(organization=self.a, status="verified").exists())
        self.assertFalse(InventoryWrite.objects.exists())
        r = self.post(
            "/api/v1/agent/enroll/",
            data,
            identity="enroll:" + str(grant.pk),
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(r.json()["device_id"], str(device.pk))
        self.assertEqual(Asset.objects.filter(name="synthetic-new-linux").count(), 1)

    def test_existing_hostname_requires_review_and_host_input_never_rebinds_identity(self):
        grant, token = agents.create_enrollment(
            self.admin, self.a, None, self.public, new_asset_kind="server"
        )
        data = {
            "schema": "bearings.agent.enroll.v1",
            "request_id": str(uuid.uuid4()),
            "host": {"hostname": self.asset.name, "addresses": []},
        }
        self.assertEqual(
            self.post(
                "/api/v1/agent/enroll/",
                data,
                identity="enroll:" + str(grant.pk),
                headers={"Authorization": "Bearer " + token},
            ).status_code,
            403,
        )
        self.assertFalse(AgentDevice.objects.exists())

    def test_registration_requires_explicit_profile_and_rejects_invalid_address_claims(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            agents.create_enrollment(self.admin, self.a, None, self.public)
        grant, token = agents.create_enrollment(self.admin, self.a, None, self.public, new_asset_kind="vm")
        data = {
            "schema": "bearings.agent.enroll.v1",
            "request_id": str(uuid.uuid4()),
            "host": {
                "hostname": "synthetic-host",
                "addresses": [{"interface": "eth0", "address": "127.0.0.1/8"}],
            },
        }
        self.assertEqual(
            self.post(
                "/api/v1/agent/enroll/",
                data,
                identity="enroll:" + str(grant.pk),
                headers={"Authorization": "Bearer " + token},
            ).status_code,
            403,
        )

    def test_new_netbox_host_uses_existing_write_queue_and_read_only_refusal(self):
        from .models import NetBoxInstance, InventoryWrite
        from django.core.exceptions import PermissionDenied

        instance = NetBoxInstance.objects.create(
            name="SYNTHETIC source",
            base_url="https://netbox.example.invalid",
            token_env_var="TEST_ONLY_NETBOX_TOKEN",
            access_mode="read_only",
        )
        self.sa.mode = "central"
        self.sa.instance = instance
        self.sa.tenant_id = 7
        self.sa.save()
        with self.assertRaises(PermissionDenied):
            agents.create_enrollment(self.admin, self.a, None, self.public, new_asset_kind="vm")
        instance.access_mode = "read_write"
        instance.save()
        grant, token = agents.create_enrollment(self.admin, self.a, None, self.public, new_asset_kind="vm")
        data = {
            "schema": "bearings.agent.enroll.v1",
            "request_id": str(uuid.uuid4()),
            "host": {"hostname": "synthetic-netbox-new", "addresses": []},
        }
        r = self.post(
            "/api/v1/agent/enroll/",
            data,
            identity="enroll:" + str(grant.pk),
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(r.status_code, 200, r.content)
        device = AgentDevice.objects.get(pk=r.json()["device_id"])
        job = InventoryWrite.objects.get(asset=device.asset)
        self.assertIsNone(job.completed_at)
        self.assertEqual(job.asset.state, "pending")
        self.assertEqual(device.source_id, self.sa.pk)
        self.assertEqual(device.source.tenant_id, 7)

    def test_500_owned_version_changes_are_batched_without_changing_other_company(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from .models import Product

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
            for i in range(500)
        ]
        self.send(data)
        agents.process_pending()
        components = list(AgentComponent.objects.order_by("key"))
        products = Product.objects.bulk_create(
            [
                Product(organization=self.a, name=c.name, identifier="pkg:deb/test/" + c.name)
                for c in components
            ]
        )
        installs = Installation.objects.bulk_create(
            [Installation(asset=self.asset, product=p, version="1.0") for p in products]
        )
        for component, installation in zip(components, installs):
            component.installation = installation
        AgentComponent.objects.bulk_update(components, ["installation"])
        self.relax()
        data["sequence"] = 2
        data["report_id"] = str(uuid.uuid4())
        for value in data["components"]:
            value["version"] = "2.0"
        self.assertEqual(self.send(data).status_code, 202)
        with CaptureQueriesContext(connection) as queries:
            agents.process_pending()
        self.assertLessEqual(len(queries), 30)
        self.assertEqual(Installation.objects.filter(asset=self.asset, version="2.0").count(), 500)
        self.assertFalse(Installation.objects.filter(asset=self.other).exists())

    def test_enrollment_asset_choices_are_bounded_searchable_and_keep_explicit_selection(self):
        from .agent_views import EnrollmentForm
        from .models import Asset

        Asset.objects.bulk_create(
            [
                Asset(organization=self.a, source=self.asset.source, kind="server", name=f"host-{n:04d}")
                for n in range(300)
            ]
        )
        self.assertLessEqual(EnrollmentForm(org=self.a).fields["asset"].queryset.count(), 250)
        chosen = self.a.assets.get(name="host-0299")
        form = EnrollmentForm(org=self.a, selected_asset=str(chosen.pk))
        self.assertIn(chosen, form.fields["asset"].queryset)
        self.assertLessEqual(form.fields["asset"].queryset.count(), 251)
        form = EnrollmentForm(org=self.a, asset_query="host-0299")
        self.assertEqual(list(form.fields["asset"].queryset), [chosen])

    def test_new_binding_during_manual_form_validation_prevents_version_overwrite(self):
        from .discovery_views import VersionForm

        self.enroll()
        self.send()
        agents.process_pending()
        component = AgentComponent.objects.get()
        validate = VersionForm.is_valid

        def concurrent_binding(form):
            result = validate(form)
            agents.bind(self.admin, self.a, component.pk, self.installation.pk)
            return result

        self.login()
        with patch.object(VersionForm, "is_valid", concurrent_binding):
            response = self.client.post(
                f"/organizations/alpha/software/{self.installation.pk}/version/",
                {"version": "manual-race", "edition": "", "build": ""},
            )
        self.assertRedirects(response, "/organizations/alpha/agents/", fetch_redirect_response=False)
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, component.version)

    def binary_data(self, sequence=1, version="1.2.3"):
        data = self.data(sequence, scope="configured-binaries")
        data["complete"] = False
        data["services"] = []
        data["components"] = [
            {
                "key": "binary:custom-nginx:x86_64",
                "manager": "binary",
                "name": "nginx",
                "version": version,
                "architecture": "x86_64",
                "binary": {"path": "/opt/nginx/sbin/nginx", "sha256": "a" * 64},
            }
        ]
        return data

    def test_configured_binary_evidence_and_explicit_version_ownership(self):
        self.enroll()
        finding = self.record_finding()
        before = finding.status
        self.assertEqual(self.send(self.data()).status_code, 202)
        agents.process_pending()
        self.device.refresh_from_db()
        full_at = self.device.last_complete_at
        package = AgentComponent.objects.get(manager="dpkg")
        package_time = package.observed_at
        self.relax()
        self.assertEqual(self.send(self.binary_data(2)).status_code, 202)
        agents.process_pending()
        component = AgentComponent.objects.get(manager="binary")
        self.assertEqual(component.binary["sha256"], "a" * 64)
        self.assertEqual(component.binary["path"], "/opt/nginx/sbin/nginx")
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "")
        agents.bind(self.admin, self.a, component.pk, self.installation.pk)
        self.relax()
        data = self.binary_data(3, "1.2.4-custom")
        data["components"][0]["binary"]["sha256"] = "b" * 64
        self.send(data)
        agents.process_pending()
        self.installation.refresh_from_db()
        component.refresh_from_db()
        self.device.refresh_from_db()
        package.refresh_from_db()
        finding.refresh_from_db()
        self.assertEqual(self.installation.version, "1.2.4-custom")
        self.assertEqual(component.binary["sha256"], "b" * 64)
        self.assertEqual(package.observed_at, package_time)
        self.assertIsNone(package.missing_since)
        self.assertEqual(self.device.last_complete_at, full_at)
        self.assertEqual(finding.status, before)
        first = AgentReport.objects.get(sequence=2)
        self.assertIn(b'"sha256":"aaaaaaaa', bytes(first.body))
        self.login()
        response = self.client.get(f"/organizations/alpha/agents/?device={self.device.pk}")
        self.assertContains(response, "/opt/nginx/sbin/nginx")
        self.assertContains(response, "b" * 64)

    def test_binary_scope_and_evidence_are_strict_and_cannot_impersonate_packages(self):
        self.enroll()
        for mutate in [
            lambda d: d.update(complete=True),
            lambda d: d.update(scope="system-packages"),
            lambda d: d["components"][0].update(manager="rpm"),
            lambda d: d["components"][0].update(key="binary:other:wrong-arch"),
            lambda d: d["components"][0]["binary"].update(path="relative"),
            lambda d: d["components"][0]["binary"].update(path="/opt/../secret"),
            lambda d: d["components"][0]["binary"].update(sha256="not-a-hash"),
            lambda d: d["components"][0]["binary"].update(args=["arbitrary-command"]),
            lambda d: d.update(components=d["components"] * 17),
        ]:
            data = self.binary_data()
            mutate(data)
            with self.subTest(data=data):
                self.assertEqual(self.send(data).status_code, 403)
        self.assertFalse(AgentReport.objects.exists())

    def test_creating_binary_software_uses_generic_identity_not_rpm(self):
        self.enroll()
        self.send(self.binary_data())
        agents.process_pending()
        c = AgentComponent.objects.get()
        installation = agents.bind(self.admin, self.a, c.pk, create=True)
        self.assertTrue(installation.product.identifier.startswith("pkg:generic/"))
        self.assertEqual(installation.version, "1.2.3")

    def test_bound_binary_cannot_silently_change_program_path_or_name(self):
        self.enroll()
        self.send(self.binary_data())
        agents.process_pending()
        c = AgentComponent.objects.get()
        agents.bind(self.admin, self.a, c.pk, self.installation.pk)
        self.relax()
        data = self.binary_data(2, "99.0.0")
        data["components"][0]["binary"]["path"] = "/opt/another-program/bin/tool"
        self.send(data)
        agents.process_pending()
        self.assertEqual(AgentReport.objects.get(sequence=2).status, "rejected")
        self.installation.refresh_from_db()
        c.refresh_from_db()
        self.assertEqual(self.installation.version, "1.2.3")
        self.assertEqual(c.binary["path"], "/opt/nginx/sbin/nginx")
