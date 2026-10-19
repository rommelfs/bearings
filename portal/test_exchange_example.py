import copy
import io
import uuid
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from django.utils.html import strip_tags
from .tests import Fixture
from .models import Asset, Finding, FindingHistory, InventorySource, Organization, RiskLink
from .presentation import vulnerability_summary
from .services import persist_lookup, transition_finding
from .intelligence import withdraw_link
from .management.commands.seed_exchange_example import BUILD, CVE, PRODUCT, RISK_UUIDS


def evidence():
    return {
        "cveMetadata": {"cveId": CVE, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "title": "Microsoft Exchange Server Remote Code Execution Vulnerability",
                "descriptions": [
                    {"lang": "en-US", "value": "An unauthorized attacker can execute code over a network."}
                ],
                "affected": [
                    {
                        "product": PRODUCT,
                        "versions": [
                            {
                                "version": "15.02.0.0",
                                "lessThan": "15.02.1748.055",
                                "versionType": "custom",
                                "status": "affected",
                            }
                        ],
                    }
                ],
                "metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 8.1, "baseSeverity": "HIGH"}}],
            }
        },
    }


class SourcePresentationTests(SimpleTestCase):
    def test_source_severity_is_separate_and_unsupported_values_stay_unknown(self):
        self.assertEqual(vulnerability_summary(evidence())["severity"], "High")
        for value in [None, {}, [], {"containers": []}, {"containers": {"cna": "bad"}}]:
            self.assertIsNone(vulnerability_summary(value)["score"])
        for score in [True, "8.1", -1, 11, 10**400, float("nan"), float("inf")]:
            record = evidence()
            record["containers"]["cna"]["metrics"][0]["cvssV3_1"]["baseScore"] = score
            self.assertIsNone(vulnerability_summary(record)["score"])
        record = evidence()
        record["containers"]["cna"]["metrics"][0]["cvssV3_1"]["baseScore"] = 0
        self.assertEqual(vulnerability_summary(record)["severity"], "None")


@override_settings(DEBUG=True)
class ExchangeExampleTests(Fixture):
    def setUp(self):
        self.payload = evidence()
        self.lookup = patch(
            "portal.management.commands.seed_exchange_example.lookup",
            side_effect=lambda *a: ("https://vulnerability.circl.lu", copy.deepcopy(self.payload)),
        ).start()
        bundle = {
            k: {"uuid": str(uuid.uuid4()), "id": i, "description": k, "name": k, "data": {}}
            for i, k in enumerate(["risk", "asset", "threat", "vulnerability"], 1)
        }
        bundle["risk"]["uuid"] = RISK_UUIDS[0]
        self.bundle = patch("portal.intelligence.risk_bundle", return_value=bundle).start()
        self.addCleanup(patch.stopall)

    def seed(self, **kwargs):
        call_command("seed_exchange_example", actor=self.admin.username, stdout=io.StringIO(), **kwargs)
        return Finding.objects.get(record__external_id=CVE)

    def test_seed_records_explicit_build_live_origin_and_manual_affected_assessment(self):
        finding = self.seed()
        self.assertEqual(finding.installation.build, BUILD)
        self.assertEqual(finding.record.source, "https://vulnerability.circl.lu")
        self.assertEqual(
            (finding.analyst_applicability, finding.applicability, finding.status),
            ("affected", "unknown", "under_review"),
        )
        self.assertIn("SYNTHETIC", finding.explanation)
        self.assertEqual(FindingHistory.objects.filter(finding=finding).count(), 1)
        self.assertEqual(RiskLink.objects.filter(finding=finding).count(), 1)
        self.assertEqual(finding.installation.asset.state, "synced")
        self.assertEqual(finding.installation.asset.source.mode, "development")

    def test_repeat_preserves_review_withdrawal_and_source_policy(self):
        finding = self.seed()
        link = finding.risk_links.get()
        withdraw_link(self.admin, link.pk, "Scenario rejected after local review")
        transition_finding(self.admin, finding, "resolved", "Patch installed", "not_affected")
        finding.record.shareable = False
        finding.record.save()
        again = self.seed()
        self.assertEqual(
            (again.pk, again.status, again.analyst_applicability), (finding.pk, "resolved", "not_affected")
        )
        self.assertFalse(again.record.shareable)
        self.assertEqual(again.risk_links.count(), 1)
        self.assertIsNotNone(again.risk_links.get().withdrawn_at)
        self.assertEqual(Asset.objects.filter(source__organization__slug="exchange-example").count(), 1)

    def test_changed_build_is_not_downgraded_by_seed(self):
        finding = self.seed()
        installation = finding.installation
        installation.build = installation.version = "15.2.1748.55"
        installation.save()
        with self.assertRaisesMessage(CommandError, "preserved"):
            self.seed()
        installation.refresh_from_db()
        self.assertEqual(installation.build, "15.2.1748.55")

    def test_development_and_external_guards_precede_http(self):
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            self.seed()
        self.lookup.assert_not_called()
        org = Organization.objects.create(slug="exchange-example", name="Existing")
        InventorySource.objects.create(organization=org, mode="external")
        with self.assertRaisesMessage(CommandError, "refuses"):
            self.seed()
        self.lookup.assert_not_called()
        with (
            patch("pathlib.Path.read_text", return_value='{"mode":"external"}'),
            self.assertRaises(CommandError),
        ):
            self.seed(bundled=True)
        self.lookup.assert_not_called()

    def test_changed_upstream_range_does_not_invent_affectedness(self):
        self.payload["containers"]["cna"]["affected"][0]["versions"][0]["lessThan"] = "different"
        with self.assertRaisesMessage(CommandError, "edition/range"):
            self.seed()
        self.assertFalse(Finding.objects.filter(record__external_id=CVE).exists())
        self.assertFalse(Asset.objects.filter(source__organization__slug="exchange-example").exists())

    def test_analyst_sees_high_severity_build_and_consequences_without_compromise_inference(self):
        finding = self.seed()
        self.login(self.analyst)
        home = self.client.get("/")
        for text in [CVE, "High", "8.1", BUILD, "Review required", "confidential email", "No exploitation"]:
            self.assertContains(home, text)
        self.assertContains(home, f"?finding={finding.pk}#finding-{finding.pk}")
        detail = self.client.get(self.url("intelligence", finding.organization), {"finding": finding.pk})
        self.assertContains(detail, "Possible consequences")
        self.assertContains(detail, "Source severity: High")
        self.assertIn("Analyst assessment: affected", strip_tags(detail.content.decode()))
        data = self.client.get(
            self.url("api-intelligence", finding.organization), {"finding": finding.pk}
        ).json()
        self.assertEqual(data["relationships"][0]["source_summary"]["score"], 8.1)
        self.assertEqual(data["relationships"][0]["risk_links"][0]["assessment"], "unassessed")

    def test_queue_counters_and_deep_links_follow_current_visibility_and_workflow(self):
        finding = self.seed()
        self.login(self.analyst)
        org = finding.organization
        org.operator_visibility = False
        org.save()
        self.assertNotContains(self.client.get("/"), CVE)
        self.assertEqual(
            self.client.get(self.url("intelligence", org), {"finding": finding.pk}).status_code, 404
        )
        org.operator_visibility = True
        org.save()
        finding.record.shareable = False
        finding.record.save()
        self.login(self.admin)
        self.assertNotContains(self.client.get("/"), CVE)
        self.assertEqual(
            self.client.get(self.url("intelligence", org), {"finding": finding.pk}).status_code, 404
        )
        self.login(self.analyst)
        self.assertContains(self.client.get("/"), CVE)
        finding.status = "accepted_risk"
        finding.save()
        self.assertNotContains(self.client.get("/"), CVE)
        self.assertContains(self.client.get(self.url("intelligence", org)), CVE)

    def test_source_text_is_escaped_and_foreign_filter_is_denied(self):
        self.payload["containers"]["cna"]["title"] = '<script>alert("source")</script>'
        finding = self.seed()
        self.login(self.admin)
        self.assertContains(self.client.get("/"), "&lt;script&gt;")
        self.assertNotContains(self.client.get("/"), '<script>alert("source")</script>')
        self.assertEqual(
            self.client.get(self.url("intelligence", finding.organization), {"finding": "bad"}).status_code,
            404,
        )
        foreign = self.record_finding()
        self.assertEqual(
            self.client.get(
                self.url("intelligence", finding.organization), {"finding": foreign.pk}
            ).status_code,
            404,
        )

    def test_queue_pages_are_bounded_and_criticality_sort_is_explicit(self):
        finding = self.seed()
        for i in range(28):
            persist_lookup(self.admin, self.installation, "fixture://queue", f"CVE-2026-{80000 + i}", {})
        self.login(self.analyst)
        home = self.client.get("/")
        self.assertEqual(home.context["review_page"].paginator.count, 29)
        self.assertEqual(len(home.context["review_page"]), 25)
        self.assertEqual(home.context["review_page"][0].pk, finding.pk)
        self.assertEqual(len(self.client.get("/?review_page=2").context["review_page"]), 4)
