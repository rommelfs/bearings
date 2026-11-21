"""Reviews need explicit reasons, state and actions rather than unexplained alarm lists."""

from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import Finding, SourceRecord
from .issues import ensure_vulnerability_issue


class OverviewExplanationTests(Fixture):
    def setUp(self):
        self.login()

    def finding(
        self, number, *, automatic="unknown", analyst="unassessed", score=5, rule="distro-oval-review/v1"
    ):
        record = SourceRecord.objects.create(
            organization=self.a,
            source="https://security.example.invalid/advisory",
            external_id=f"CVE-2026-{10000 + number}",
            shareable=True,
            payload={
                "containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": score}}]}}
            },
        )
        return Finding.objects.create(
            organization=self.a,
            installation=self.installation,
            record=record,
            applicability=automatic,
            analyst_applicability=analyst,
            rule=rule,
            explanation="Synthetic matching evidence",
        )

    def test_manual_review_explains_missing_version_and_links_to_assessment(self):
        finding = self.finding(1, rule="manual-cve-review/v1")
        ensure_vulnerability_issue(finding)
        response = self.client.get(reverse("overview"))
        review = response.context["priority_assets"][0]["problems"][0]["review"]
        self.assertIn("installed version is missing", review["reason"])
        self.assertEqual(review["assessment"], "Not assessed")
        self.assertEqual(review["automatic"], "No automatic version check recorded")
        self.assertEqual(review["source"], "security.example.invalid")
        self.assertContains(response, "Why this server is listed:")
        self.assertContains(response, "Installed software:")
        self.assertContains(response, "open CVE–installation reviews")
        self.assertContains(response, f"?finding={finding.pk}#finding-{finding.pk}")
        self.assertNotContains(response, "0 Critical source severity")
        self.assertContains(response, "Optional risk scenario · draft")
        finding.refresh_from_db()
        self.assertEqual(finding.status, "new")

    def test_automatic_not_affected_conflict_requires_reconciliation(self):
        finding = self.finding(2, automatic="not_affected", analyst="affected")
        ensure_vulnerability_issue(finding)
        response = self.client.get(reverse("overview"))
        review = response.context["priority_assets"][0]["problems"][0]["review"]
        self.assertIn("need reconciliation", review["reason"])
        self.assertIn("reconcile", review["next_action"])
        self.assertEqual(review["automatic"], "Not affected by recorded check")
        self.assertEqual(review["assessment"], "Affected (analyst assessment)")

    def test_preview_prioritizes_due_actions_then_assessment_then_matching_and_severity(self):
        self.installation.version = "1.2.3"
        self.installation.save()
        overdue = self.finding(3, score=1)
        confirmed = self.finding(4, analyst="affected", score=4)
        potential = self.finding(5, automatic="potential", score=8)
        unresolved = self.finding(6, score=10)
        not_affected = self.finding(7, automatic="not_affected", score=10)
        for finding in (not_affected, unresolved, potential, confirmed, overdue):
            issue = ensure_vulnerability_issue(finding)
            if finding == overdue:
                issue.action_due = timezone.localdate() - timedelta(days=1)
                issue.save()
        response = self.client.get(reverse("overview"))
        problems = response.context["priority_assets"][0]["problems"]
        self.assertEqual(
            [p["title"] for p in problems],
            [f.record.external_id for f in (overdue, confirmed, potential, unresolved)],
        )
        self.assertEqual(problems[2]["review"]["version"], "1.2.3")
        self.assertIn("potential match", problems[2]["review"]["reason"])
        self.assertEqual(problems[2]["review"]["severity"], "High")

    def test_legacy_review_preview_is_ordered_and_closed_reviews_drop_out(self):
        self.finding(8, score=1)
        confirmed = self.finding(9, analyst="affected")
        response = self.client.get(reverse("overview"))
        self.assertEqual(
            response.context["priority_assets"][0]["problems"][0]["title"], confirmed.record.external_id
        )
        Finding.objects.filter(organization=self.a).update(status="resolved")
        response = self.client.get(reverse("overview"))
        self.assertEqual(response.context["priority_assets"], [])

    def test_saved_uncertain_assessment_is_not_labelled_unassessed(self):
        finding = self.finding(10, analyst="unknown")
        ensure_vulnerability_issue(finding)
        response = self.client.get(reverse("overview"))
        review = response.context["priority_assets"][0]["problems"][0]["review"]
        self.assertEqual(review["assessment"], "Uncertain (analyst assessment)")
