"""Synthetic WUA snapshots through signed admission; no online Windows scan."""

from copy import deepcopy
from datetime import timedelta
import uuid

from django.test import SimpleTestCase
from django.utils import timezone

from . import agent_protocol, agents, windows_updates
from .models import AgentDevice, AgentReport
from .tests import Fixture
from . import test_windows_agent


def snapshot():
    entry = {
        "id": "11111111-1111-4111-8111-111111111111",
        "revision": 2,
        "title": "Synthetic security update <script>unsafe()</script>",
        "kbs": ["KB5000001"],
        "hidden": False,
    }
    return {
        "source": "windows-update-agent-cache",
        "cache_last_search_at": timezone.now().isoformat(),
        "reboot": "present",
        "installed": {"status": "ok", "total": 1, "truncated": False, "updates": [entry]},
        "pending": {"status": "ok", "total": 0, "truncated": False, "updates": []},
    }


class WindowsUpdateValidation(SimpleTestCase):
    def test_empty_cache_partial_failures_and_unknown_cache_age_are_independent(self):
        value = snapshot()
        windows_updates.validate(value, timezone.now())
        value["cache_last_search_at"] = ""
        value["installed"].update(status="partial", total=1000, truncated=True)
        value["pending"].update(status="timeout", total=None)
        windows_updates.validate(value, timezone.now())

    def test_bounds_counts_types_ids_and_server_owned_receipts_are_enforced(self):
        variants = []
        for key, bad in (
            ("status", "safe"),
            ("total", True),
            ("total", -1),
            ("total", 100001),
            ("truncated", True),
            ("updates", None),
            ("status", "error"),
        ):
            s = snapshot()
            s["installed"][key] = bad
            variants.append(s)
        for key, bad in (
            ("id", "wrong"),
            ("revision", True),
            ("revision", 0),
            ("kbs", ['KB1234" onclick="bad']),
            ("hidden", "false"),
            ("title", "x" * 241),
            ("kbs", ["KB5000001", "KB5000001"]),
        ):
            s = snapshot()
            s["installed"]["updates"][0][key] = bad
            variants.append(s)
        s = snapshot()
        s["installed"]["updates"] *= 2
        s["installed"]["total"] = 2
        variants.append(s)
        s = snapshot()
        s["installed"]["updates"] *= 251
        s["installed"]["total"] = 251
        variants.append(s)
        for key, bad in (
            ("cache_last_search_at", "2026-01-01T00:00:00"),
            ("cache_last_search_at", "2099-01-01T00:00:00Z"),
            ("reboot", "up-to-date"),
            ("last_success", {}),
        ):
            s = snapshot()
            s[key] = bad
            variants.append(s)
        for value in variants:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                windows_updates.validate(value, timezone.now())

    def test_linux_cannot_claim_windows_update_evidence_and_reboot_must_agree(self):
        data = test_windows_agent.observation()
        data["os"]["windows_update"] = snapshot()
        with self.assertRaises(ValueError):  # Legacy unknown reboot conflicts with observed present.
            agent_protocol.report_data(data)
        data["os"]["reboot_hint"] = "present"
        agent_protocol.report_data(data)
        data["os"]["id"] = "ubuntu"
        with self.assertRaises(ValueError):
            agent_protocol.report_data(data)


class WindowsUpdateReceipts(Fixture):
    legacy_manual_projection = False
    setUp = test_windows_agent.WindowsAgentTests.setUp
    enroll = test_windows_agent.WindowsAgentTests.enroll
    post = test_windows_agent.WindowsAgentTests.post
    send = test_windows_agent.WindowsAgentTests.send
    relax = test_windows_agent.WindowsAgentTests.relax

    def publish(self, sequence=1, updates=True, version="26100.1234"):
        data = test_windows_agent.observation()
        data.update(sequence=sequence, report_id=str(uuid.uuid4()), observed_at=timezone.now().isoformat())
        data["os"].update(version=version, kernel=version)
        for c in data["components"]:
            if c["windows"]["kind"] == "os":
                c["version"] = version
        if updates is not False:
            data["os"]["windows_update"] = deepcopy(updates if isinstance(updates, dict) else snapshot())
            data["os"]["reboot_hint"] = data["os"]["windows_update"]["reboot"]
        if sequence > 1:
            self.relax()
        response = self.send(data)
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_one(self.device.pk, response.json()["report_id"])
        self.device.refresh_from_db()
        self.assertEqual(AgentReport.objects.get(pk=response.json()["report_id"]).status, "applied")
        return data

    def test_signed_kbs_pending_cache_age_restart_and_escaped_scoped_pages(self):
        self.enroll()
        self.publish()
        receipt = self.device.os["windows_update"]
        self.assertEqual(receipt["installed"]["updates"][0]["kbs"], ["KB5000001"])
        self.assertEqual(receipt["pending"]["total"], 0)
        self.assertEqual(receipt["last_success"]["reboot"]["data"], "present")
        self.login(self.reader)
        for url in (
            self.url("agent-center") + "?device=" + str(self.device.pk),
            self.url("asset", pk=self.asset.pk),
        ):
            page = self.client.get(url)
            self.assertContains(page, "Windows Update")
            self.assertContains(page, "KB5000001")
            self.assertContains(page, "support.microsoft.com/help/5000001")
            self.assertContains(page, "present")
            self.assertContains(page, "does not prove that Windows is fully updated")
            self.assertNotContains(page, "<script>unsafe()")
            self.assertContains(page, "&lt;script&gt;unsafe()")
        self.assertEqual(
            self.client.get(self.url("agent-center", self.b) + "?device=" + str(self.device.pk)).status_code,
            404,
        )

    def test_asset_prioritizes_pending_updates_before_connection_and_keeps_stale_counts(self):
        from .test_package_verdicts import save_browser_evidence

        self.enroll()
        value = snapshot()
        value["pending"].update(total=1, updates=value["installed"]["updates"])
        self.publish(updates=value)
        self.login(self.reader)
        url = self.url("asset", pk=self.asset.pk)
        page = self.client.get(url)
        self.assertContains(page, "1 pending update")
        self.assertContains(page, 'aria-label="Cache query completed.')
        self.assertNotContains(page, "Query status:")
        self.assertLess(
            page.content.index(b"1 pending update"), page.content.index(b"Inventory synchronization")
        )
        save_browser_evidence("asset-attention-windows", page)
        self.publish(2, False, "26100.2222")
        self.assertContains(self.client.get(url), "1 pending update last recorded")

    def test_failure_and_partial_result_retain_complete_results_without_false_success(self):
        self.enroll()
        self.publish()
        first = deepcopy(self.device.os["windows_update"]["last_success"])
        bad = snapshot()
        bad["reboot"] = "unknown"
        bad["installed"].update(status="error", total=None, updates=[])
        bad["pending"].update(status="partial", total=5, truncated=True)
        self.publish(2, bad)
        receipt = self.device.os["windows_update"]
        self.assertEqual(receipt["last_success"], first)
        self.assertIsNone(receipt["installed"]["total"])
        self.assertEqual(receipt["pending"]["status"], "partial")
        self.login()
        page = self.client.get(self.url("asset", pk=self.asset.pk))
        self.assertContains(page, "Retained complete installed query")
        self.assertContains(page, "Missing results are not zero pending updates")
        self.assertContains(page, "Partial query")

    def test_legacy_report_build_change_staleness_and_revocation_never_refresh_receipt(self):
        self.enroll()
        self.publish()
        before = deepcopy(self.device.os["windows_update"])
        self.publish(2, False, "26100.2222")
        after = self.device.os["windows_update"]
        self.assertEqual(after["observed_at"], before["observed_at"])
        self.assertEqual(after["build"], "26100.1234")
        self.assertFalse(after["included"])
        self.assertTrue(windows_updates.presentation(self.device)["historical"])
        self.publish(3)
        AgentDevice.objects.filter(pk=self.device.pk).update(enabled=False)
        self.device.refresh_from_db()
        self.assertTrue(windows_updates.presentation(self.device)["historical"])
        self.device.enabled = True
        self.device.os["windows_update"]["observed_at"] = (timezone.now() - timedelta(days=2)).isoformat()
        self.assertTrue(windows_updates.presentation(self.device)["historical"])

    def test_old_client_no_update_data_stays_unknown_and_does_not_invent_receipts(self):
        self.enroll()
        self.publish(updates=False)
        self.assertNotIn("windows_update", self.device.os)
        self.login()
        self.assertContains(
            self.client.get(self.url("asset", pk=self.asset.pk)), "No Windows Update observation"
        )

    def test_empty_cache_is_not_current_when_cache_time_unknown_and_source_binding_changed(self):
        self.enroll()
        value = snapshot()
        value["cache_last_search_at"] = ""
        self.publish(updates=value)
        self.assertTrue(windows_updates.presentation(self.device)["cache_outdated"])
        self.device.source = self.sb
        self.assertTrue(windows_updates.presentation(self.device)["historical"])
