"""Exact official source/release status, absence/age/conflict retention and safe cache refresh."""

from datetime import timedelta
from unittest.mock import patch
from django.test import override_settings
from django.utils import timezone
from .tests import Fixture
from . import agents, distro_cves, ubuntu_status
from .intelligence import digest
from .models import UbuntuCVEStatus, UbuntuStatusUse, Finding, AgentDevice
from .test_distro_cves import XML

CVE = "CVE-2099-99999"


def response(cve=CVE, status="released", version="1:1.24.0-2ubuntu7.8", source="nginx", release="noble"):
    return {
        "id": cve,
        "packages": [
            {
                "name": source,
                "statuses": [
                    {
                        "release_codename": release,
                        "status": status,
                        "description": version,
                        "pocket": "security",
                    }
                ],
            }
        ],
    }


class UbuntuStatusTests(Fixture):
    from .test_distro_cves import DistroTests as _Distro

    legacy_manual_projection = False
    setUp = _Distro.setUp
    post = _Distro.post
    enroll = _Distro.enroll
    data = _Distro.data
    send = _Distro.send
    load = _Distro.load

    def cached(self, **kwargs):
        data = ubuntu_status.normalize(response(**kwargs), CVE)
        row, _ = UbuntuCVEStatus.objects.update_or_create(
            cve=CVE, defaults={"payload": data, "content_hash": digest(data), "last_success": timezone.now()}
        )
        return row

    def prepare(self, *, with_source=True, guard=False):
        self.enroll()
        data = self.data(version="99.0")
        if with_source:
            data["components"][0]["source"] = {"name": "nginx", "version": "1:1.24.0-2ubuntu7.6"}
        self.send(data)
        agents.process_pending()
        xml = XML.replace('<l:state state_ref="s1"/>', "")
        if guard:
            xml = xml.replace('test_ref="t1"/>', 'test_ref="t1"/><criterion test_ref="unsupported"/>')
        self.feed = self.load(xml)
        return distro_cves.evaluate_device(self.device.pk)

    def test_source_version_not_binary_version_controls_fix_and_preserves_human_workflow(self):
        self.cached()
        summary = self.prepare()
        self.assertEqual(summary["potential"], 1)
        finding = Finding.objects.get()
        proof = finding.distro_match.snapshot["package_check"]
        self.assertEqual(proof["comparisons"][0]["installed_version"], "1:1.24.0-2ubuntu7.6")
        self.assertEqual(proof["comparisons"][0]["basis"], "source package")
        self.assertEqual(finding.distro_match.ubuntu_status_id, CVE)
        finding.status = "confirmed"
        finding.analyst_applicability = "affected"
        finding.save()
        self.cached(version="1:1.24.0-2ubuntu7.5")
        finding.refresh_from_db()
        self.assertTrue(finding.distro_match.inputs_changed)
        distro_cves.evaluate_device(self.device.pk)
        finding.refresh_from_db()
        self.assertEqual(finding.applicability, "not_affected")
        self.assertEqual(finding.status, "confirmed")
        self.assertEqual(finding.analyst_applicability, "affected")
        self.assertEqual(finding.distro_match.snapshot["package_check"]["verdict"], "fixed")
        self.assertEqual(UbuntuStatusUse.objects.count(), 1)

    def test_needs_triage_missing_source_and_required_guard_remain_unresolved(self):
        self.cached(status="needs-triage", version="")
        summary = self.prepare()
        self.assertEqual(summary["state"], "partial")
        self.assertEqual(summary["uncertainty_reasons"], {"vendor_needs_triage": 1})
        self.cached()
        self.device.components.update(package_source={})
        summary = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(summary["uncertainty_reasons"], {"source_metadata_missing": 1})

    def test_status_cannot_bypass_unsupported_oval_guard(self):
        self.cached()
        summary = self.prepare(guard=True)
        self.assertEqual(summary["potential"], 0)
        self.assertEqual(summary["uncertain"], 1)
        self.assertFalse(Finding.objects.get().distro_match.ubuntu_status_id)

    def test_wrong_release_and_source_never_become_a_version_verdict(self):
        self.cached(source="not-nginx", release="jammy")
        summary = self.prepare()
        self.assertEqual(summary["potential"], 0)
        self.assertEqual(summary["uncertainty_reasons"], {"vendor_source_not_listed": 1})

    def test_expired_status_is_not_used_and_pending_dependency_is_retained(self):
        row = self.cached()
        row.last_success = timezone.now() - timedelta(hours=13)
        row.save()
        summary = self.prepare()
        self.assertEqual(summary["potential"], 0)
        self.assertEqual(summary["uncertainty_reasons"], {"ubuntu_status_stale": 1})
        self.assertEqual(UbuntuStatusUse.objects.get().content_hash, "")
        self.assertTrue(summary["ubuntu_status_pending"])

    def test_conflicting_pockets_and_unknown_version_stay_unresolved(self):
        data = response()
        data["packages"][0]["statuses"].append(
            {
                "release_codename": "noble",
                "status": "released",
                "description": "1:1.24.0-2ubuntu7.5",
                "pocket": "esm-apps",
            }
        )
        payload = ubuntu_status.normalize(data, CVE)
        UbuntuCVEStatus.objects.create(
            cve=CVE, payload=payload, content_hash=digest(payload), last_success=timezone.now()
        )
        summary = self.prepare()
        self.assertEqual(summary["potential"], 0)
        self.assertEqual(summary["uncertain"], 1)
        self.device.components.update(package_source={"name": "nginx", "version": "unknown"})
        summary = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(summary["potential"], 0)
        self.assertEqual(summary["uncertainty_reasons"], {"invalid_source_version": 1})

    def test_queue_and_receipt_cannot_keep_stale_supplementary_fixed_proof_current(self):
        from .review_queue import classified
        from . import distro_display

        self.cached()
        self.prepare()
        self.cached(version="1:1.24.0-2ubuntu7.5")
        distro_cves.evaluate_device(self.device.pk)
        finding = Finding.objects.get()
        self.assertEqual(classified(Finding.objects.all()).get().queue_bucket, "cleared")
        self.cached(status="needs-triage", version="")
        finding.refresh_from_db()
        self.assertTrue(finding.distro_match.inputs_changed)
        self.assertEqual(classified(Finding.objects.all()).get().queue_bucket, "pending")
        installation = finding.installation
        distro_display.decorate_installations(self.reader, [installation])
        self.assertFalse(installation.cve_component.check_current)

    def test_receipt_retains_all_status_dependencies_when_another_rule_wins(self):
        self.cached(version="1:1.24.0-2ubuntu7.5")
        self.prepare()
        xml = XML.replace('operation="less than"', 'operation="equals"').replace(
            "1:1.24.0-2ubuntu7.6</l:evr>", "0</l:evr>"
        )
        definition = xml.split("<definitions>")[1].split("</definitions>")[0]
        definition = definition.replace('id="oval:synthetic:def:1"', 'id="oval:synthetic:def:2"').replace(
            'test_ref="t1"', 'test_ref="t2"'
        )
        test = '<l:dpkginfo_test id="t2" check="at least one" check_existence="at_least_one_exists"><l:object object_ref="o1"/></l:dpkginfo_test>'
        self.load(
            xml.replace("</definitions>", definition + "</definitions>").replace(
                "</tests>", test + "</tests>"
            )
        )
        distro_cves.evaluate_device(self.device.pk)
        component = self.device.components.get()
        self.assertEqual(component.distro_check["counts"]["not_matched"], 1)
        self.assertEqual(
            component.distro_check["ubuntu_status_hashes"],
            {CVE: self.cached(version="1:1.24.0-2ubuntu7.5").content_hash},
        )
        self.cached(status="needed", version="")
        self.assertFalse(ubuntu_status.receipt_flags([component])[component.pk])

    @override_settings(UBUNTU_STATUS_FETCH_ENABLED=True)
    def test_refresh_is_bounded_fixed_destination_and_outage_retains_verified_data(self):
        old = self.cached()
        old.last_success = timezone.now() - timedelta(hours=7)
        old.save()
        ubuntu_status.enqueue(["CVE-2099-" + str(n) for n in range(10001, 10006)])

        def fetch(method, url, **kwargs):
            return response(cve=url.rsplit("/", 1)[1].removesuffix(".json"))

        with (
            patch("portal.ubuntu_status.approved_base"),
            patch("portal.ubuntu_status.request_json", side_effect=fetch) as request,
        ):
            ubuntu_status.refresh_due()
        self.assertEqual(request.call_count, 4)
        self.assertTrue(
            all(
                c.args[0] == "GET" and c.args[1].startswith("https://ubuntu.com/security/cves/CVE-2099-")
                for c in request.call_args_list
            )
        )
        # A provider failure never clears the prior payload or success timestamp.
        UbuntuCVEStatus.objects.exclude(cve=CVE).update(lease_until=timezone.now() + timedelta(hours=1))
        old.refresh_from_db()
        before = old.payload
        stamp = old.last_success
        with (
            patch("portal.ubuntu_status.approved_base"),
            patch("portal.ubuntu_status.request_json", side_effect=ValueError("secret-sentinel")),
        ):
            ubuntu_status.refresh_due()
        old.refresh_from_db()
        self.assertEqual(old.payload, before)
        self.assertEqual(old.last_success, stamp)
        self.assertNotIn("secret-sentinel", old.error)

    @override_settings(UBUNTU_STATUS_FETCH_ENABLED=True)
    def test_status_change_requeues_even_initial_fixed_package_without_finding(self):
        self.cached(version="1:1.24.0-2ubuntu7.5")
        self.prepare()
        self.assertFalse(Finding.objects.exists())
        self.assertEqual(UbuntuStatusUse.objects.count(), 1)
        self.cached(status="needs-triage", version="")
        AgentDevice.objects.filter(pk=self.device.pk).update(
            distro_requested=False, distro_checked_at=timezone.now() - timedelta(minutes=16)
        )
        with (
            patch("portal.ubuntu_status.approved_base"),
            patch("portal.ubuntu_status.request_json") as request,
        ):
            ubuntu_status.refresh_due()
        self.assertFalse(request.called)
        self.device.refresh_from_db()
        self.assertTrue(self.device.distro_requested)
