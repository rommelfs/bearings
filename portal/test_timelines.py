"""Event charts retain current policy, exact date buckets and honest receipt semantics."""

from datetime import timedelta
from zoneinfo import ZoneInfo
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import FindingHistory
from .timelines import review_decisions, report_receipts, series


class ReviewTimelineTests(Fixture):
    def decision(self, finding, previous, status, when):
        return FindingHistory.objects.create(
            finding=finding, previous_status=previous, status=status, reason="fixture", created_at=when
        )

    def test_filters_and_confidential_evidence_are_respected_across_all_pages(self):
        visible = self.record_finding(shareable=False)
        self.decision(visible, "new", "resolved", timezone.now())
        self.login(self.reader)
        response = self.client.get(reverse("intelligence", args=[self.a.slug]))
        self.assertEqual(response.context["review_timeline"]["total"], 0)
        visible.record.shareable = True
        visible.record.save()
        response = self.client.get(reverse("intelligence", args=[self.a.slug]))
        self.assertEqual(response.context["review_timeline"]["total"], 1)
        self.assertContains(response, "Daily values")
        self.assertIn("no-store", response["Cache-Control"])
        response = self.client.get(reverse("intelligence", args=[self.a.slug]), {"attention": "affected"})
        self.assertEqual(response.context["review_timeline"]["total"], 0)
        self.assertEqual(self.client.get(reverse("intelligence", args=[self.b.slug])).status_code, 404)

    def test_repeated_resolved_state_is_not_a_new_transition_and_future_is_excluded(self):
        finding = self.record_finding()
        self.decision(finding, "new", "resolved", timezone.now())
        self.decision(finding, "resolved", "resolved", timezone.now())
        self.decision(finding, "resolved", "new", timezone.now())
        self.decision(finding, "new", "confirmed", timezone.now() + timedelta(days=1))
        self.decision(finding, "new", "confirmed", timezone.now() - timedelta(days=40))
        data = review_decisions(self.a.findings.all())
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["rows"][-1]["counts"], [0, 1, 1])
        self.assertEqual(len(data["rows"]), 30)
        self.assertEqual(len(data["chart"]["labels"]), 30)

    def test_inconsistent_inventory_lineage_does_not_add_derived_history(self):
        from .models import Installation

        finding = self.record_finding()
        self.decision(finding, "new", "resolved", timezone.now())
        Installation.objects.filter(pk=self.installation.pk).update(asset=self.other)
        self.assertEqual(review_decisions(self.a.findings.all())["total"], 0)

    @override_settings(TIME_ZONE="Europe/Luxembourg")
    def test_event_bucket_uses_the_display_timezone(self):
        with timezone.override(ZoneInfo("Europe/Luxembourg")):
            finding = self.record_finding()
            local_yesterday = timezone.localdate() - timedelta(days=2)
            when = timezone.datetime.combine(
                local_yesterday, timezone.datetime.min.time(), tzinfo=ZoneInfo("UTC")
            ) + timedelta(hours=23, minutes=30)
            self.decision(finding, "new", "resolved", when)
            data = review_decisions(self.a.findings.all())
            self.assertEqual(data["timezone"], "Europe/Luxembourg")
            self.assertEqual(data["rows"][-2]["counts"], [0, 1, 0])

    def test_empty_window_does_not_invent_a_backlog_or_health_measure(self):
        data = series("Fixture", "Retained events", {"n": "Events"}, {})
        self.assertEqual(data["total"], 0)
        self.assertEqual(len(data["rows"]), 30)
        self.assertTrue(all(row["counts"] == [0] for row in data["rows"]))


class ReportTimelineTests(Fixture):
    legacy_manual_projection = False
    from .test_agents import AgentTests as _Agent

    setUp = _Agent.setUp
    post = _Agent.post
    enroll = _Agent.enroll
    data = _Agent.data
    send = _Agent.send
    relax = _Agent.relax

    def test_receipt_status_is_current_and_device_lineage_is_required(self):
        from . import agents
        from .models import AgentDevice, Asset

        self.enroll()
        self.send()
        devices = AgentDevice.objects.filter(pk=self.device.pk)
        self.assertEqual(report_receipts(devices)["rows"][-1]["counts"], [0, 1, 0, 0])
        agents.process_pending()
        self.assertEqual(report_receipts(devices)["rows"][-1]["counts"], [1, 0, 0, 0])
        self.assertEqual(report_receipts(AgentDevice.objects.filter(organization=self.b))["total"], 0)
        Asset.objects.filter(pk=self.asset.pk).update(source=self.sb)
        self.assertEqual(report_receipts(devices)["total"], 0)
