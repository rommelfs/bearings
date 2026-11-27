"""Exact official source/release status, absence/age/conflict retention and safe cache refresh."""

from datetime import timedelta
from unittest.mock import patch
from django.test import override_settings
from django.urls import reverse
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

    def test_confirmed_no_fix_stays_in_evidence_and_reenters_work_when_a_fix_is_published(self):
        from . import remediation
        from .review_queue import classified
        from .review_work import scoped_work

        self.cached(status="ignored", version="")
        self.prepare()
        url = reverse("intelligence", args=[self.a.slug])
        self.login(self.admin)

        for status, label in (
            ("ignored", "Ubuntu has marked the issue ignored"),
            ("deferred", "Ubuntu has deferred the fix"),
            ("needed", "Ubuntu marks the package vulnerable"),
            ("pending", "Ubuntu has a fix pending publication"),
        ):
            with self.subTest(status=status):
                self.cached(status=status, version="")
                distro_cves.evaluate_device(self.device.pk)
                finding = classified(Finding.objects.all()).get()
                self.assertEqual(finding.queue_bucket, "vendor_no_fix")
                self.assertEqual(finding.analyst_applicability, "unassessed")
                self.assertFalse(remediation.work(self.admin, self.a).exists())
                self.assertFalse(scoped_work(Finding.objects.all(), "cleared").exists())
                for view in ("cve", "machine", "software"):
                    response = self.client.get(url, {"view": view})
                    self.assertEqual(response.context["page"].paginator.count, 0)
                    response = self.client.get(url, {"view": view, "state": "vendor_no_fix"})
                    self.assertEqual(response.context["page"].paginator.count, 1)
                evidence = self.client.get(url, {"state": "vendor_no_fix"})
                self.assertContains(evidence, label)
                self.assertNotContains(evidence, "Notify about this CVE")
                self.assertContains(self.client.get(url, {"finding": finding.pk}), label)
                self.assertEqual(self.client.get(reverse("issues")).context["page"].paginator.count, 0)

        self.cached()
        self.assertEqual(classified(Finding.objects.all()).get().queue_bucket, "pending")
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(classified(Finding.objects.all()).get().queue_bucket, "action")
        self.assertContains(self.client.get(url), CVE)
        self.assertTrue(remediation.work(self.admin, self.a).exists())

    def test_current_ubuntu_triage_is_visible_as_monitoring_and_keeps_assessment_precedence(self):
        from . import remediation
        from .review_queue import classified
        from .review_work import scoped_work

        row = self.cached(status="needs-triage", version="")
        self.prepare()
        url = reverse("intelligence", args=[self.a.slug])
        self.login(self.admin)
        findings = Finding.objects.all()
        finding = classified(findings).get()
        self.assertEqual(finding.queue_bucket, "vendor_triage")
        for view in ("cve", "machine", "software"):
            self.assertEqual(self.client.get(url, {"view": view}).context["page"].paginator.count, 0)
            page = self.client.get(url, {"view": view, "state": "vendor_triage"}).context["page"]
            self.assertEqual(page.paginator.count, 1)
        response = self.client.get(url, {"state": "vendor_triage"})
        self.assertContains(response, "Canonical is still assessing this release and source package")
        self.assertContains(response, f'href="https://vulnerability.circl.lu/vuln/{CVE.lower()}"')
        self.assertNotContains(response, "Notify about this CVE")
        self.assertFalse(scoped_work(findings, "unresolved").exists())
        self.assertFalse(scoped_work(findings, "vendor_no_fix").exists())
        self.assertFalse(remediation.work(self.admin, self.a).exists())
        self.assertEqual(self.client.get(reverse("issues")).context["page"].paginator.count, 0)

        findings.update(analyst_applicability="affected")
        self.assertTrue(scoped_work(findings, "attention").exists())
        findings.update(analyst_applicability="unassessed")
        row.last_success = timezone.now() - timedelta(hours=13)
        row.save(update_fields=["last_success"])
        self.assertEqual(classified(findings).get().queue_bucket, "pending")
        self.assertTrue(scoped_work(findings, "attention").exists())

    def test_no_fix_evidence_keeps_a_saved_affected_assessment_actionable(self):
        from .review_queue import classified
        from .review_work import scoped_work

        self.cached(status="deferred", version="")
        self.prepare()
        finding = Finding.objects.get()
        finding.analyst_applicability = "affected"
        finding.save(update_fields=["analyst_applicability"])
        self.assertEqual(classified(Finding.objects.all()).get().queue_bucket, "action")
        self.assertTrue(scoped_work(Finding.objects.all(), "attention").exists())

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
            ubuntu_status.refresh_due(limit=4)
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
    def test_batch_continues_after_fast_results_without_more_than_four_requests_at_once(self):
        import threading
        import time

        ubuntu_status.enqueue(["CVE-2099-" + str(n) for n in range(10010, 10030)])
        lock = threading.Lock()
        active, peak = 0, 0

        def fetch(method, url, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.005)
            with lock:
                active -= 1
            self.assertLessEqual(kwargs["timeout"].read, 40)
            return response(cve=url.rsplit("/", 1)[1].removesuffix(".json"))

        with (
            patch("portal.ubuntu_status.approved_base"),
            patch("portal.ubuntu_status.request_json", side_effect=fetch) as request,
        ):
            ubuntu_status.refresh_due()
        self.assertEqual(request.call_count, 16)
        self.assertLessEqual(peak, 4)
        self.assertEqual(UbuntuCVEStatus.objects.filter(last_attempt__isnull=True).count(), 4)

    @override_settings(UBUNTU_STATUS_FETCH_ENABLED=True)
    def test_unstarted_batch_items_keep_queue_position_and_timeout_diagnostics_are_safe(self):
        from .connectors.http import ConnectorError, request_json
        import httpx

        ubuntu_status.enqueue([CVE])
        with (
            patch("time.monotonic", side_effect=lambda: next(ticks, 1000)),
            patch("portal.ubuntu_status.request_json") as request,
        ):
            ticks = iter([0])
            ubuntu_status.refresh_due()
        request.assert_not_called()
        row = UbuntuCVEStatus.objects.get(pk=CVE)
        self.assertIsNone(row.last_attempt)
        self.assertIsNone(row.lease_until)
        with patch("portal.connectors.http.httpx.Client", side_effect=httpx.ReadTimeout("secret-sentinel")):
            try:
                request_json("GET", "https://example.invalid")
            except ConnectorError as exc:
                self.assertEqual(exc.reason_code, "timeout")
                failure = exc
        with (
            patch("portal.ubuntu_status.approved_base"),
            patch("portal.ubuntu_status.request_json", side_effect=failure),
        ):
            ubuntu_status.refresh_due()
        row.refresh_from_db()
        self.assertIn("HTTPS timeout", row.error)
        self.assertNotIn("secret-sentinel", row.error)

    def test_live_progress_counts_unique_cves_not_associations_and_rejects_foreign_source(self):
        self.cached()
        self.prepare()
        item = ubuntu_status.progress([self.device.pk])[self.device.pk]
        self.assertEqual((item["total"], item["fresh"], item["failed"]), (1, 1, 0))
        self.login(self.reader)
        from django.urls import reverse

        response = self.client.get(reverse("agent-center", args=[self.a.slug]), {"device": self.device.pk})
        self.assertContains(response, "Ubuntu status lookup progress")
        self.assertContains(response, 'data-count="fresh">1</span>')
        self.assertContains(response, "unique CVE lookups current")
        cache = UbuntuCVEStatus.objects.get(pk=CVE)
        cache.error = "Ubuntu status refresh failed (HTTPS timeout); previous evidence retained"
        cache.save()
        item = ubuntu_status.progress([self.device.pk])[self.device.pk]
        self.assertEqual((item["fresh"], item["failed"], item["refresh_errors"]), (1, 0, 1))
        cache.last_success = None
        cache.save()
        item = ubuntu_status.progress([self.device.pk])[self.device.pk]
        self.assertEqual((item["total"], item["fresh"], item["pending"], item["failed"]), (1, 0, 0, 1))
        cache.error = ""
        cache.save()
        item = ubuntu_status.progress([self.device.pk])[self.device.pk]
        self.assertEqual((item["total"], item["fresh"], item["pending"], item["failed"]), (1, 0, 1, 0))
        self.device.source = self.sb
        self.device.save(update_fields=["source"])
        self.assertFalse(ubuntu_status.progress([self.device.pk]))

    def test_poll_endpoint_is_scoped_read_only_bounded_and_does_not_fetch_or_evaluate(self):
        from django.urls import reverse
        from .models import AgentDevice, Asset

        self.cached()
        self.prepare()
        self.login(self.reader)
        url = reverse("agent-lookup-progress")
        with (
            patch("portal.ubuntu_status.request_json") as fetch,
            patch("portal.distro_cves.evaluate_device") as evaluate,
        ):
            response = self.client.get(url, {"device": [str(self.device.pk)]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["schema"], "bearings.lookup-progress.v1")
            self.assertEqual(response.json()["devices"][str(self.device.pk)]["fresh"], 1)
            self.assertNotContains(response, CVE)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual(self.client.post(url, {}).status_code, 405)
            self.assertEqual(self.client.get(url).status_code, 400)
            self.assertEqual(self.client.get(url, {"device": "bad"}).status_code, 400)
            self.assertEqual(self.client.get(url, {"device": [str(self.device.pk)] * 37}).status_code, 400)
            foreign_asset = Asset.objects.create(
                organization=self.b, source=self.sb, name="private-poll-asset"
            )
            foreign = AgentDevice.objects.create(
                organization=self.b,
                source=self.sb,
                asset=foreign_asset,
                public_key="private-poll-key",
                expires_at=timezone.now() + timedelta(days=1),
            )
            denied = self.client.get(url, {"device": [str(self.device.pk), str(foreign.pk)]})
            self.assertEqual(denied.status_code, 404)
            self.assertNotIn("devices", denied.json())
            fetch.assert_not_called()
            evaluate.assert_not_called()
        UbuntuStatusUse.objects.filter(device=self.device).delete()
        empty = self.client.get(url, {"device": self.device.pk}).json()["devices"][str(self.device.pk)]
        self.assertEqual((empty["total"], empty["fresh"], empty["pending"], empty["failed"]), (0, 0, 0, 0))
        initial = self.client.get(reverse("agent-center", args=[self.a.slug]), {"device": self.device.pk})
        self.assertContains(initial, "data-ubuntu-progress")
        self.assertContains(initial, "No CVE lookups requested by the last evaluation yet.")
        self.device.source = self.sb
        self.device.save(update_fields=["source"])
        self.assertEqual(self.client.get(url, {"device": self.device.pk}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url, {"device": self.device.pk}).status_code, 302)

    def test_poll_rechecks_operator_visibility_after_page_load(self):
        from django.urls import reverse

        self.prepare()
        self.login(self.analyst)
        url = reverse("agent-lookup-progress")
        self.assertEqual(self.client.get(url, {"device": self.device.pk}).status_code, 200)
        self.a.operator_visibility = False
        self.a.save(update_fields=["operator_visibility"])
        self.assertEqual(self.client.get(url, {"device": self.device.pk}).status_code, 404)

    @override_settings(UBUNTU_STATUS_FETCH_ENABLED=True)
    def test_stale_status_invalidates_once_and_new_fresh_data_requeues_after_two_minutes(self):
        row = self.cached()
        self.prepare()
        row.last_success = timezone.now() - timedelta(hours=13)
        row.lease_until = timezone.now() + timedelta(hours=1)
        row.save()

        def eligible():
            AgentDevice.objects.filter(pk=self.device.pk).update(
                distro_requested=False, distro_checked_at=timezone.now() - timedelta(minutes=3)
            )

        eligible()
        ubuntu_status.refresh_due()
        self.device.refresh_from_db()
        self.assertTrue(self.device.distro_requested)
        distro_cves.evaluate_device(self.device.pk)
        eligible()
        ubuntu_status.refresh_due()
        self.device.refresh_from_db()
        self.assertFalse(self.device.distro_requested)
        row.last_success = timezone.now()
        row.save()
        ubuntu_status.refresh_due()
        self.device.refresh_from_db()
        self.assertTrue(self.device.distro_requested)

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
