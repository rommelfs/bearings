"""Acceptance tests for discovery → ownership/outreach → company risk decisions."""

import copy
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from . import tests
from .business_risk import assess, evidence
from .connectors.http import ConnectorError
from .connectors.vulnerability_lookup import product_records
from .discovery import sync_watch, evaluate
from .intelligence import digest, snapshot_evidence
from .issues import ensure_vulnerability_issue
from .models import (
    Contact,
    DiscoveryMatch,
    Finding,
    MOSPRisk,
    MOSPRiskRevision,
    MOSPSource,
    OutreachPolicy,
    Product,
    ProductWatch,
    RiskLink,
)
from .notifications import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    approve_local,
    preview_batch,
    queue_campaign,
    process_queued_notifications,
)
from .outreach import prepare_followups
from .services import persist_lookup, transition_finding


def cve(identifier="CVE-2025-12345", *, version="1.0.0", limit="2.0.0"):
    return {
        "cveMetadata": {"cveId": identifier, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "affected": [
                    {
                        "vendor": "example",
                        "product": "server",
                        "versions": [
                            {
                                "version": version,
                                "lessThan": limit,
                                "versionType": "semver",
                                "status": "affected",
                            }
                        ],
                    }
                ]
            }
        },
    }


class DiscoveryAcceptance(tests.Fixture):
    def setUp(self):
        self.installation.version = "1.5.0"
        self.installation.save()
        self.watch = ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="server",
            source_url="https://vulnerability.circl.lu",
        )
        self.payload = cve()

    def sync(self, records=None):
        with patch(
            "portal.discovery.product_records",
            return_value=(
                self.watch.source_url,
                records if records is not None else [("CVE-2025-12345", self.payload)],
            ),
        ):
            return sync_watch(self.watch.pk)

    def test_discovery_creates_deduplicated_scoped_review_with_history_and_supported_range(self):
        self.assertEqual(self.sync()["changed"], 1)
        finding = Finding.objects.get()
        self.assertEqual(finding.applicability, "potential")
        self.assertEqual(finding.analyst_applicability, "unassessed")
        self.assertEqual(finding.organization, self.a)
        self.assertEqual(finding.asset_issue.asset, self.asset)
        self.assertEqual(self.sync()["changed"], 0)
        self.assertEqual(DiscoveryMatch.objects.get().history.count(), 1)
        self.assertEqual(Finding.objects.count(), 1)

    def test_existing_manual_identity_evidence_policy_and_analyst_decision_survive_changed_cve(self):
        manual = persist_lookup(
            self.admin, self.installation, self.watch.source_url, "CVE-2025-12345", self.payload
        )
        transition_finding(self.admin, manual, "resolved", "Vendor backport reviewed", "not_affected")
        manual.record.shareable = False
        manual.record.save()
        self.sync()
        self.payload["containers"]["cna"]["title"] = "Changed advisory"
        self.assertEqual(self.sync()["changed"], 1)
        manual.refresh_from_db()
        self.assertEqual(Finding.objects.count(), 1)
        self.assertEqual(manual.rule, "manual-cve-review/v1")
        self.assertEqual((manual.status, manual.analyst_applicability), ("resolved", "not_affected"))
        self.assertFalse(manual.record.shareable)
        self.assertTrue(manual.discovery.review_required)
        self.assertGreaterEqual(manual.record.revisions.count(), 2)
        self.login(self.reader)
        response = self.client.get(reverse("discovery"))
        self.assertContains(response, "0 new/changed visible reviews")
        self.assertNotContains(self.client.get(self.url("intelligence") + "?changed=1"), "CVE-2025-12345")

    def test_new_revision_is_reviewable_after_closed_workflow_without_resetting_decision(self):
        self.sync()
        finding = Finding.objects.get()
        transition_finding(self.admin, finding, "resolved", "Reviewed fix", "not_affected")
        self.payload["containers"]["cna"]["title"] = "New evidence"
        self.sync()
        self.login()
        self.assertContains(self.client.get(self.url("intelligence") + "?changed=1"), "CVE-2025-12345")
        self.assertContains(
            self.client.get(self.url("intelligence")),
            "New evidence needs review despite a saved assessment",
        )
        finding.refresh_from_db()
        self.assertEqual(finding.status, "resolved")

    def test_unknown_versions_unsupported_rules_boundaries_and_conflicts_stay_uncertain(self):
        for installed, kind, expected in [
            ("", "semver", "unknown"),
            ("1.5.0", "maven", "unknown"),
            ("2.0.0", "semver", "unknown"),
            ("1.5.0-beta1", "semver", "unknown"),
            ("1.5.0", "semver", "potential"),
        ]:
            with self.subTest(version=installed, kind=kind):
                payload = copy.deepcopy(self.payload)
                payload["containers"]["cna"]["affected"][0]["versions"][0]["versionType"] = kind
                self.installation.version = installed
                self.assertEqual(evaluate(self.watch, self.installation, payload)[0], expected)
        payload = copy.deepcopy(self.payload)
        payload["containers"]["cna"]["affected"][0]["versions"].append(
            {"version": "1.5.0", "status": "unaffected"}
        )
        self.assertEqual(evaluate(self.watch, self.installation, payload)[0], "unknown")

    def test_cpe_identity_matches_descriptive_vendor_names_but_not_similar_products(self):
        self.product.identifier = "cpe:2.3:a:example:server:*:*:*:*:*:*:*:*"
        payload = copy.deepcopy(self.payload)
        affected = payload["containers"]["cna"]["affected"][0]
        affected.update(
            vendor="Example Corporation", product="Example Server", cpes=[self.product.identifier]
        )
        self.assertEqual(evaluate(self.watch, self.installation, payload)[0], "potential")
        affected["cpes"] = ["cpe:2.3:a:example:server_plus:*:*:*:*:*:*:*:*"]
        self.assertEqual(evaluate(self.watch, self.installation, payload)[0], "unknown")

    def test_failure_and_missing_results_preserve_last_success_and_local_reviews(self):
        self.sync()
        self.watch.refresh_from_db()
        success = self.watch.last_success
        with patch("portal.discovery.product_records", side_effect=ConnectorError("sensitive response")):
            with self.assertRaises(ConnectorError):
                sync_watch(self.watch.pk)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.last_success, success)
        self.assertNotIn("sensitive", self.watch.error)
        self.assertEqual(self.sync([])["retained_missing"], 1)
        self.assertEqual(Finding.objects.count(), 1)

    def test_changed_product_identifier_reevaluates_and_preserves_input_history(self):
        self.sync()
        self.product.identifier = "pkg:generic/example-server"
        self.product.save()
        self.assertEqual(self.sync()["changed"], 1)
        self.assertEqual(DiscoveryMatch.objects.get().history.count(), 2)

    def test_configuration_scope_pause_queue_and_version_change(self):
        self.login(self.reader)
        self.assertEqual(
            self.client.post(self.url("discovery-configure", pk=self.product.pk), {}).status_code, 403
        )
        self.login()
        response = self.client.post(
            self.url("discovery-configure", pk=self.product.pk),
            {
                "vendor": "example",
                "product_key": "server",
                "enabled": "on",
                "interval_minutes": 60,
                "source_url": "https://evil.invalid",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.source_url, "https://vulnerability.circl.lu")
        foreign = Product.objects.create(organization=self.b, name="Other")
        self.assertEqual(self.client.get(self.url("discovery-configure", pk=foreign.pk)).status_code, 404)
        self.client.post(
            self.url("installation-version", pk=self.installation.pk),
            {"version": "1.6.0", "build": "vendor-backport", "edition": ""},
        )
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "1.6.0")
        self.watch.enabled = False
        self.watch.save()
        with patch("portal.discovery.product_records") as upstream:
            sync_watch(self.watch.pk)
            upstream.assert_not_called()

    def test_due_scheduler_skips_recent_watches_and_refreshes_queued(self):
        self.sync()
        with patch("portal.discovery.product_records", return_value=(self.watch.source_url, [])) as upstream:
            call_command("sync_vulnerabilities", due=True)
            upstream.assert_not_called()
            ProductWatch.objects.filter(pk=self.watch.pk).update(requested=True)
            call_command("sync_vulnerabilities", due=True)
            self.assertEqual(upstream.call_count, 1)

    def test_current_live_contract_and_partial_changing_duplicate_pages(self):
        def pair(i):
            identifier = f"CVE-2025-{10000 + i}"
            return [identifier.lower(), cve(identifier)]

        with (
            patch("portal.connectors.vulnerability_lookup.approved_base", return_value=self.watch.source_url),
            patch("portal.connectors.vulnerability_lookup.request_json") as http,
        ):
            http.side_effect = [
                {
                    "results": {"cvelistv5": [pair(i) for i in range(100)]},
                    "total_count": 101,
                    "page_size": 100,
                    "page": 1,
                },
                {"results": {"cvelistv5": [pair(100)]}, "total_count": 101, "page_size": 100, "page": 2},
            ]
            self.assertEqual(len(product_records(self.watch)[1]), 101)
            self.assertTrue(all(call.args[0] == "GET" for call in http.call_args_list))
            for response in [
                {
                    "cvelistv5": [
                        [
                            "CVE-2025-12345",
                            {
                                "cveMetadata": {"cveId": "CVE-2025-12345", "state": "PUBLISHED"},
                                "containers": [],
                            },
                        ]
                    ]
                },
                {"cvelistv5": [["CVE-2025-12345", {"cveMetadata": {"cveId": None, "state": "REJECTED"}}]]},
                {"results": {"cvelistv5": []}, "total_count": 1, "page_size": 100, "page": 1},
                {"results": {}, "total_count": 2001, "page_size": 100, "page": 1},
                {"cvelistv5": [pair(1), pair(1)]},
                {"cvelistv5": [["CVE-2025-10000", cve("CVE-2025-10001")]]},
            ]:
                http.side_effect, http.return_value = None, response
                with self.assertRaises(ConnectorError):
                    product_records(self.watch)


class OutreachAcceptance(tests.Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.contact.notification_enabled = True
        self.contact.reachable_at = self.contact.reviewed_at = timezone.now()
        self.contact.next_review = timezone.localdate() + timedelta(days=30)
        self.contact.save()
        self.dpo = Contact.objects.create(
            organization=self.a,
            name="DPO",
            function="dpo",
            email="dpo@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=30),
        )
        self.manager = Contact.objects.create(
            organization=self.a,
            name="Management",
            function="management",
            escalation_order=2,
            email="manager@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=30),
        )
        self.filters = {"organization": self.a.pk, "sort": "severity"}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings = override_settings(EMAIL_FILE_PATH=Path(self.directory.name))
        settings.enable()
        self.addCleanup(settings.disable)

    def preview(self, filters=None):
        return preview_batch(self.admin, "company", filters or self.filters, DEFAULT_SUBJECT, DEFAULT_BODY)

    def test_optional_dpo_preview_policy_and_blocker(self):
        batch = self.preview()
        self.assertFalse(batch.deliveries.filter(contact=self.dpo).exists())
        batch = self.preview({**self.filters, "include_dpo": True})
        self.assertTrue(batch.deliveries.filter(contact=self.dpo).exists())
        self.dpo.reachable_at = None
        self.dpo.save()
        with self.assertRaises(ValidationError):
            self.preview({**self.filters, "include_dpo": True})
        OutreachPolicy.objects.create(organization=self.a, include_dpo=True)
        with self.assertRaises(ValidationError):
            self.preview()

    def test_new_company_dpo_policy_invalidates_an_older_security_only_preview(self):
        batch = self.preview()
        OutreachPolicy.objects.create(organization=self.a, include_dpo=True)
        with self.assertRaises(ValidationError):
            queue_campaign(self.admin, batch.pk, set(batch.deliveries.values_list("pk", flat=True)))

    def test_disabled_timed_policy_blocks_a_queued_followup(self):
        original = self.original()
        policy = OutreachPolicy.objects.create(organization=self.a, reminder_days=1)
        prepare_followups(original.pk)
        reminder = original.followups.get(kind="reminder").batch
        queue_campaign(self.admin, reminder.pk, set(reminder.deliveries.values_list("pk", flat=True)))
        policy.reminder_days = 0
        policy.save()
        with patch("portal.notifications.EmailMessage.send") as send:
            process_queued_notifications()
            send.assert_not_called()

    def test_changed_contact_role_or_consent_blocks_queued_transport(self):
        batch = self.preview({**self.filters, "include_dpo": True})
        queue_campaign(self.admin, batch.pk, set(batch.deliveries.values_list("pk", flat=True)))
        self.dpo.notification_enabled = False
        self.dpo.save()
        with patch("portal.notifications.EmailMessage.send") as send:
            process_queued_notifications()
            send.assert_not_called()
        self.assertTrue(batch.deliveries.filter(status="uncertain").exists())

    def original(self):
        batch = self.preview()
        delivery = batch.deliveries.get(contact=self.contact)
        approve_local(self.admin, batch.pk, {delivery.pk})
        delivery.refresh_from_db()
        delivery.filed_at = timezone.now() - timedelta(days=4)
        delivery.save()
        return delivery

    def test_timed_reminder_and_escalation_are_idempotent_private_drafts(self):
        original = self.original()
        OutreachPolicy.objects.create(organization=self.a, reminder_days=1, escalation_days=3)
        with patch("portal.notifications.EmailMessage.send") as send:
            self.assertEqual(prepare_followups(original.pk), 2)
            self.assertEqual(prepare_followups(original.pk), 0)
            send.assert_not_called()
        reminder = original.followups.get(kind="reminder").batch
        escalation = original.followups.get(kind="escalation").batch
        self.assertEqual(reminder.status, "draft")
        self.assertEqual(list(reminder.deliveries.values_list("contact_id", flat=True)), [self.contact.pk])
        self.assertEqual(list(escalation.deliveries.values_list("contact_id", flat=True)), [self.manager.pk])
        self.assertNotEqual(reminder.deliveries.get().fingerprint, original.fingerprint)

    def test_acknowledgment_cancels_drafts_and_blocks_already_queued_followup(self):
        original = self.original()
        OutreachPolicy.objects.create(organization=self.a, reminder_days=1, escalation_days=3)
        prepare_followups(original.pk)
        reminder = original.followups.get(kind="reminder").batch
        queue_campaign(self.admin, reminder.pk, set(reminder.deliveries.values_list("pk", flat=True)))
        original.acknowledged_at = timezone.now()
        original.save()
        prepare_followups(original.pk)
        self.assertEqual(original.followups.get(kind="escalation").batch.status, "cancelled")
        with patch("portal.notifications.EmailMessage.send") as send:
            process_queued_notifications()
            send.assert_not_called()

    def test_later_escalation_is_not_lost_after_first_reminder_and_command_fairness(self):
        original = self.original()
        original.filed_at = timezone.now() - timedelta(days=2)
        original.save()
        OutreachPolicy.objects.create(organization=self.a, reminder_days=1, escalation_days=3)
        call_command("prepare_followups")
        self.assertEqual(original.followups.count(), 1)
        original.filed_at = timezone.now() - timedelta(days=4)
        original.save()
        call_command("prepare_followups")
        self.assertEqual(original.followups.count(), 2)

    def test_revoked_operator_scope_blocks_followup_and_preserves_explanation(self):
        batch = preview_batch(self.analyst, "circl", self.filters, DEFAULT_SUBJECT, DEFAULT_BODY)
        delivery = batch.deliveries.get(contact=self.contact)
        approve_local(self.analyst, batch.pk, {delivery.pk})
        delivery.refresh_from_db()
        delivery.filed_at = timezone.now() - timedelta(days=4)
        delivery.save()
        OutreachPolicy.objects.create(organization=self.a, reminder_days=1)
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(prepare_followups(delivery.pk), 0)
        row = delivery.followups.get()
        self.assertIsNone(row.batch)
        self.assertIn("blocked", row.error)

    def test_asset_contact_is_local_and_policy_requires_company_admin(self):
        self.login()
        foreign = Contact.objects.create(organization=self.b, name="Other", email="other@example.invalid")
        response = self.client.post(
            self.url("edit-local-asset", pk=self.asset.pk),
            {
                "criticality": "normal",
                "lifecycle": "active",
                "responsible_team": "Ops",
                "responsible_contact": foreign.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.asset.refresh_from_db()
        self.assertIsNone(self.asset.responsible_contact_id)
        response = self.client.post(
            self.url("edit-local-asset", pk=self.asset.pk),
            {
                "criticality": "normal",
                "lifecycle": "active",
                "responsible_team": "Ops",
                "responsible_contact": self.contact.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertContains(
            self.client.get(self.url("asset", pk=self.asset.pk)), "mailto:security@example.invalid"
        )
        for actor in [self.editor, self.analyst, self.reader]:
            self.login(actor)
            self.assertEqual(
                self.client.post(self.url("outreach-policy"), {"include_dpo": "on"}).status_code, 403
            )


class CompanyRiskAcceptance(tests.Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.issue = ensure_vulnerability_issue(self.finding)
        self.source = MOSPSource.objects.create(name="Test public catalog")
        self.risk = MOSPRisk.objects.create(
            source=self.source,
            uuid="aaaaaaaa-0000-0000-0000-000000000001",
            external_id=1,
            description="Business service unavailable",
            payload={},
            content_hash=digest({}),
        )
        self.revision = MOSPRiskRevision.objects.create(
            risk=self.risk, content_hash="a" * 64, risk_hash=digest({}), payload={"fixture": True}
        )
        self.risk.current_revision = self.revision
        self.risk.save()
        self.link = RiskLink.objects.create(
            finding=self.finding,
            evidence_revision=snapshot_evidence(self.finding.record),
            risk_revision=self.revision,
            reason="Review service outage",
            created_by=self.admin,
        )

    def values(self, **overrides):
        latest = self.issue.business_risks.first()
        values = {
            "previous_revision": latest.pk if latest else 0,
            "reviewed_evidence": digest(evidence(self.issue)),
            "scenario": f"cve:{self.link.pk}",
            "business_process": "Customer portal",
            "business_impact": "Loss of customer access and revenue",
            "assumptions": "Internet-facing; exact build still requires confirmation",
            "likelihood": 4,
            "impact": 4,
            "existing_controls": "Restricted management access",
            "planned_measures": "Validate vendor patch and deploy",
            "residual_likelihood": 2,
            "residual_impact": 3,
            "residual_rationale": "Estimate assumes successful patch validation",
            "decision": "mitigate",
            "owner": self.contact.pk,
            "action_due": (timezone.localdate() + timedelta(days=7)).isoformat(),
            "acceptance_until": "",
            "reason": "Review of service context",
        }
        return {**values, **overrides}

    def test_assessment_pins_context_calculates_documented_local_matrix_and_retains_history(self):
        first = assess(self.admin, self.issue, self.values())
        self.assertEqual((first.snapshot["score"], first.snapshot["band"]), (16, "High"))
        self.assertEqual(first.snapshot["residual_score"], 6)
        self.assertEqual(first.snapshot["risk_revision"], self.revision.pk)
        self.assertTrue(first.snapshot["cve_revision"])
        second = assess(self.admin, self.issue, self.values(likelihood=3, reason="Reviewed controls"))
        self.assertEqual(second.previous, first)
        first.refresh_from_db()
        self.assertEqual(first.snapshot["likelihood"], 4)
        self.assertEqual(self.issue.business_risks.count(), 2)

    def test_only_company_admin_accepts_risk_with_expiry_and_reason(self):
        values = self.values(
            decision="accept", acceptance_until=(timezone.localdate() + timedelta(days=30)).isoformat()
        )
        for actor in [self.editor, self.analyst]:
            with self.assertRaises(PermissionDenied):
                assess(actor, self.issue, values)
        accepted = assess(self.admin, self.issue, values)
        self.assertEqual(accepted.snapshot["accepted_by"], self.admin.pk)
        with self.assertRaises(ValidationError):
            assess(self.admin, self.issue, self.values(decision="accept", acceptance_until=""))

    def test_changed_evidence_withdrawn_scenarios_and_stale_concurrent_edits_block_save(self):
        stale_values = self.values()
        assess(self.admin, self.issue, stale_values)
        with self.assertRaises(ValidationError):
            assess(self.admin, self.issue, stale_values)
        self.finding.record.payload = {"updated": "evidence"}
        self.finding.record.save()
        with self.assertRaises(ValidationError):
            assess(self.admin, self.issue, self.values())
        self.link.withdrawn_at = timezone.now()
        self.link.save()
        with self.assertRaises(ValidationError):
            assess(self.admin, self.issue, self.values())

    def test_restricted_raw_and_derived_risk_hidden_from_participants_and_revoked_analysts(self):
        assess(self.admin, self.issue, self.values())
        self.finding.record.shareable = False
        self.finding.record.save()
        for actor in [self.admin, self.reader]:
            self.login(actor)
            self.assertEqual(
                self.client.get(self.url("business-risk", pk=self.issue.pk) + "?format=json").status_code, 404
            )
        self.login(self.analyst)
        self.assertEqual(
            self.client.get(self.url("business-risk", pk=self.issue.pk) + "?format=json").status_code, 200
        )
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.url("business-risk", pk=self.issue.pk)).status_code, 404)

    def test_risk_ui_post_json_history_escaping_and_foreign_contact(self):
        self.login()
        url = self.url("business-risk", pk=self.issue.pk)
        self.assertContains(self.client.get(url), "local 5×5 matrix")
        self.assertContains(self.client.get(url), "Security · Security · security@example.invalid")
        response = self.client.post(url, self.values(business_process="<script>alert(1)</script>"))
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(self.client.get(url), "<script>alert(1)</script>")
        self.assertEqual(len(self.client.get(url + "?format=json").json()["revisions"]), 1)
        foreign = Contact.objects.create(organization=self.b, name="Foreign", email="foreign@example.invalid")
        with self.assertRaises(ValidationError):
            assess(self.admin, self.issue, self.values(owner=foreign.pk))
        self.login(self.reader)
        self.assertEqual(self.client.post(url, self.values()).status_code, 403)

    def test_inventory_change_marks_historical_risk_for_review_without_mutation(self):
        revision = assess(self.admin, self.issue, self.values())
        self.asset.criticality = "high"
        self.asset.save()
        self.login()
        self.assertContains(
            self.client.get(self.url("business-risk", pk=self.issue.pk)), "changed since this assessment"
        )
        revision.refresh_from_db()
        self.assertEqual(revision.snapshot["evidence"]["asset"]["criticality"], "normal")

    def test_risk_register_shows_only_latest_visible_assessment_and_filter(self):
        assess(self.admin, self.issue, self.values())
        assess(self.admin, self.issue, self.values(business_process="Updated business process"))
        self.login(self.analyst)
        response = self.client.get(reverse("risk-register"))
        self.assertContains(response, "Updated business process")
        self.assertContains(response, "1 assessed issues")
        self.assertNotContains(
            self.client.get(reverse("risk-register") + "?decision=accept"), "Updated business process"
        )
        self.finding.record.shareable = False
        self.finding.record.save()
        self.login(self.reader)
        self.assertNotContains(self.client.get(reverse("risk-register")), "Updated business process")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row-lock semantics")
class ContinuousReviewConcurrency(TransactionTestCase):
    record_finding = tests.Fixture.record_finding

    def setUp(self):
        tests.Fixture.setUpTestData.__func__(type(self))

    def race(self, action):
        def worker(_):
            close_old_connections()
            try:
                return action()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, range(2)))

    def test_product_workers_commit_one_evaluation_and_one_finding(self):
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="server",
            source_url="https://vulnerability.circl.lu",
        )
        with patch(
            "portal.discovery.product_records", return_value=(watch.source_url, [("CVE-2025-12345", cve())])
        ) as upstream:
            results = self.race(lambda: sync_watch(watch.pk, due=True))
        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(results.count(None), 1)
        self.assertEqual(Finding.objects.count(), 1)
        self.assertEqual(DiscoveryMatch.objects.get().history.count(), 1)

    def test_risk_workers_preserve_one_current_decision_and_reject_stale_edit(self):
        # Reuse the realistic scenario/evidence setup without inheriting its test methods.
        CompanyRiskAcceptance.setUp(self)
        values = CompanyRiskAcceptance.values(self)

        def save():
            try:
                return assess(self.admin, self.issue, values).pk
            except ValidationError:
                return "stale"

        results = self.race(save)
        self.assertEqual(results.count("stale"), 1)
        self.assertEqual(self.issue.business_risks.count(), 1)

    def test_followup_workers_prepare_each_stage_once(self):
        self.contact.notification_enabled = True
        self.contact.reviewed_at = self.contact.reachable_at = timezone.now()
        self.contact.next_review = timezone.localdate() + timedelta(days=30)
        self.contact.save()
        record = tests.Fixture.record_finding(self)
        self.assertEqual(record.organization, self.a)
        batch = preview_batch(
            self.admin, "company", {"organization": self.a.pk}, DEFAULT_SUBJECT, DEFAULT_BODY
        )
        delivery = batch.deliveries.get()
        # Simulated local completion, not an actual external notification.
        delivery.status, delivery.filed_at = "filed", timezone.now() - timedelta(days=2)
        delivery.save()
        OutreachPolicy.objects.create(organization=self.a, reminder_days=1)
        results = self.race(lambda: prepare_followups(delivery.pk))
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(delivery.followups.count(), 1)
