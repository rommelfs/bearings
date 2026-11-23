"""Current review cohorts, data/evaluation phases, distinct units and explicit UI timezone."""

from types import SimpleNamespace
import copy
from datetime import datetime, timezone as utc, timedelta
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .test_ubuntu_status import UbuntuStatusTests as Base, CVE
from .models import Finding, AssetIssue, AgentComponent, DistroMatch, Installation
from . import distro_cves, distro_evaluation
from .overview import company_states
from .templatetags.ui_time import display_time


class UnitTests(SimpleTestCase):
    @override_settings(DISPLAY_TIME_ZONE="Europe/Berlin")
    def test_ui_times_are_explicit_and_dst_correct_without_changing_backend_clock(self):
        self.assertEqual(display_time("2026-11-23T14:57:00+00:00"), "2026-11-23 15:57:00 CET")
        self.assertEqual(display_time(datetime(2026, 7, 1, 13, tzinfo=utc.utc)), "2026-07-01 15:00:00 CEST")
        self.assertEqual(settings.TIME_ZONE, "UTC")

    def test_distinct_cves_packages_and_records_do_not_multiply_advisories(self):
        def row(reason):
            return {"result": "unknown", "package_check": {"uncertainty_reason": reason}}

        result = distro_evaluation.metrics(
            SimpleNamespace(
                results={
                    "a": {CVE: row("vendor_needs_triage")},
                    "b": {CVE: row("vendor_ignored"), "CVE-2099-20000": row("vendor_needs_triage")},
                }
            )
        )
        self.assertEqual(result["outcomes"]["unknown"], {"cves": 2, "packages": 2, "records": 3})
        self.assertEqual(sum(g["records"] for g in result["reasons"]), 3)


class EvaluationTests(Fixture):
    legacy_manual_projection = False
    setUp = Base.setUp
    post = Base.post
    enroll = Base.enroll
    data = Base.data
    send = Base.send
    load = Base.load
    cached = Base.cached
    prepare = Base.prepare

    def test_data_complete_is_distinct_from_evaluation_complete_and_fragment_updates(self):
        self.prepare()
        row = self.device.ubuntu_status_uses.get().status
        row.error = "Ubuntu status refresh failed (HTTPS timeout); previous evidence retained"
        row.save()
        distro_cves.evaluate_device(self.device.pk)
        self.cached(version="1:1.24.0-2ubuntu7.5")
        self.login(self.reader)
        poll = self.client.get(reverse("agent-lookup-progress"), {"device": self.device.pk}).json()[
            "devices"
        ][str(self.device.pk)]
        self.assertEqual((poll["fresh"], poll["total"]), (1, 1))
        self.assertEqual(poll["evaluation"]["state"], "evaluation_pending")
        self.assertTrue(poll["evaluation"]["historical"])
        url = reverse("agent-evaluation", args=[self.a.slug, self.device.pk])
        before = self.client.get(url)
        self.assertEqual(before.status_code, 200)
        self.assertIn("no-store", before.headers["Cache-Control"])
        self.assertIn("previous snapshot", before.json()["html"])
        self.assertIn("Previous evaluation counts and reasons", before.json()["html"])
        old = before.json()["revision"]
        distro_cves.evaluate_device(self.device.pk)
        after = self.client.get(url).json()
        self.assertNotEqual(after["revision"], old)
        self.assertNotIn("Ubuntu lookup failed at evaluation time", after["html"])
        self.device.refresh_from_db()
        self.assertEqual(self.device.distro_summary["decision_counts"]["outcomes"]["fixed"]["records"], 1)
        self.assertEqual(
            self.client.get(reverse("agent-evaluation", args=[self.b.slug, self.device.pk])).status_code, 404
        )
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_overview_matches_review_cohorts_and_preserves_analyst_and_task_authority(self):
        self.cached()
        self.prepare()
        state = company_states(self.reader, [self.a])[0]
        self.assertEqual((state["automatic_affected"], state["affected"], state["review_action"]), (1, 0, 1))
        finding = Finding.objects.get()
        original_status = finding.status
        self.cached(version="1:1.24.0-2ubuntu7.5")
        distro_cves.evaluate_device(self.device.pk)
        state = company_states(self.reader, [self.a])[0]
        self.assertEqual((state["reviews"], state["review_cleared"], state["automatic_affected"]), (0, 1, 0))
        self.assertNotEqual(state["status"], "Review required")
        issue = AssetIssue.objects.get(finding=finding)
        from .issues import save_issue

        save_issue(
            self.admin, issue, {"priority": "low"}, "Synthetic explicit follow-up remains a human task"
        )
        state = company_states(self.reader, [self.a])[0]
        self.assertEqual((state["reviews"], state["issues"]), (0, 1))
        issue.action_due = timezone.localdate() - timedelta(days=1)
        issue.next_action = "Synthetic explicitly scheduled follow-up"
        issue.save()
        state = company_states(self.reader, [self.a])[0]
        self.assertEqual(state["overdue"], 1)
        finding.refresh_from_db()
        self.assertEqual(finding.status, original_status)
        finding.analyst_applicability = "affected"
        finding.save()
        state = company_states(self.reader, [self.a])[0]
        self.assertEqual((state["affected"], state["review_action"], state["review_cleared"]), (1, 1, 0))

    def test_pending_fix_is_separate_from_untriaged_and_ignored(self):
        self.cached(status="pending", version="")
        summary = self.prepare()
        groups = summary["decision_counts"]["reasons"]
        self.assertEqual(groups[0]["code"], "vendor_fix_pending")
        self.assertEqual(groups[0]["cves"], 1)
        self.assertEqual(summary["potential"], 0)

    def test_shared_rollups_keep_complete_counts_when_previews_are_limited(self):
        self.cached()
        self.prepare()
        finding = Finding.objects.get()
        match = finding.distro_match
        issue = AssetIssue.objects.get(finding=finding)
        component = self.device.components.get()
        initial_installations = Installation.objects.filter(asset=self.asset).count()
        for number in range(29):
            installation = copy.copy(finding.installation)
            installation.pk = None
            installation.save()
            another_component = copy.copy(component)
            another_component.pk = None
            another_component.key = f"dpkg:nginx:synthetic-{number}"
            another_component.installation = installation
            another_component.save()
            another = copy.copy(finding)
            another.pk, another.installation = None, installation
            another.save()
            proof = copy.copy(match)
            proof.pk, proof.component, proof.finding = None, another_component, another
            proof.snapshot = copy.deepcopy(match.snapshot)
            proof.snapshot["package_check"]["verdict"] = (
                "fixed" if number < 9 else "unresolved" if number < 19 else "affected"
            )
            proof.save()
            another_issue = copy.copy(issue)
            another_issue.pk, another_issue.finding, another_issue.installation = None, another, installation
            another_issue.save()
        self.login(self.platform)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/infrastructure/?organization=alpha")
        self.assertEqual(response.status_code, 200)
        state = response.context["companies"][0]
        self.assertEqual((state["reviews"], state["review_cleared"], state["issues"]), (21, 9, 21))
        self.assertEqual((state["review_action"], state["review_unresolved"]), (11, 10))
        preview = response.context["priority_assets"][0]
        self.assertEqual(preview["reviews"], state["reviews"])
        self.assertEqual(len(preview["problems"]), 4)
        # Fixed per-request work, including PostgreSQL local planning guards;
        # aggregating 30 rows must not hydrate each proof or preview separately.
        self.assertLessEqual(len(queries), 33)
        self.assertEqual(Installation.objects.filter(asset=self.asset).count(), initial_installations + 29)
        self.assertEqual(AgentComponent.objects.filter(device=self.device).count(), 30)
        self.assertEqual(DistroMatch.objects.count(), 30)
        # The rollups are request-local: a new input invalidates the next page.
        self.device.distro_requested = True
        self.device.save(update_fields=["distro_requested"])
        state = self.client.get("/infrastructure/?organization=alpha").context["companies"][0]
        self.assertEqual((state["review_pending"], state["review_cleared"]), (30, 0))
