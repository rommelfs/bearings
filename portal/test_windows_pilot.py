"""Synthetic ARM64/x64 pilot contracts; no real machine inventory is published."""

from datetime import date, timedelta
from io import StringIO
import json
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase
from django.utils import timezone

from . import windows_pilot as pilot
from .models import AgentComponent, AgentDevice, AgentReport
from . import test_windows_agent, test_windows_cves
from .test_windows_updates import snapshot
from .tests import Fixture


class PilotIdentity(SimpleTestCase):
    def component(self, version="22621.1234", **facts):
        return SimpleNamespace(
            name="Synthetic name deliberately not used",
            version=version,
            windows={
                "kind": "os",
                "installation_type": "Client",
                "edition": "Professional",
                "release": "22H2",
                **facts,
            },
        )

    def os(self, c, architecture="arm64"):
        return {"id": "windows", "version": c.version, "kernel": c.version, "architecture": architecture}

    def test_native_architecture_and_release_have_distinct_reviewed_product_ids(self):
        for release, build, ids in (
            ("22H2", "22621", ("12085", "12086")),
            ("24H2", "26100", ("12389", "12390")),
            ("25H2", "26200", ("20437", "20438")),
        ):
            for arch, product_id in zip(("arm64", "x86_64"), ids):
                c = self.component(build + ".1234", release=release)
                result = pilot.identity(c, self.os(c, arch))
                self.assertEqual(result["product"]["id"], product_id)
                self.assertIn("Windows 11", result["product"]["name"])

    def test_ambiguous_server_ltsc_architecture_and_missing_revision_do_not_map(self):
        for c, arch in (
            (self.component("22621"), "arm64"),
            (self.component("22621.invalid"), "arm64"),
            (self.component(release="23H2"), "arm64"),
            (self.component(installation_type=""), "arm64"),
            (self.component(edition="Unknown"), "arm64"),
            (self.component(edition="EnterpriseS"), "arm64"),
            (
                self.component(
                    "26100.1234", release="24H2", installation_type="Server", edition="ServerDatacenter"
                ),
                "x86_64",
            ),
            (self.component(), "x86"),
        ):
            with self.subTest(c=c, arch=arch):
                self.assertIsNone(pilot.identity(c, self.os(c, arch))["product"])
        c = self.component()
        self.assertIsNone(pilot.identity(c, {**self.os(c), "kernel": "22621.9999"})["product"])

    def test_support_period_is_edition_specific_and_never_a_patch_verdict(self):
        c = self.component()
        self.assertEqual(
            pilot.identity(c, self.os(c), today=date(2024, 10, 8))["lifecycle"]["state"],
            "within_reviewed_support_period",
        )
        self.assertEqual(
            pilot.identity(c, self.os(c), today=date(2024, 10, 9))["lifecycle"]["state"], "out_of_support"
        )
        c.windows["edition"] = "Enterprise"
        self.assertEqual(pilot.identity(c, self.os(c))["lifecycle"]["state"], "not_established")


class PilotObservation(Fixture):
    legacy_manual_projection = False
    setUp = test_windows_agent.WindowsAgentTests.setUp
    enroll = test_windows_agent.WindowsAgentTests.enroll
    post = test_windows_agent.WindowsAgentTests.post
    send = test_windows_agent.WindowsAgentTests.send
    relax = test_windows_agent.WindowsAgentTests.relax
    publish = test_windows_cves.WindowsDiscovery.publish

    def prepare(self):
        self.enroll()
        self.data = test_windows_agent.observation()
        self.data["os"].update(
            architecture="arm64",
            version="22621.1234",
            kernel="22621.1234",
            reboot_hint="present",
            windows_update=snapshot(),
        )
        for c in self.data["components"]:
            if c["windows"]["kind"] == "os":
                c.update(version="22621.1234")
                c["windows"].update(installation_type="Client", release="22H2")
        self.publish(self.data)
        self.component = AgentComponent.objects.get(device=self.device, windows__kind="os")

    def inspect(self, user=None):
        return pilot.inspect(user or self.reader, self.a.slug, self.device.pk)

    def test_signed_arm64_report_exports_traceable_scoped_metadata_without_names(self):
        self.prepare()
        with patch("portal.connectors.http.request_json", side_effect=AssertionError("No pilot egress")):
            result = self.inspect()
            self.assertEqual(result["fingerprint"], self.inspect()["fingerprint"])
        self.assertEqual(result["product"]["id"], "12085")
        self.assertEqual(result["lifecycle"]["state"], "out_of_support")
        self.assertTrue(result["observation"]["current"])
        self.assertEqual(result["update_line"], "unknown")
        self.assertEqual(result["cve_compliance"], "not_established")
        self.assertEqual(result["windows_update"]["groups"][0]["kbs"], ["KB5000001"])
        text = json.dumps(result)
        self.assertNotIn(self.asset.name, text)
        self.assertNotIn(self.device.public_key, text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("signature", text)

    def test_failed_new_report_does_not_promote_last_successful_update_rows(self):
        self.prepare()
        old = self.inspect()["fingerprint"]
        self.relax()
        self.data.update(sequence=2, report_id=str(uuid.uuid4()), observed_at=timezone.now().isoformat())
        self.data["os"]["windows_update"]["installed"].update(status="timeout", total=None, updates=[])
        self.publish(self.data)
        result = self.inspect()
        self.assertNotEqual(result["fingerprint"], old)
        self.assertEqual(result["windows_update"]["groups"][0]["status"], "timeout")
        self.assertEqual(result["windows_update"]["groups"][0]["kbs"], [])
        self.assertNotIn("KB5000001", json.dumps(result))

    def test_legacy_report_does_not_reuse_retained_update_success(self):
        self.prepare()
        self.relax()
        self.data.update(sequence=2, report_id=str(uuid.uuid4()), observed_at=timezone.now().isoformat())
        del self.data["os"]["windows_update"]
        self.data["os"]["reboot_hint"] = "unknown"
        self.publish(self.data)
        result = self.inspect()
        self.assertTrue(result["observation"]["current"])
        self.assertIsNone(result["windows_update"])
        self.assertNotIn("KB5000001", json.dumps(result))
        self.assertTrue(any("no Windows Update" in gap for gap in result["gaps"]))

    def test_revoked_or_stale_reports_are_retained_without_currentness(self):
        self.prepare()
        AgentDevice.objects.filter(pk=self.device.pk).update(enabled=False)
        self.assertFalse(self.inspect()["observation"]["current"])
        AgentDevice.objects.filter(pk=self.device.pk).update(
            enabled=True, last_observed_at=timezone.now() - timedelta(days=1)
        )
        self.assertFalse(self.inspect()["observation"]["current"])

    def test_cross_company_source_and_report_bindings_are_denied(self):
        self.prepare()
        with self.assertRaises(ObjectDoesNotExist):
            pilot.inspect(self.reader, self.b.slug, self.device.pk)
        AgentDevice.objects.filter(pk=self.device.pk).update(source=self.sb)
        with self.assertRaises(PermissionDenied):
            self.inspect()
        AgentDevice.objects.filter(pk=self.device.pk).update(source=self.sa)
        # Even an otherwise local component cannot use another device's report.
        other_device = AgentDevice.objects.create(
            organization=self.b,
            asset=self.other,
            source=self.sb,
            public_key="synthetic-different-key",
            expires_at=timezone.now() + timedelta(days=1),
        )
        AgentReport.objects.filter(pk=self.component.last_report_id).update(device=other_device)
        with self.assertRaises(PermissionDenied):
            self.inspect()

    def test_retained_body_or_projection_changes_fail_closed(self):
        self.prepare()
        AgentComponent.objects.filter(pk=self.component.pk).update(version="22621.9999")
        with self.assertRaises(ValueError):
            self.inspect()
        AgentComponent.objects.filter(pk=self.component.pk).update(version="22621.1234")
        AgentReport.objects.filter(pk=self.component.last_report_id).update(body=b"{}")
        with self.assertRaises(ValueError):
            self.inspect()

    def test_command_requires_an_active_scoped_actor_and_only_writes_json(self):
        self.prepare()
        output = StringIO()
        call_command(
            "windows_pilot",
            actor=self.reader.username,
            organization=self.a.slug,
            device=str(self.device.pk),
            stdout=output,
        )
        self.assertEqual(json.loads(output.getvalue())["product"]["id"], "12085")
        self.reader.is_active = False
        self.reader.save(update_fields=["is_active"])
        with self.assertRaises(CommandError):
            call_command(
                "windows_pilot",
                actor=self.reader.username,
                organization=self.a.slug,
                device=str(self.device.pk),
                stdout=StringIO(),
            )
