"""Exact problem navigation and automatically explained, reviewable risk hypotheses."""

import uuid
from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import (
    Asset,
    AssetIssue,
    MOSPRisk,
    MOSPRiskRevision,
    MOSPSource,
    RiskLink,
    IssueRiskLink,
    BusinessRiskRevision,
)
from .issues import ensure_vulnerability_issue
from .intelligence import digest
from .scenario_suggestions import draft_scenario, catalog_suggestions
from .scenario_views import confirm


class ProblemNavigationTests(Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.finding.analyst_applicability = "affected"
        self.finding.save()
        self.issue = ensure_vulnerability_issue(self.finding)
        self.issue.action_due = timezone.localdate() - timedelta(days=1)
        self.issue.next_action = "Review and test vendor update"
        self.issue.save()
        self.lifecycle = []
        for kind in ["support", "warranty"]:
            self.lifecycle.append(
                AssetIssue.objects.create(
                    organization=self.a,
                    asset=self.asset,
                    kind=kind,
                    title=f"Distinct {kind} problem",
                    source_label="Synthetic evidence",
                    evidence_text="Reported expiry",
                    priority="high",
                    action_due=timezone.localdate() - timedelta(days=2),
                    next_action="Same action, separate problem",
                )
            )
        self.login()

    def test_cards_link_each_actual_problem_action_scenario_and_exact_badge_set(self):
        response = self.client.get(reverse("overview"))
        row = response.context["priority_assets"][0]
        for issue in [self.issue, *self.lifecycle]:
            self.assertContains(response, self.url("issue", pk=issue.pk))
            self.assertContains(response, self.url("automatic-scenario", pk=issue.pk))
        self.assertEqual(len(row["problems"]), 3)
        self.assertEqual(self.client.get(row["links"]["overdue"]).context["page"].paginator.count, 3)
        self.assertEqual(self.client.get(row["links"]["lifecycle"]).context["page"].paginator.count, 2)
        self.assertEqual(self.client.get(row["links"]["affected"]).context["page"].paginator.count, 1)
        self.assertContains(response, "Automatic risk scenario")

    def test_asset_filters_use_identity_not_ambiguous_names_and_reject_foreign_ids(self):
        other = Asset.objects.create(organization=self.a, source=self.sa, name=self.asset.name, kind="server")
        AssetIssue.objects.create(
            organization=self.a,
            asset=other,
            kind="eol",
            title="Must not match same name",
            source_label="Synthetic",
            evidence_text="Expiry",
            action_due=timezone.localdate() - timedelta(days=1),
        )
        path = reverse("issues")
        response = self.client.get(
            path, {"asset": str(self.asset.pk), "attention": "overdue", "organization": self.a.slug}
        )
        self.assertEqual(response.context["page"].paginator.count, 3)
        self.assertNotContains(response, "Must not match same name")
        for key in [str(self.other.pk), "invalid-uuid"]:
            self.assertEqual(self.client.get(path, {"asset": key}).status_code, 404)
            self.assertEqual(self.client.get(self.url("intelligence"), {"asset": key}).status_code, 404)
        self.assertEqual(
            self.client.get(path, {"asset": str(other.pk), "organization": self.b.slug}).status_code, 404
        )

    def test_legacy_cve_without_common_issue_still_has_exact_deep_link(self):
        self.issue.finding = None
        self.issue.kind = "other"
        self.issue.save()
        response = self.client.get(reverse("overview"))
        self.assertContains(response, f"?finding={self.finding.pk}#finding-{self.finding.pk}")
        row = response.context["priority_assets"][0]
        self.assertEqual(self.client.get(row["links"]["reviews"]).context["page"].paginator.count, 1)

    def test_restricted_problem_does_not_leak_through_links_scenarios_or_lists(self):
        self.finding.record.shareable = False
        self.finding.record.save()
        self.login(self.reader)
        response = self.client.get(reverse("overview"))
        self.assertNotContains(response, self.url("issue", pk=self.issue.pk))
        self.assertNotContains(response, self.finding.record.external_id)
        self.assertEqual(self.client.get(self.url("automatic-scenario", pk=self.issue.pk)).status_code, 404)
        filtered = self.client.get(reverse("issues"), {"asset": str(self.asset.pk), "attention": "overdue"})
        self.assertEqual(filtered.context["page"].paginator.count, 2)

    def test_issue_and_cve_pagination_retain_exact_asset_and_attention_filters(self):
        for i in range(26):
            AssetIssue.objects.create(
                organization=self.a,
                asset=self.asset,
                kind="support",
                title=f"Support {i}",
                source_label="Synthetic",
                evidence_text="Reported",
                action_due=timezone.localdate() - timedelta(days=1),
            )
        response = self.client.get(reverse("issues"), {"asset": str(self.asset.pk), "attention": "overdue"})
        self.assertContains(response, 'name="asset"')
        self.assertIn(str(self.asset.pk), response.context["filters"])
        self.assertIn("attention=overdue", response.context["filters"])


class AutomaticScenarioTests(Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.finding.record.payload = {
            "cveMetadata": {"cveId": self.finding.record.external_id},
            "containers": {
                "cna": {
                    "problemTypes": [{"descriptions": [{"cweId": "CWE-502"}]}],
                    "descriptions": [
                        {"lang": "en", "value": "Unsafe deserialization may allow arbitrary code execution."}
                    ],
                }
            },
        }
        self.finding.record.save()
        self.issue = ensure_vulnerability_issue(self.finding)
        self.source = MOSPSource.objects.create(name="Public catalog contract")
        self.risk = self.make_risk()
        self.revision = MOSPRiskRevision.objects.create(
            risk=self.risk,
            content_hash=digest({"version": 1}),
            risk_hash=self.risk.content_hash,
            payload={
                "risk": self.risk.payload,
                "asset": {"name": "Server"},
                "threat": {"name": "Malware infection"},
                "vulnerability": {"name": "Update management (patches) is flawed"},
            },
        )
        self.risk.current_revision = self.revision
        self.risk.save()
        self.login()
        self.path = self.url("automatic-scenario", pk=self.issue.pk)

    def make_risk(
        self,
        *,
        description="Asset: Server. Threat: Malware infection. Vulnerability: Update management (patches) is flawed",
        **overrides,
    ):
        data = {"publisher": "MONARC", "licenses": ["CC0-1.0"]}
        return MOSPRisk.objects.create(
            source=self.source,
            uuid=uuid.uuid4(),
            external_id=MOSPRisk.objects.count() + 1,
            description=description,
            payload=overrides.get("payload", data),
            content_hash=digest(data),
        )

    def values(self):
        draft = draft_scenario(self.issue)
        return {
            "risk": self.risk.pk,
            "reviewed_revision": self.revision.pk,
            "reviewed_draft": draft["fingerprint"],
            "reason": draft["reason"],
        }

    def test_source_weakness_generates_conditional_scenario_without_asserting_affectedness_or_score(self):
        draft = draft_scenario(self.issue)
        self.assertEqual(draft["profile"], "execution")
        self.assertIn("CWE-502", draft["basis"])
        self.assertIn("If this installation", draft["consequence"])
        self.assertIn("does not establish flawed company processes", draft["assumptions"])
        self.assertNotIn("likelihood", draft)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.analyst_applicability, "unassessed")
        self.finding.record.payload = {}
        self.finding.record.save()
        self.finding.installation.product.name = "Apache Log4j"
        self.assertEqual(draft_scenario(self.issue)["profile"], "vulnerability")

    def test_support_and_contract_issues_have_distinct_scenarios(self):
        self.issue.finding = None
        self.issue.kind = "support"
        self.assertEqual(draft_scenario(self.issue)["profile"], "support")
        self.issue.kind = "license"
        draft = draft_scenario(self.issue)
        self.assertEqual(draft["profile"], "entitlement")
        self.assertIn("Vendor lifecycle facts alone", draft["consequence"])

    def test_catalog_recommendations_require_matching_asset_enabled_cc0_and_exclude_fixtures(self):
        self.make_risk(description="Asset: Desktop computer. Threat: Malware infection.")
        self.make_risk(payload={"publisher": "MONARC", "licenses": ["proprietary"]})
        self.make_risk(payload={"publisher": "MONARC", "licenses": ["CC0-1.0"], "fixture": True})
        self.assertEqual([c["risk"].pk for c in catalog_suggestions(self.issue)], [self.risk.pk])
        self.source.enabled = False
        self.source.save()
        self.assertEqual(catalog_suggestions(self.issue), [])

    @patch("portal.scenario_views.resolve_risk")
    def test_draft_and_cached_preview_are_read_only_and_auto_justification_is_prefilled(self, remote):
        response = self.client.get(self.path)
        self.assertContains(response, "Automatically generated")
        self.assertContains(response, "Unauthorized code execution")
        self.assertFalse(RiskLink.objects.exists())
        self.assertFalse(BusinessRiskRevision.objects.exists())
        response = self.client.get(self.path, {"risk": self.risk.pk})
        self.assertContains(response, "Automatic scenario draft")
        remote.assert_not_called()

    @patch("portal.scenario_views.resolve_risk")
    def test_confirm_pins_original_evidence_and_is_idempotent_without_auto_assessment(self, remote):
        remote.return_value = self.revision
        response = self.client.post(self.path, self.values())
        self.assertRedirects(response, self.url("business-risk", pk=self.issue.pk))
        link = RiskLink.objects.get()
        self.assertEqual(link.evidence_revision.record_id, self.finding.record_id)
        self.assertIn("asset-evidence-scenario/v1", link.reason)
        self.client.post(self.path, self.values())
        self.assertEqual(RiskLink.objects.count(), 1)
        self.assertFalse(BusinessRiskRevision.objects.exists())
        form = self.client.get(self.url("business-risk", pk=self.issue.pk)).context["form"]
        self.assertIn("attacker", form["business_impact"].value())
        self.assertIsNone(form["likelihood"].value())

    @patch("portal.scenario_views.resolve_risk")
    def test_stale_source_and_catalog_changes_block_confirmation_and_keep_reason(self, remote):
        values = self.values()
        self.issue.next_action = "New reviewed action"
        self.issue.save()
        response = self.client.post(self.path, values)
        self.assertContains(response, "Issue or source evidence changed")
        remote.assert_not_called()
        values = self.values()
        second = MOSPRiskRevision.objects.create(
            risk=self.risk,
            content_hash=digest({"version": 2}),
            risk_hash=self.risk.content_hash,
            payload=self.revision.payload,
        )
        self.risk.current_revision = second
        self.risk.save()
        remote.return_value = second
        response = self.client.post(self.path, values)
        self.assertContains(response, "catalog scenario changed")
        self.assertEqual(response.context["form"]["reason"].value(), values["reason"])
        self.assertFalse(RiskLink.objects.exists())

    @patch("portal.scenario_views.resolve_risk")
    def test_policy_revocation_and_reader_foreign_access_are_checked_before_source_io(self, remote):
        self.login(self.reader)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertEqual(self.client.post(self.path, self.values()).status_code, 403)
        self.login()
        self.assertEqual(
            self.client.get(self.url("automatic-scenario", self.b, pk=self.issue.pk)).status_code, 404
        )
        self.finding.record.shareable = False
        self.finding.record.save()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        remote.assert_not_called()

    @patch("portal.scenario_views.resolve_risk")
    def test_non_cve_confirmation_links_issue_evidence_and_outages_keep_local_draft(self, remote):
        issue = AssetIssue.objects.create(
            organization=self.a,
            asset=self.asset,
            kind="support",
            title="Support review",
            source_label="Synthetic",
            evidence_text="Reported lifecycle",
        )
        self.risk.description = "Asset: Server. Threat: Unavailability. Vulnerability: Maintenance is flawed"
        self.risk.save()
        remote.return_value = self.revision
        draft = draft_scenario(issue)
        path = self.url("automatic-scenario", pk=issue.pk)
        response = self.client.post(
            path,
            {
                "risk": self.risk.pk,
                "reviewed_revision": self.revision.pk,
                "reviewed_draft": draft["fingerprint"],
                "reason": draft["reason"],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(IssueRiskLink.objects.get().issue_revision.issue_id, issue.pk)
        self.source.enabled = False
        self.source.save()
        response = self.client.get(path)
        self.assertContains(response, "local draft remains available")

    @patch("portal.scenario_views.resolve_risk")
    def test_mid_request_evidence_change_cannot_be_adopted(self, remote):
        values = self.values()

        def change(*args):
            AssetIssue.objects.filter(pk=self.issue.pk).update(next_action="Changed while source was read")
            return self.revision

        remote.side_effect = change
        with self.assertRaises(ValidationError):
            confirm(self.admin, self.issue, self.risk, values)
        self.assertFalse(RiskLink.objects.exists())

    @patch("portal.scenario_views.resolve_risk")
    def test_last_moment_cve_refresh_cannot_pin_unreviewed_source_evidence(self, remote):
        from .intelligence import link_resolved_risk
        from .models import SourceRecord

        remote.return_value = self.revision

        def refresh_before_pin(*args, **kwargs):
            SourceRecord.objects.filter(pk=self.finding.record_id).update(
                payload={"changed": "after preview guard"}
            )
            return link_resolved_risk(*args, **kwargs)

        with patch("portal.scenario_views.link_resolved_risk", side_effect=refresh_before_pin):
            with self.assertRaises(ValidationError):
                confirm(self.admin, self.issue, self.risk, self.values())
        self.assertFalse(RiskLink.objects.exists())

    def test_untrusted_issue_and_catalog_text_are_escaped(self):
        self.risk.description += '<script>alert("catalog")</script>'
        self.risk.save()
        response = self.client.get(self.path)
        self.assertNotContains(response, '<script>alert("catalog")</script>')
        self.assertContains(response, "&lt;script&gt;")

    @patch("portal.scenario_views.resolve_risk")
    def test_upstream_outage_keeps_draft_and_does_not_create_mapping(self, remote):
        from .connectors.http import ConnectorError

        remote.side_effect = ConnectorError("private source response")
        response = self.client.post(self.path, self.values())
        self.assertContains(response, "Catalog verification failed")
        self.assertContains(response, "Unauthorized code execution")
        self.assertNotContains(response, "private source response")
        self.assertFalse(RiskLink.objects.exists())

    @patch("portal.scenario_views.resolve_risk")
    def test_withdrawn_mapping_is_not_suggested_again_for_unchanged_evidence(self, remote):
        remote.return_value = self.revision
        self.client.post(self.path, self.values())
        link = RiskLink.objects.get()
        link.withdrawn_at = timezone.now()
        link.save()
        self.assertEqual(catalog_suggestions(self.issue), [])
        response = self.client.get(self.path)
        self.assertContains(response, "No compatible catalog suggestion")
