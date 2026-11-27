"""Windows client contract against the real signature verifier and publication pipeline."""

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
from unittest.mock import patch
from datetime import timedelta

from django.utils import timezone
from django.test import TransactionTestCase, override_settings
from clients.windows import bearings_windows as client
from . import agent_fleets, agents, agent_protocol, distro_cves, test_agent_client
from .models import AgentDevice, AgentEnrollment, AgentReport, Asset, Installation
from . import test_agents
from .tests import Fixture


class Registry:
    """Synthetic Windows registry; no Windows execution is claimed."""

    HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY, KEY_WOW64_32KEY = 1, 2, 4, 8

    def __init__(self):
        self.entries = {
            (client.OS_KEY, 4): dict(
                ProductName="Windows 11 Pro",
                EditionID="Professional",
                DisplayVersion="24H2",
                CurrentBuildNumber="26100",
                UBR=1234,
            ),
            (client.UNINSTALL, 4): ["Example"],
            (client.UNINSTALL, 8): ["Example", "NoVersion"],
            (client.UNINSTALL + "\\Example", 4): dict(
                DisplayName="Example Tools (64-bit)", DisplayVersion="2.1", Publisher="Example"
            ),
            (client.UNINSTALL + "\\Example", 8): dict(
                DisplayName="Example Tools (32-bit)", DisplayVersion="1.9"
            ),
            (client.UNINSTALL + "\\NoVersion", 8): dict(DisplayName="Version inconnue – Werkzeug"),
        }

    def OpenKey(self, hive, path, reserved, access):
        entry = self.entries[(path, access & 12)]

        class Key:
            def __enter__(self):
                return entry

            def __exit__(self, *_):
                pass

        return Key()

    def QueryValueEx(self, key, field):
        if field not in key:
            raise FileNotFoundError(field)
        return key[field], 1

    def QueryInfoKey(self, key):
        return len(key), 0, 0

    def EnumKey(self, key, index):
        return key[index]


def observation():
    with patch.object(client, "native_architecture", return_value="x86_64"):
        return client.collect(Registry())


class MemoryStore:
    def __init__(self, seed, **extra):
        self.data = dict(seed=base64.b64encode(seed).decode(), counter=0, queue=[], **extra)
        self.saved = None

    def save(self):
        self.saved = deepcopy(self.data)


class WindowsAgentTests(Fixture):
    legacy_manual_projection = False
    setUp = test_agents.AgentTests.setUp
    post = test_agents.AgentTests.post
    enroll = test_agents.AgentTests.enroll
    relax = test_agents.AgentTests.relax
    send = test_agents.AgentTests.send

    def test_portal_explains_standalone_windows_client_setup(self):
        self.login(self.admin)
        downloads = self.client.get("/downloads/windows/")
        self.assertContains(downloads, "Rollout keys")
        self.assertContains(downloads, 'href="/downloads/rollout/"')
        self.assertContains(downloads, r".\bearings-windows.exe enroll --code")
        self.assertContains(downloads, r".\bearings-windows.exe watch")
        self.assertContains(downloads, "Rollout to several computers")
        self.assertContains(downloads, "Windows Task Scheduler")
        self.assertContains(downloads, "Automatic client updates")
        self.assertContains(downloads, "Existing older clients need one manual bootstrap upgrade")
        self.assertContains(downloads, "Register and enable reports")
        self.assertContains(downloads, "Windows downloads are currently unavailable")
        self.assertNotContains(downloads, "/downloads/windows/bearings-windows-x64.zip")
        self.assertContains(
            self.client.get("/downloads/linux/?organization=alpha"),
            'href="/downloads/windows/?organization=alpha"',
        )
        center = self.client.get(self.url("agent-center"))
        self.assertNotContains(center, "Create a Windows registration code")
        self.assertContains(center, 'href="/downloads/windows/"')
        platforms = self.client.get("/downloads/?organization=alpha")
        self.assertContains(platforms, 'href="/downloads/linux/?organization=alpha"')
        self.assertContains(platforms, 'href="/downloads/windows/?organization=alpha"')
        self.assertContains(platforms, 'href="/downloads/rollout/?organization=alpha"')
        self.assertContains(platforms, 'href="/downloads/profiles/?organization=alpha"')

    def test_download_administration_entries_are_scoped(self):
        self.login(self.reader)
        for path in ("/downloads/rollout/", "/downloads/profiles/"):
            self.assertContains(self.client.get(path), "Ask your company administrator")
            self.assertEqual(self.client.get(path, {"organization": self.a.slug}).status_code, 404)
        self.login(self.admin)
        self.assertRedirects(self.client.get("/downloads/profiles/"), self.url("application-profiles"))
        self.assertEqual(
            self.client.get("/downloads/rollout/", {"organization": self.b.slug}).status_code, 404
        )
        self.login(self.platform)
        path = "/downloads/rollout/"
        self.assertContains(self.client.get(path), 'name="organization" required')
        result = self.client.get(path, {"organization": self.a.slug}, follow=True)
        self.assertEqual(result.redirect_chain, [(self.url("agent-fleets"), 302)])
        self.assertContains(result, "Create limited rollout key")
        self.assertNotContains(result, "Install the Bearings Linux client")
        self.assertNotContains(result, "Existing Windows asset")
        self.assertFalse(AgentEnrollment.objects.exists())
        self.assertRedirects(
            self.client.get("/downloads/windows/", {"setup": "windows", "organization": self.a.slug}),
            self.url("agent-fleets"),
        )

    @override_settings(PUBLIC_BASE_URL="https://testserver")
    def test_windows_code_binds_first_signing_key_and_rejects_other_devices(self):
        grant, token = agents.create_enrollment(self.admin, self.a, self.asset, "", claim_key_on_redeem=True)
        self.assertEqual(grant.public_key, "")

        request = {
            "schema": "bearings.agent.enroll.windows.v1",
            "request_id": str(uuid.uuid4()),
            "public_key": self.public,
        }
        target = "/api/v1/agent/enroll/"
        identity = "enroll:" + str(grant.pk)
        headers = {"Authorization": "Bearer " + token}
        attacker = client.Ed25519PrivateKey.generate()
        self.assertEqual(
            self.post(target, request, key=attacker, identity=identity, headers=headers).status_code, 403
        )
        grant.refresh_from_db()
        self.assertIsNone(grant.used_at)
        accepted = self.post(target, request, identity=identity, headers=headers)
        self.assertEqual(accepted.status_code, 200, accepted.content)
        retry = self.post(target, request, identity=identity, headers=headers)
        self.assertEqual(retry.json(), accepted.json())
        competing = {
            **request,
            "public_key": base64.b64encode(attacker.public_key().public_bytes_raw()).decode(),
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(
            self.post(target, competing, key=attacker, identity=identity, headers=headers).status_code, 403
        )
        grant.refresh_from_db()
        self.assertEqual(grant.public_key, self.public)

    @override_settings(PUBLIC_BASE_URL="https://testserver")
    def test_linux_rollout_key_registers_a_new_windows_host_and_accepts_inventory(self):
        fleet, token = agent_fleets.create(self.admin, self.a, "Synthetic rollout", "desktop", max_devices=1)
        host = "synthetic-windows"
        request = {
            "schema": "bearings.agent.bootstrap.v1",
            "public_key": self.public,
            "request_id": str(uuid.uuid4()),
        }
        bootstrap = self.post(
            "/api/v1/agent/bootstrap/",
            request,
            identity="fleet:" + str(fleet.pk),
            headers={"Authorization": "Bearer " + token},
        )
        self.assertEqual(bootstrap.status_code, 200, bootstrap.content)
        self.assertFalse(Asset.objects.filter(organization=self.a, name=host).exists())
        grant = bootstrap.json()
        self.assertTrue(grant["register_host"])
        self.assertEqual(grant["asset_id"], "")
        enrollment_token = grant["grant"]
        response = self.post(
            "/api/v1/agent/enroll/",
            {
                "schema": "bearings.agent.enroll.v1",
                "request_id": str(uuid.uuid4()),
                "host": {"hostname": host, "addresses": []},
            },
            identity="enroll:" + enrollment_token.split(".")[0],
            headers={"Authorization": "Bearer " + enrollment_token},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.device = AgentDevice.objects.get(pk=response.json()["device_id"])
        self.assertEqual(self.device.asset.name, host)
        self.assertEqual(self.device.asset.kind, "desktop")
        self.assertEqual(self.device.source_id, self.sa.pk)
        self.assertNotEqual(self.device.asset_id, self.asset.pk)
        self.assertTrue(self.device.asset.upstream_data["agent_observed_only"])
        accepted = self.send(observation())
        self.assertEqual(accepted.status_code, 202, accepted.content)
        agents.process_one(self.device.pk, accepted.json()["report_id"])
        self.assertTrue(self.device.components.filter(key="win-reg:os:all").exists())

    def test_windows_downloads_require_complete_release_and_matching_checksum(self):
        base = "/downloads/windows/"
        artifact = "bearings-windows-x64.zip"
        source = "bearings-windows-source.zip"
        filenames = (artifact, "bearings-windows-arm64.zip", "bearings-windows-x86.zip", source)
        with TemporaryDirectory() as directory, override_settings(WINDOWS_CLIENT_DOWNLOAD_DIR=directory):
            root = Path(directory)
            content = {name: f"Synthetic fixture for {name}".encode() for name in filenames}
            for name, body in content.items():
                (root / name).write_bytes(body)
                (root / name).chmod(0o644)
            manifest = "".join(
                f"{hashlib.sha256(body).hexdigest()}  {name}\n" for name, body in content.items()
            )
            (root / "SHA256SUMS").write_text(manifest, encoding="ascii")
            (root / "SHA256SUMS").chmod(0o644)

            self.assertContains(self.client.get(base), f'href="{base}{artifact}"')
            with override_settings(PUBLIC_BASE_URL="https://bearings.test"):
                page = self.client.get(base)
                self.assertContains(page, "Download from this Bearings server in PowerShell")
                self.assertContains(page, f"https://bearings.test{base}{artifact}")
            for name, body in content.items():
                response = self.client.get(base + name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Disposition"], f'attachment; filename="{name}"')
                self.assertEqual(response["Cache-Control"], "no-store")
                self.assertEqual(b"".join(response.streaming_content), body)
            self.assertEqual(self.client.get(base + "README.md").status_code, 404)
            self.assertEqual(self.client.get(base + "bearings-windows-x64.exe").status_code, 404)

            (root / artifact).write_bytes(b"changed")
            self.assertEqual(self.client.get(base + artifact).status_code, 404)
            (root / source).rename(root / "outside.zip")
            (root / source).symlink_to(root / "outside.zip")
            self.assertNotContains(self.client.get(base), f'href="{base}{artifact}"')
            self.assertEqual(self.client.get(base + "bearings-windows-arm64.zip").status_code, 404)

    def test_signed_update_manifest_requires_complete_immutable_checksummed_release(self):
        from portal.client_downloads import WINDOWS_ARTIFACTS

        base = "/downloads/windows/"
        with TemporaryDirectory() as directory, override_settings(WINDOWS_CLIENT_DOWNLOAD_DIR=directory):
            root = Path(directory)
            contents = {name: b"synthetic package" for name in WINDOWS_ARTIFACTS if name != "SHA256SUMS"}
            contents["update.json"] = b'{"synthetic":"signed envelope"}'
            for name, body in contents.items():
                (root / name).write_bytes(body)
                (root / name).chmod(0o644)
            sums = "".join(f"{hashlib.sha256(body).hexdigest()}  {name}\n" for name, body in contents.items())
            (root / "SHA256SUMS").write_text(sums)
            (root / "SHA256SUMS").chmod(0o644)
            response = self.client.get(base + "update.json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(b"".join(response.streaming_content), contents["update.json"])
            (root / "update.json").write_bytes(b"tampered")
            self.assertEqual(self.client.get(base + "update.json").status_code, 404)
            (root / "update.json").write_bytes(contents["update.json"])
            (root / "update.json").chmod(0o666)
            self.assertEqual(self.client.get(base + "update.json").status_code, 404)
            (root / "update.json").chmod(0o644)
            (root / "bearings-windows-source.zip").unlink()
            self.assertEqual(self.client.get(base + "update.json").status_code, 404)

    def test_collector_and_own_signature_verified_by_independent_receiver(self):
        self.enroll()
        data = observation()
        raw = client.packed(data)
        headers = client.headers(
            self.key, "device:" + str(self.device.pk), "https://testserver", "/api/v1/agent/reports/", raw
        )
        response = self.machine.post(
            "/api/v1/agent/reports/",
            raw,
            content_type="application/json",
            secure=True,
            headers={k: v for k, v in headers.items() if k != "Content-Type"},
        )
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_one(self.device.pk, response.json()["report_id"])
        self.device.refresh_from_db()
        self.assertEqual(self.device.os["version"], "26100.1234")
        self.assertIsNotNone(self.device.last_complete_at)
        components = self.device.components.all()
        self.assertEqual(components.count(), 4)
        self.assertEqual(
            Installation.objects.filter(asset=self.asset, agent_component__device=self.device).count(), 4
        )
        os_install = Installation.objects.get(asset=self.asset, agent_component__key="win-reg:os:all")
        self.assertTrue(os_install.is_operating_system)
        self.assertEqual(os_install.version, "26100.1234")
        unknown = components.get(name="Version inconnue – Werkzeug")
        self.assertEqual(unknown.version, "")
        self.assertEqual(unknown.installation.version, "")
        self.assertTrue(
            unknown.installation.product.identifier.startswith("pkg:generic/windows-registration/")
        )
        self.assertEqual(unknown.windows["view"], "32")

    def test_host_overview_shows_windows_inventory_without_package_evaluation(self):
        self.enroll()
        response = self.send(observation())
        self.assertEqual(response.status_code, 202)
        agents.process_one(self.device.pk, response.json()["report_id"])
        self.assertEqual(distro_cves.evaluate_device(self.device.pk)["state"], "unsupported")

        self.login(self.reader)
        response = self.client.get(self.url("organization-hosts"))
        self.assertContains(response, "Windows 26100.1234")
        self.assertContains(response, "No current package evaluation")
        hosts = response.context["host_page"]
        host = next(row for row in hosts if row.pk == self.asset.pk)
        self.assertIsNotNone(host.report_time)
        self.assertFalse(host.evaluated)
        self.assertIsNone(host.fix_packages)
        self.assertNotIn(self.other.pk, [row.pk for row in hosts])

    def test_strict_windows_scope_identity_build_and_no_runtime_claim(self):
        good = observation()
        agent_protocol.report_data(good)
        mutations = [
            lambda d: d.update(scope="system-packages"),
            lambda d: d["os"].update(id="ubuntu"),
            lambda d: d["os"].update(version="10.0"),
            lambda d: d["os"].update(reboot_hint="not_observed"),
            lambda d: d["components"][0].update(key="win-reg:guessed:all"),
            lambda d: d["components"][0]["windows"].update(view="user"),
            lambda d: d["components"].append(deepcopy(d["components"][0])),
            lambda d: d.update(
                services=[dict(name="nginx", state="not_running", coverage="main_process_only")]
            ),
            lambda d: d["components"][0].update(version=None),
            lambda d: d["components"][0]["windows"].update(registry_key=r"SOFTWARE\Other"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = deepcopy(good)
                mutate(data)
                with self.assertRaises(ValueError):
                    agent_protocol.report_data(data)

    def test_missing_and_version_change_retain_evidence_and_manual_installations(self):
        self.enroll()
        data = observation()
        response = self.send(data)
        self.assertEqual(response.status_code, 202)
        agents.process_one(self.device.pk, response.json()["report_id"])
        original = self.device.components.exclude(key="win-reg:os:all").first()
        install_id = original.installation_id
        self.relax()
        updated = observation()
        updated.update(report_id=str(uuid.uuid4()), sequence=2)
        updated["components"] = [c for c in updated["components"] if c["key"] != original.key]
        response = self.send(updated)
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_one(self.device.pk, response.json()["report_id"])
        original.refresh_from_db()
        self.assertIsNotNone(original.missing_since)
        self.assertEqual(original.installation_id, install_id)
        self.assertTrue(Installation.objects.filter(pk=install_id).exists())
        self.assertEqual(AgentReport.objects.filter(device=self.device, status="applied").count(), 2)
        self.relax()
        updated = observation()
        updated["sequence"] = 3
        next(c for c in updated["components"] if c["key"] == original.key)["version"] = "3.0"
        response = self.send(updated)
        agents.process_one(self.device.pk, response.json()["report_id"])
        original.refresh_from_db()
        self.assertIsNone(original.missing_since)
        original.installation.refresh_from_db()
        self.assertEqual(original.installation.version, "3.0")
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "")
        self.assertFalse(hasattr(self.installation, "agent_component"))
        agents.revoke(self.admin, self.a, self.device.pk)
        self.relax()
        updated["sequence"] = 4
        self.assertEqual(self.send(updated).status_code, 403)

    def test_client_outbox_keeps_identical_bytes_on_failure_and_checks_exact_receipt(self):
        self.enroll()
        store = MemoryStore(
            self.key.private_bytes_raw(),
            device_id=str(self.device.pk),
            url="https://testserver",
            expires_at=(timezone.now() + timedelta(days=1)).isoformat(),
        )
        client.enqueue(store, observation())
        queued = store.saved["queue"][0]
        with patch.object(client, "send", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                client.flush(store)
        self.assertEqual(store.saved["queue"], [queued])
        report = json.loads(queued)
        ack = dict(
            schema="bearings.agent.receipt.v1",
            report_id=report["report_id"],
            sequence=1,
            status="pending",
            body_sha256="wrong",
        )
        with patch.object(client, "send", return_value=ack):
            with self.assertRaises(ValueError):
                client.flush(store)
        self.assertEqual(store.saved["queue"], [queued])
        ack["body_sha256"] = hashlib.sha256(queued.encode()).hexdigest()
        with patch.object(client, "send", return_value=ack) as delivery:
            client.flush(store)
        self.assertEqual(delivery.call_args.args[2], queued.encode())
        self.assertEqual(store.saved["queue"], [])

    def test_client_enrollment_lost_ack_reuses_request_and_checks_asset(self):
        grant, token = agents.create_enrollment(self.admin, self.a, self.asset, self.public)
        from .agent_enrollment_codes import payload
        from django.test import override_settings

        with override_settings(PUBLIC_BASE_URL="https://testserver"):
            value = payload(grant, token)
        store = MemoryStore(self.key.private_bytes_raw())
        with patch.object(client, "send", side_effect=OSError("lost")):
            with self.assertRaises(OSError):
                client.enroll(store, value, None)
        pending = deepcopy(store.saved["pending"])
        ack = dict(
            schema="bearings.agent.enrolled.v1",
            device_id=str(uuid.uuid4()),
            asset_id=str(self.asset.pk),
            expires_at=(timezone.now() + timedelta(days=90)).isoformat(),
        )
        with patch.object(client, "send", return_value=ack) as delivery:
            client.enroll(store, value, None)
        self.assertEqual(json.loads(delivery.call_args.args[2]), pending["body"])
        self.assertNotIn("pending", store.saved)

    def test_incomplete_registry_access_fails_collection_without_partial_report(self):
        registry = Registry()
        with (
            patch.object(client, "native_architecture", return_value="x86_64"),
            patch.object(registry, "OpenKey", side_effect=PermissionError("denied")),
        ):
            with self.assertRaises(PermissionError):
                client.collect(registry)
        for endpoint in (
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/path",
        ):
            with self.assertRaises(ValueError):
                client.origin(endpoint)
        self.assertEqual(client.origin("https://Example.COM:443/"), "https://example.com")

    def test_registry_changes_detected_before_returning_complete_scope(self):
        registry = Registry()
        enumerate_key = registry.EnumKey

        def add_registration(key, index):
            item = enumerate_key(key, index)
            key.append("Concurrent registration")
            return item

        with (
            patch.object(client, "native_architecture", return_value="x86_64"),
            patch.object(registry, "EnumKey", side_effect=add_registration),
            self.assertRaisesRegex(ValueError, "registry changed"),
        ):
            client.collect(registry)

    def test_periodic_reports_keep_complete_samples_when_https_is_offline(self):
        self.enroll()
        samples = [observation(), observation()]
        store = MemoryStore(
            self.key.private_bytes_raw(),
            device_id=str(self.device.pk),
            expires_at=(timezone.now() + timedelta(days=1)).isoformat(),
        )
        with (
            patch.object(client, "collect", side_effect=samples),
            patch.object(client, "send", side_effect=OSError("offline")),
        ):
            for sequence in (1, 2):
                with self.assertRaises(OSError):
                    client.report_now(store)
                self.assertEqual(len(store.saved["queue"]), sequence)
                self.assertEqual(json.loads(store.saved["queue"][-1])["sequence"], sequence)

    def test_changed_publisher_preserves_version_until_explicit_ownership_review(self):
        self.enroll()
        data = observation()
        response = self.send(data)
        agents.process_one(self.device.pk, response.json()["report_id"])
        original = self.device.components.get(name="Example Tools (64-bit)")
        os_component = self.device.components.get(key="win-reg:os:all")
        agents.detach(self.admin, self.a, os_component.pk)
        with self.assertRaisesMessage(agents.ValidationError, "matching operating-system classification"):
            agents.bind(self.admin, self.a, os_component.pk, self.installation.pk)
        self.relax()
        data = observation()
        data["sequence"] = 2
        switched = next(c for c in data["components"] if c["key"] == original.key)
        switched["windows"]["publisher"] = "Different publisher"
        switched["version"] = "5.0"
        response = self.send(data)
        self.assertEqual(response.status_code, 202)
        agents.process_pending()
        self.assertEqual(AgentReport.objects.get(pk=data["report_id"]).status, "rejected")
        original.refresh_from_db()
        self.assertEqual(original.installation.version, "2.1")


@override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"], DEBUG=False)
class WindowsTransportTests(TransactionTestCase):
    """Real Windows-protocol HTTPS transport and PostgreSQL with synthetic collector input."""

    setUp = test_agent_client.AgentClientTests.setUp
    shutdown = test_agent_client.AgentClientTests.shutdown

    def test_verified_https_enrollment_report_status_and_revocation(self):
        key = client.Ed25519PrivateKey.generate()
        store = MemoryStore(key.private_bytes_raw())
        grant, token = agents.create_enrollment(self.admin, self.org, self.asset, client.public(store.data))
        from .agent_enrollment_codes import payload

        with override_settings(PUBLIC_BASE_URL=self.origin):
            value = payload(grant, token)
        result = client.enroll(store, value, str(self.ca))
        self.assertEqual(result["asset_id"], str(self.asset.pk))
        client.enqueue(store, observation())
        result = client.flush(store)
        self.assertEqual(result["status"], "pending")
        agents.process_one(
            result_device := result.get("device_id", store.data["device_id"]), result["report_id"]
        )
        status = client.send(
            store.data,
            "/api/v1/agent/status/",
            client.packed(dict(schema="bearings.agent.status.v1", report_id=result["report_id"])),
        )
        self.assertEqual(status["status"], "applied")
        self.assertEqual(Installation.objects.filter(asset=self.asset).count(), 4)
        agents.revoke(self.admin, self.org, result_device)
        with self.assertRaises(ValueError):
            client.send(
                store.data,
                "/api/v1/agent/status/",
                client.packed(dict(schema="bearings.agent.status.v1", report_id=result["report_id"])),
            )

    def test_untrusted_certificate_keeps_pending_enrollment(self):
        key = client.Ed25519PrivateKey.generate()
        store = MemoryStore(key.private_bytes_raw())
        grant, token = agents.create_enrollment(self.admin, self.org, self.asset, client.public(store.data))
        from .agent_enrollment_codes import payload
        import ssl

        with override_settings(PUBLIC_BASE_URL=self.origin):
            value = payload(grant, token)
        with self.assertRaises(ssl.SSLError):
            client.enroll(store, value, None)
        self.assertIn("pending", store.saved)
        self.assertNotIn("device_id", store.saved)
        result = client.enroll(store, value, self.ca)
        self.assertEqual(result["asset_id"], str(self.asset.pk))
