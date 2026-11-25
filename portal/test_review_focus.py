"""Machine-based denominators, scoped grouping and live evidence drill-down."""

from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
from django.urls import reverse
from django.utils import timezone
from .test_evaluation_presentation import EvaluationTests
from .models import AgentDevice, Asset, Finding
from .review_focus import posture, cases, case_scope
from .test_package_verdicts import save_browser_evidence
from .circl import findings_for, outstanding


class FocusTests(EvaluationTests):
    def test_current_machine_denominator_excludes_ip_records_and_missing_coverage(self):
        self.cached()
        self.prepare()
        baseline = posture(self.reader, [self.a.pk])["national"]
        self.assertEqual(baseline["evaluated_count"], 1)
        self.assertEqual(baseline["affected"]["count"], 1)
        self.assertEqual(baseline["affected"]["percent"], 100)
        Asset.objects.create(organization=self.a, source=self.sa, name="unreported", kind="server")
        Asset.objects.create(
            organization=self.a,
            source=self.sa,
            name="192.0.2.99",
            kind="ip_address",
            object_type="ipam.ipaddress",
        )
        next_state = posture(self.reader, [self.a.pk])["national"]
        self.assertEqual(next_state["total"], baseline["total"] + 1)
        self.assertEqual(next_state["affected"], baseline["affected"])
        self.assertEqual(next_state["missing"], baseline["missing"] + 1)
        AgentDevice.objects.filter(pk=self.device.pk).update(
            last_observed_at=timezone.now() - timedelta(days=1)
        )
        stale = posture(self.reader, [self.a.pk])["national"]
        self.assertEqual(stale["evaluated_count"], 0)
        self.assertIsNone(stale["affected"]["percent"])

    def test_bundle_links_preserve_scope_and_manual_evidence_is_separate(self):
        self.cached()
        self.prepare()
        self.login(self.analyst)
        url = reverse("circl-findings")
        response = self.client.get(url)
        save_browser_evidence("focus-cases", response)
        self.assertContains(response, "Software follow-up cases")
        group = response.context["page"].object_list[0]
        self.assertEqual(group["case_kind"], "version")
        self.assertEqual(group["machines"], 1)
        detail = self.client.get(group["url"])
        self.assertEqual(detail.context["page"].paginator.count, 1)
        self.assertContains(detail, "Affected package version")
        self.login(self.reader)
        org_url = reverse("organization-cases", args=[self.a.slug])
        own = self.client.get(org_url)
        self.assertEqual(own.status_code, 200)
        own_detail = self.client.get(own.context["page"].object_list[0]["url"])
        self.assertEqual(own_detail.status_code, 200)
        machines = self.client.get(reverse("organization-machines", args=[self.a.slug]), {"focus": "matched"})
        self.assertEqual(machines.context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("national-machines")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("organization-machines", args=[self.b.slug])).status_code, 404
        )

        self.assertEqual(self.client.get(reverse("organization-cases", args=[self.b.slug])).status_code, 404)
        token = parse_qs(urlsplit(group["url"]).query)["case"][0]
        self.assertEqual(
            self.client.get(org_url, {"view": "records", "case": token + "bad"}).status_code, 400
        )
        self.assertEqual(posture(self.reader, [self.b.pk])["national"]["total"], 0)

    def test_same_family_bundles_records_without_merging_versions_or_human_decisions(self):
        self.cached()
        self.prepare()
        finding = Finding.objects.get()
        # A second evidence source is kept, while the same machine still counts once.
        from .models import SourceRecord

        record = SourceRecord.objects.create(
            organization=self.a,
            source="https://example.invalid/synthetic",
            external_id="CVE-2099-55555",
            payload={},
            shareable=True,
        )
        Finding.objects.create(
            organization=self.a,
            installation=finding.installation,
            record=record,
            rule="synthetic-manual",
            applicability="unknown",
        )
        rows = list(cases(outstanding(findings_for(self.reader)), 1))
        self.assertEqual({r["case_kind"] for r in rows}, {"version", "manual"})
        self.assertEqual(posture(self.reader, [self.a.pk])["national"]["affected"]["count"], 1)
        finding.refresh_from_db()
        self.assertEqual(finding.analyst_applicability, "unassessed")
        self.login(self.reader)
        manual = self.client.get(reverse("organization-cases", args=[self.a.slug]), {"category": "manual"})
        self.assertContains(manual, "Check version applicability")
        self.assertEqual(manual.context["page"].paginator.count, 1)

    def test_saved_not_affected_assessment_overrides_version_case_grouping(self):
        self.cached()
        self.prepare()
        finding = Finding.objects.get()
        assessment = case_scope(findings_for(self.reader)).values("case_kind", "queue_bucket")
        self.assertEqual(assessment.get(pk=finding.pk)["case_kind"], "version")
        Finding.objects.filter(pk=finding.pk).update(analyst_applicability="not_affected")
        self.assertEqual(assessment.get(pk=finding.pk), {"case_kind": "cleared", "queue_bucket": "cleared"})

    def test_attention_defaults_to_machine_teasers_and_keeps_the_grouped_view(self):
        self.cached()
        self.prepare()
        self.login(self.reader)
        response = self.client.get(reverse("company-actions"), {"organization": self.a.slug})
        self.assertEqual(response.status_code, 200)
        save_browser_evidence("focus-attention", response)
        self.assertContains(response, "Current distribution-version match")
        self.assertContains(response, "Version match")
        self.assertContains(response, "nginx")
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.login(self.analyst)
        national = self.client.get(reverse("circl-panel", args=["summary"]))
        self.assertContains(national, "currently evaluated machines")
        save_browser_evidence("focus-national", national)
        self.login(self.reader)
        grouped = self.client.get(reverse("company-actions"), {"view": "groups", "organization": self.a.slug})
        self.assertEqual(grouped.status_code, 200)
        self.assertContains(grouped, "Grouped actions")
        self.assertEqual(
            self.client.get(reverse("company-actions"), {"organization": self.b.slug}).status_code, 404
        )
        self.assertEqual(self.client.get(reverse("company-actions"), {"view": "invalid"}).status_code, 400)
