"""Synthetic registry/advisory contracts; no real host or patch claim."""

import copy
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from . import agent_protocol, agents, discovery, product_matching, windows_cves as windows
from .models import AgentComponent, AgentDevice, DiscoveryMatch, Finding, ProductWatch
from .services import transition_finding
from . import test_windows_agent
from .test_windows_agent import observation
from .tests import Fixture


def os_component(**facts):
    return SimpleNamespace(
        name="Windows 10 Pro",
        version="26100.1000",
        windows={
            "kind": "os",
            "edition": "Professional",
            "release": "24H2",
            "installation_type": "Client",
            "servicing_channel": "gac",
            "update_line": "regular",
            **facts,
        },
    )


def advisory(cpe, low="130.0.0.0", high="130.0.10.0", **item):
    return {
        "cveMetadata": {"cveId": "CVE-2026-99999", "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "references": [
                    {"url": "https://msrc.microsoft.com/update-guide/vulnerability/CVE-2026-99999"}
                ],
                "affected": [
                    {
                        "vendor": "Microsoft",
                        "product": "Microsoft Edge (Chromium-based)",
                        "cpes": [cpe],
                        "versions": [
                            {"version": low, "lessThan": high, "versionType": "custom", "status": "affected"}
                        ],
                        **item,
                    }
                ],
            }
        },
    }


class WindowsRules(SimpleTestCase):
    def test_role_release_edition_and_build_jointly_identify_msrc_product(self):
        os = {"architecture": "x86_64"}
        c = os_component()
        m = windows.resolve(c, os)
        self.assertEqual(m["msrc_product"], "Windows 11 Version 24H2")
        self.assertEqual(m["gaps"], [])  # ProductName deliberately still says Windows 10.
        c.windows.update(
            installation_type="Server Core", edition="ServerDatacenter", servicing_channel="ltsc"
        )
        m = windows.resolve(c, os)
        self.assertEqual(m["msrc_product"], "Windows Server 2025 (Server Core installation)")
        self.assertTrue(any("LTSC" in g for g in m["gaps"]))
        for fact in ({"edition": "Unknown"}, {"release": "23H2"}, {"installation_type": ""}):
            self.assertTrue(windows.resolve(os_component(**fact), os)["gaps"])
        self.assertTrue(windows.resolve(os_component(), {"architecture": "x86"})["gaps"])

    def test_windows_10_11_release_architecture_matrix_and_line_gaps(self):
        for build, (family, release) in windows.CLIENTS.items():
            c = os_component(release=release)
            c.version = build + ".1000"
            for architecture in ("x86_64", "arm64"):
                m = windows.resolve(c, {"architecture": architecture})
                self.assertEqual(m["msrc_product"], f"Windows {family} Version {release}")
            for line in ("", "hotpatch", "esu"):
                c.windows["update_line"] = line
                self.assertTrue(windows.resolve(c, {"architecture": "x86_64"})["gaps"])

    def test_os_comparison_requires_same_branch_architecture_and_explicit_line(self):
        c = os_component()
        m = windows.resolve(c, {"architecture": "x86_64"})
        watch = SimpleNamespace(vendor="microsoft", product_key=m["product_key"])
        i = SimpleNamespace(version=c.version, build="", edition="")
        p = advisory(
            m["cpe"],
            "10.0.26100.0",
            "10.0.26100.1100",
            vendor="Microsoft",
            product=m["msrc_product"],
            platforms=["x64-based Systems"],
        )
        self.assertEqual(windows.evaluate(watch, i, p, m)[0], "potential")
        i.version = "26100.1100"
        self.assertEqual(windows.evaluate(watch, i, p, m)[0], "unknown")
        i.version = c.version
        affected = p["containers"]["cna"]["affected"][0]
        for mutate in (
            {"platforms": ["ARM64-based Systems"]},
            {"product": "Windows Server 2025"},
            {
                "versions": [
                    {
                        "version": "10.0.22631.0",
                        "lessThan": "10.0.26200.1100",
                        "versionType": "custom",
                        "status": "affected",
                    }
                ]
            },
        ):
            modified = copy.deepcopy(p)
            modified["containers"]["cna"]["affected"][0] = {**affected, **mutate}
            self.assertEqual(windows.evaluate(watch, i, modified, m)[0], "unknown")

    def test_application_catalog_refuses_ambiguous_products_and_publisher_substrings(self):
        for name, publisher, gap in (
            ("Microsoft Edge", "Microsoft Corporation", False),
            ("Microsoft Edge", "Fake Microsoft Corporation", True),
            ("Microsoft Edge", "", True),
            ("Microsoft Edge Beta", "Microsoft Corporation", True),
            ("Google Chrome", "Google LLC", False),
            ("7-Zip 24.09 (x64)", "Igor Pavlov", False),
            ("Mozilla Firefox ESR (x64 en-US)", "Mozilla", False),
            ("Mozilla Firefox (x64 en-US)", "Mozilla", True),
            ("Microsoft Edge WebView2 Runtime", "Microsoft Corporation", True),
            ("Microsoft 365 Apps for enterprise", "Microsoft Corporation", True),
            ("Adobe Acrobat Reader DC", "Adobe", True),
        ):
            with self.subTest(name=name, publisher=publisher):
                m = windows.resolve(
                    SimpleNamespace(
                        name=name, version="1.0", windows={"kind": "program", "publisher": publisher}
                    ),
                    {},
                )
                self.assertEqual(bool(m["gaps"]), gap)
                self.assertTrue(m["rule"])

    def test_optional_protocol_fields_preserve_old_clients_and_refuse_unknown_values(self):
        c = next(c for c in observation()["components"] if c["windows"]["kind"] == "os")
        agent_protocol.validate_windows_component(c)
        c["windows"].update(installation_type="Client", servicing_channel="gac", update_line="hotpatch")
        agent_protocol.validate_windows_component(c)
        for field in ("installation_type", "servicing_channel", "update_line"):
            changed = copy.deepcopy(c)
            changed["windows"][field] = "x" * 121 if field == "installation_type" else "arbitrary"
            with self.assertRaises(ValueError):
                agent_protocol.validate_windows_component(changed)


class WindowsDiscovery(Fixture):
    legacy_manual_projection = False
    setUp = test_windows_agent.WindowsAgentTests.setUp
    enroll = test_windows_agent.WindowsAgentTests.enroll
    post = test_windows_agent.WindowsAgentTests.post
    send = test_windows_agent.WindowsAgentTests.send
    relax = test_windows_agent.WindowsAgentTests.relax

    def publish(self, data):
        response = self.send(data)
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_one(self.device.pk, response.json()["report_id"])
        self.assertEqual(self.device.reports.get(pk=response.json()["report_id"]).status, "applied")

    def prepare(self):
        self.enroll()
        data = observation()
        program = data["components"][1]
        program.update(name="Microsoft Edge", version="130.0.1.0")
        program["windows"]["publisher"] = "Microsoft Corporation"
        self.publish(data)
        self.component = AgentComponent.objects.select_related("installation__product").get(
            device=self.device, name="Microsoft Edge"
        )
        self.i = self.component.installation
        self.assertEqual(product_matching.enroll_products(), 1)
        self.watch = ProductWatch.objects.get(product=self.i.product)
        self.payload = advisory(windows.cpe("microsoft", "edge_chromium"))
        return data

    def sync(self):
        with patch(
            "portal.discovery.product_records",
            return_value=(
                self.watch.source_url,
                [("CVE-2026-99999", self.payload)],
            ),
        ):
            return discovery.sync_watch(self.watch.pk)

    def test_signed_inventory_enrolls_curated_watch_with_explainable_immutable_evidence(self):
        self.prepare()
        self.assertTrue(self.i.product.identifier.startswith("pkg:generic/windows-registration/"))
        self.assertEqual(self.sync()["changed"], 1)
        finding = Finding.objects.get(installation=self.i)
        self.assertEqual(finding.applicability, "potential")
        self.assertEqual(finding.analyst_applicability, "unassessed")
        self.assertIn("130.0.1.0", finding.explanation)
        self.assertIn(windows.RULE, finding.explanation)
        self.assertIn("https://msrc.microsoft.com/", finding.explanation)
        match = DiscoveryMatch.objects.get(finding=finding)
        self.assertFalse(match.inputs_changed)
        self.assertEqual(
            match.history.get().snapshot["windows"]["registry"]["publisher"], "Microsoft Corporation"
        )
        self.assertEqual(self.sync()["changed"], 0)
        self.login(self.reader)
        page = self.client.get(self.url("agent-center") + "?device=" + str(self.device.pk))
        self.assertContains(page, windows.RULE)
        self.assertContains(page, "Manufacturer mapping reference")
        self.assertContains(page, "Update line missing")
        self.login(self.admin)
        self.assertEqual(
            self.client.get(self.url("agent-center", self.b) + "?device=" + str(self.device.pk)).status_code,
            404,
        )

    def test_version_boundaries_unsupported_rules_vendor_evidence_and_conflicts(self):
        self.prepare()
        m = windows.context(self.i)
        for version, expected in (
            ("130.0.0.0", "potential"),
            ("130.0.9.9", "potential"),
            ("130.0.10.0", "unknown"),
            ("", "unknown"),
            ("130.0.1.0-beta", "unknown"),
        ):
            self.i.version = version
            self.assertEqual(windows.evaluate(self.watch, self.i, self.payload, m)[0], expected)
        self.i.version = "130.0.1.0"
        variants = []
        for url in (
            "https://msrc.microsoft.com.attacker.invalid/advisory",
            "http://msrc.microsoft.com/advisory",
            "https://msrc.microsoft.com@attacker.invalid/advisory",
        ):
            p = copy.deepcopy(self.payload)
            p["containers"]["cna"]["references"] = [{"url": url}]
            variants.append(p)
        for field, value in (
            ("platforms", ["Linux"]),
            ("product", "Microsoft Edge (Chromium-based) Webview2"),
            ("modules", ["optional"]),
            ("cpes", [windows.cpe("microsoft", "edge")]),
        ):
            p = copy.deepcopy(self.payload)
            p["containers"]["cna"]["affected"][0][field] = value
            variants.append(p)
        for rule in (
            {"changes": [{"at": "130.0.1.0", "status": "unaffected"}]},
            {"versionType": "maven"},
            {"versionType": "semver"},  # Four-part browser versions are not SemVer.
            {"version": "*"},
        ):
            p = copy.deepcopy(self.payload)
            p["containers"]["cna"]["affected"][0]["versions"][0].update(rule)
            variants.append(p)
        p = copy.deepcopy(self.payload)
        p["containers"]["cna"]["affected"][0]["versions"].append(
            {"version": "130.0.1.0", "status": "unaffected"}
        )
        variants.append(p)
        for p in variants:
            self.assertEqual(windows.evaluate(self.watch, self.i, p, m)[0], "unknown")

    def test_expiry_missing_and_source_mismatch_invalidate_even_without_version_change(self):
        self.prepare()
        self.sync()
        match = DiscoveryMatch.objects.get()
        for change in (
            lambda: AgentComponent.objects.filter(pk=self.component.pk).update(missing_since=timezone.now()),
            lambda: AgentComponent.objects.filter(pk=self.component.pk).update(
                observed_at=timezone.now() - timedelta(days=1)
            ),
            lambda: AgentDevice.objects.filter(pk=self.device.pk).update(enabled=False),
            lambda: AgentDevice.objects.filter(pk=self.device.pk).update(source=self.sb),
        ):
            with self.subTest(change=change):
                # Savepoints keep each deliberately invalid binding isolated.
                from django.db import transaction

                with transaction.atomic():
                    change()
                    fresh = DiscoveryMatch.objects.get(pk=match.pk)
                    self.assertTrue(fresh.inputs_changed)
                    self.sync()
                    self.assertEqual(DiscoveryMatch.objects.get(pk=match.pk).result, "unknown")
                    transaction.set_rollback(True)

    def test_manual_decision_pause_and_source_visibility_survive_automatic_update(self):
        self.prepare()
        self.sync()
        finding = Finding.objects.get()
        transition_finding(self.admin, finding, "resolved", "Reviewed separately", "not_affected")
        finding.record.shareable = False
        finding.record.save()
        self.component.windows["publisher"] = ""
        self.component.save(update_fields=["windows"])
        self.sync()
        finding.refresh_from_db()
        self.assertEqual((finding.status, finding.analyst_applicability), ("resolved", "not_affected"))
        self.assertFalse(finding.record.shareable)
        self.assertEqual(finding.discovery.result, "unknown")
        self.assertEqual(finding.discovery.history.count(), 2)
        self.watch.enabled = False
        self.watch.save()
        self.assertEqual(product_matching.enroll_products(), 0)
        self.assertIsNone(discovery.sync_watch(self.watch.pk))
        self.watch.refresh_from_db()
        self.assertFalse(self.watch.enabled)

    def test_metadata_only_report_requests_new_evaluation_without_retargeting_watch(self):
        data = self.prepare()
        self.sync()
        data["components"][1]["windows"]["publisher"] = ""
        self.relax()
        data.update(report_id=str(uuid.uuid4()), sequence=2, observed_at=timezone.now().isoformat())
        self.publish(data)
        self.watch.refresh_from_db()
        self.assertTrue(self.watch.requested)
        self.assertEqual((self.watch.vendor, self.watch.product_key), ("microsoft", "edge_chromium"))
        self.sync()
        self.assertEqual(DiscoveryMatch.objects.get().result, "unknown")
        self.assertEqual(Finding.objects.get().installation.product_id, self.i.product_id)

    def test_foreign_report_reference_is_rejected_before_copying_its_body(self):
        self.prepare()
        foreign = self.component.last_report
        # Deliberately malformed retained data would fail JSON decoding if read.
        foreign.device_id = self.device.pk
        foreign.body = b"not-json-foreign-body"
        # Change the associated device identity only in memory to exercise the
        # early binding check without violating production FK constraints.
        self.component.last_report = foreign
        self.component.device = copy.copy(self.component.device)
        self.component.device.pk = uuid.uuid4()
        self.i.agent_component = self.component
        mapping = windows.context(self.i)
        self.assertIn("source/tenant", mapping["gaps"][0])
        self.assertNotIn("registry", mapping)
        self.assertNotIn("not-json", str(mapping))

    def test_existing_manual_finding_identity_and_decision_remain_authoritative(self):
        self.prepare()
        from .services import persist_lookup

        finding = persist_lookup(self.admin, self.i, self.watch.source_url, "CVE-2026-99999", self.payload)
        transition_finding(self.admin, finding, "resolved", "Manual evidence reviewed", "not_affected")
        self.sync()
        finding.refresh_from_db()
        self.assertEqual(finding.rule, "manual-cve-review/v1")
        self.assertEqual((finding.status, finding.analyst_applicability), ("resolved", "not_affected"))
        self.assertEqual(finding.discovery.result, "potential")
        self.assertEqual(Finding.objects.count(), 1)

    def test_explicit_esr_rules_cannot_cross_major_and_numeric_7zip_order_is_native(self):
        self.prepare()
        for name, publisher, version, vendor, key, reference, low, high, expected in (
            (
                "Mozilla Firefox ESR",
                "Mozilla",
                "128.9.0",
                "mozilla",
                "firefox_esr",
                "https://www.mozilla.org/security/advisories/synthetic/",
                "128.0",
                "128.10",
                "potential",
            ),
            (
                "Mozilla Firefox ESR",
                "Mozilla",
                "128.9.0",
                "mozilla",
                "firefox_esr",
                "https://www.mozilla.org/security/advisories/synthetic/",
                "115.0",
                "140.0",
                "unknown",
            ),
            (
                "7-Zip 24.09 (x64)",
                "Igor Pavlov",
                "24.09",
                "7-zip",
                "7-zip",
                "https://www.7-zip.org/history.txt",
                "24.01",
                "24.10",
                "potential",
            ),
        ):
            c = SimpleNamespace(
                name=name, version=version, windows={"kind": "program", "publisher": publisher}
            )
            m = windows.resolve(c, {})
            p = advisory(
                windows.cpe(vendor, key),
                low,
                high,
                vendor=vendor,
                product="Firefox ESR" if vendor == "mozilla" else "7-Zip",
            )
            p["containers"]["cna"]["references"] = [{"url": reference}]
            i = SimpleNamespace(version=version, build="", edition="")
            watch = SimpleNamespace(vendor=vendor, product_key=key)
            self.assertEqual(windows.evaluate(watch, i, p, m)[0], expected)
