"""macOS wire, publication and download contracts with synthetic data."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import override_settings

from . import agents, test_agents
from .agent_protocol import report_data
from .models import Installation
from .tests import Fixture


class MacOSAgentTests(Fixture):
    legacy_manual_projection = False
    setUp = test_agents.AgentTests.setUp
    post = test_agents.AgentTests.post
    enroll = test_agents.AgentTests.enroll
    relax = test_agents.AgentTests.relax
    send = test_agents.AgentTests.send

    def mac_report(self, sequence=1):
        report = test_agents.AgentTests.data(self, sequence)
        report.update(
            scope="macos-machine",
            os={
                "id": "macos",
                "version": "15.7.2",
                "build": "24G325",
                "architecture": "arm64",
                "kernel": "24.6.0",
                "kernel_scope": "host",
                "reboot_hint": "unknown",
            },
            services=[],
            components=[
                self.component("mac-app:os", "macOS", "15.7.2"),
                self.component("mac-app:bundle:com.example.Tool:" + "a" * 64, "Example", "4.2"),
                self.component("mac-app:receipt:com.example.pkg", "com.example.pkg", ""),
                self.component("mac-app:brew:python@3.12:" + "1" * 64, "python@3.12", "3.12.1"),
            ],
            gaps=[],
        )
        return report

    @staticmethod
    def component(key, name, version):
        return {
            "key": key,
            "manager": "mac-app",
            "name": name,
            "architecture": "all",
            "version": version,
        }

    def test_signed_macos_snapshot_projection_and_compact_check(self):
        self.enroll()
        first = self.mac_report()
        response = self.send(first)
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_pending()
        self.device.refresh_from_db()
        self.assertEqual(str(self.device.inventory_baseline_id), first["report_id"])
        self.assertEqual(self.device.os["build"], "24G325")
        system = Installation.objects.get(asset=self.asset, product__name="macOS")
        self.assertTrue(system.is_operating_system)
        self.assertEqual(system.version, "15.7.2")
        self.assertTrue(Installation.objects.filter(asset=self.asset, product__name="Example", version="4.2"))
        self.assertTrue(
            Installation.objects.filter(asset=self.asset, product__name="com.example.pkg", version="")
        )

        self.relax()
        compact = test_agents.AgentTests.inventory_check(self, 2, baseline=first["report_id"])
        response = self.send(compact)
        self.assertIn(response.status_code, (200, 202), response.content)
        self.assertEqual(response.json()["status"], "applied")

        self.relax()
        incomplete = self.mac_report(3)
        del incomplete["gaps"]
        incomplete["complete"] = False
        incomplete["components"] = incomplete["components"][:1]
        response = self.send(incomplete)
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_pending()
        self.device.refresh_from_db()
        self.assertIsNone(self.device.inventory_baseline_id)
        self.assertEqual(self.device.inventory_capture_gaps, ["packages"])
        self.assertFalse(self.device.components.filter(missing_since__isnull=False).exists())

        self.relax()
        reduced = self.mac_report(4)
        reduced["components"] = reduced["components"][:1]
        self.assertEqual(self.send(reduced).status_code, 202)
        agents.process_pending()
        self.assertEqual(self.device.components.filter(missing_since__isnull=False).count(), 3)

    def test_macos_scope_refuses_inconsistent_os_and_component_identity(self):
        report = self.mac_report()
        report["components"][0]["version"] = "15.6"
        with self.assertRaises(ValueError):
            report_data(report)
        report = self.mac_report()
        report["scope"] = "system-packages"
        with self.assertRaises(ValueError):
            report_data(report)

    def test_download_page_and_verified_artifacts(self):
        from .client_downloads import MACOS_ARTIFACTS

        self.login(self.admin)
        self.assertContains(self.client.get("/downloads/?organization=alpha"), "macOS")
        with TemporaryDirectory() as directory, override_settings(MACOS_CLIENT_DOWNLOAD_DIR=directory):
            url = "/downloads/macos/bearings-macos-arm64.zip"
            self.assertNotContains(self.client.get("/downloads/macos/"), url)
            self.assertEqual(self.client.get(url).status_code, 404)
            records = []
            for name in MACOS_ARTIFACTS.keys() - {"SHA256SUMS"}:
                body = ("synthetic payload for " + name).encode()
                Path(directory, name).write_bytes(body)
                records.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
            Path(directory, "SHA256SUMS").write_text("\n".join(records) + "\n")
            self.assertContains(self.client.get("/downloads/macos/"), url)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"synthetic payload", b"".join(response.streaming_content))
            Path(directory, "bearings-macos-arm64.zip").write_text("modified")
            self.assertEqual(self.client.get(url).status_code, 404)
