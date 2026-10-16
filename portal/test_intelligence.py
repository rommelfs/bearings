import copy
import uuid
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from .tests import Fixture
from .connectors.http import ConnectorError
from .connectors.mosp import SCHEMAS, risk_bundle, risk_catalog
from .intelligence import (
    link_risk,
    link_state,
    resolve_risk,
    snapshot_evidence,
    sync_catalog,
    withdraw_link,
)
from .models import MOSPRisk, MOSPRiskRevision, MOSPSource, RiskLink, SourceRecordRevision
from .services import persist_lookup

RISK = "aaaaaaaa-0000-0000-0000-000000000001"
IDS = {
    "risk": RISK,
    "asset": "aaaaaaaa-0000-0000-0000-000000000002",
    "threat": "aaaaaaaa-0000-0000-0000-000000000003",
    "vulnerability": "aaaaaaaa-0000-0000-0000-000000000004",
}
SCHEMA_IDS = {kind: i for i, kind in enumerate(SCHEMAS, 1)}


def row(kind):
    data = {"uuid": IDS[kind], "version": 1}
    if kind == "risk":
        data.update({k: IDS[k] for k in ["asset", "threat", "vulnerability"]})
    else:
        data.update(language="EN", label=kind, description=kind + " context", code="example")
    return {
        "id": SCHEMA_IDS[kind],
        "name": kind,
        "description": "Synthetic " + kind,
        "schema_id": SCHEMA_IDS[kind],
        "organization": {"name": "MONARC"},
        "licenses": [{"license_id": "CC0-1.0"}],
        "last_updated": "2020-01-01T00:00:00",
        "json_object": data,
    }


def page(rows, *, count=None, offset=0):
    return {
        "metadata": {
            "count": str(len(rows) if count is None else count),
            "offset": str(offset),
            "limit": "100",
        },
        "data": rows,
    }


class MOSPContractTests(TestCase):
    def setUp(self):
        self.source = MOSPSource.objects.create(name="Public test")
        self.rows = {kind: row(kind) for kind in SCHEMAS}
        approved = patch("portal.connectors.mosp.approved_base", return_value="https://objects.monarc.lu")
        approved.start()
        self.addCleanup(approved.stop)
        self.http = patch("portal.connectors.mosp.request_json", side_effect=self.response).start()
        self.addCleanup(patch.stopall)

    def response(self, method, url, **kwargs):
        if url.endswith("/schema/"):
            return page(
                [
                    {
                        "id": SCHEMA_IDS[k],
                        "organization": {"name": "MONARC"},
                        "json_schema": {"$id": "https://objects.monarc.lu/schema/def/" + uid},
                    }
                    for k, uid in SCHEMAS.items()
                ]
            )
        kind = next(k for k, uid in SCHEMAS.items() if kwargs["params"]["schema_uuid"] == uid)
        return page([copy.deepcopy(self.rows[kind])])

    def test_live_style_string_metadata_and_reference_resolution_use_gets_only(self):
        self.assertEqual(risk_catalog(self.source)[0]["uuid"], RISK)
        result = risk_bundle(self.source, uuid.UUID(RISK))
        self.assertEqual(result["asset"]["data"]["language"], "EN")
        self.assertEqual(set(result), {"risk", "asset", "threat", "vulnerability"})
        self.assertTrue(all(c.args[0] == "GET" for c in self.http.call_args_list))
        self.assertFalse(any("headers" in c.kwargs for c in self.http.call_args_list))
        self.assertTrue(
            all(
                c.kwargs["params"].get("language") == "EN"
                for c in self.http.call_args_list
                if c.args[1].endswith("/object/") and c.kwargs["params"]["schema_uuid"] != SCHEMAS["risk"]
            )
        )

    def test_wrong_publisher_schema_license_uuid_and_language_are_rejected(self):
        mutations = [
            ("risk", "organization", {"name": "Other"}),
            ("risk", "schema_id", 99),
            ("risk", "licenses", []),
            ("risk", "licenses", [{"license_id": "proprietary"}]),
            ("risk", "json_object", {"uuid": IDS["asset"]}),
            ("asset", "json_object", {"uuid": IDS["asset"], "language": "DE"}),
        ]
        for kind, key, value in mutations:
            with self.subTest(kind=kind, key=key):
                original = copy.deepcopy(self.rows)
                self.rows[kind][key] = value
                with self.assertRaises(ConnectorError):
                    risk_bundle(self.source, uuid.UUID(RISK))
                self.rows = original

    def test_partial_pages_and_duplicate_ids_fail_without_catalog_changes(self):
        original = self.response

        def partial(method, url, **kwargs):
            if "/object/" in url:
                return page([], count=1)
            return original(method, url, **kwargs)

        self.http.side_effect = partial
        with self.assertRaises(ConnectorError):
            sync_catalog(self.source.pk)
        self.assertFalse(MOSPRisk.objects.exists())
        self.source.refresh_from_db()
        self.assertTrue(self.source.error)

    def test_complete_pages_are_reconstructed_and_missing_templates_retained(self):
        original = self.response

        def pages(method, url, **kwargs):
            if "/object/" not in url:
                return original(method, url, **kwargs)
            second = copy.deepcopy(self.rows["risk"])
            second["id"] = 55
            second["json_object"]["uuid"] = "bbbbbbbb-0000-0000-0000-000000000001"
            return page(
                [copy.deepcopy(self.rows["risk"])] if kwargs["params"]["page"] == 1 else [second],
                count=2,
                offset=kwargs["params"]["page"] - 1,
            )

        self.http.side_effect = pages
        self.assertEqual(sync_catalog(self.source.pk), 2)
        self.http.side_effect = original
        self.assertEqual(sync_catalog(self.source.pk), 1)
        self.assertEqual(MOSPRisk.objects.count(), 2)
        self.assertEqual(MOSPRisk.objects.filter(missing_since__isnull=False).count(), 1)

    def test_failure_retains_previous_catalog_and_success_and_is_throttled(self):
        sync_catalog(self.source.pk)
        self.source.refresh_from_db()
        old = self.source.last_success
        self.http.side_effect = ConnectorError("secret upstream body")
        with self.assertRaises(ConnectorError):
            sync_catalog(self.source.pk)
        self.source.refresh_from_db()
        self.assertEqual(self.source.last_success, old)
        self.assertNotIn("secret", self.source.error)
        self.assertEqual(MOSPRisk.objects.count(), 1)
        self.assertIsNone(sync_catalog(self.source.pk, due=True))

    def test_disabled_sources_are_not_contacted_and_imported_identity_is_immutable(self):
        sync_catalog(self.source.pk)
        self.source.refresh_from_db()
        self.source.base_url = "https://other.example.invalid"
        with self.assertRaises(ValidationError):
            self.source.full_clean()
        self.source.base_url = "https://objects.monarc.lu"
        self.source.enabled = False
        self.source.save()
        self.http.reset_mock()
        with self.assertRaises(ConnectorError):
            risk_bundle(self.source, uuid.UUID(RISK))
        self.http.assert_not_called()


class IntelligenceTests(Fixture):
    def setUp(self):
        self.source = MOSPSource.objects.create(name="Public CC0")
        self.finding = persist_lookup(
            self.admin,
            self.installation,
            "https://vulnerability.circl.lu",
            "CVE-2021-44228",
            {"cveMetadata": {"cveId": "CVE-2021-44228", "state": "PUBLISHED"}},
        )
        self.bundle = {
            k: {
                "uuid": IDS[k],
                "id": SCHEMA_IDS[k],
                "kind": k,
                "schema_uuid": SCHEMAS[k],
                "publisher": "MONARC",
                "licenses": ["CC0-1.0"],
                "name": k,
                "description": "Synthetic " + k,
                "data": {"uuid": IDS[k]},
            }
            for k in SCHEMAS
        }
        self.network = patch(
            "portal.intelligence.risk_bundle", side_effect=lambda *args: copy.deepcopy(self.bundle)
        ).start()
        self.addCleanup(patch.stopall)

    def link(self, user=None):
        return link_risk(
            user or self.admin,
            self.finding,
            self.source.pk,
            uuid.UUID(RISK),
            "Scenario for explicit review; affectedness unknown",
        )

    def test_mapping_is_idempotent_and_pins_complete_catalog_and_cve_evidence(self):
        link = self.link()
        again = self.link()
        self.assertEqual(link.pk, again.pk)
        self.assertEqual((RiskLink.objects.count(), MOSPRiskRevision.objects.count()), (1, 1))
        self.assertEqual(link.evidence_revision.payload["cveMetadata"]["cveId"], "CVE-2021-44228")
        self.assertEqual(set(link.risk_revision.payload), set(SCHEMAS))
        self.finding.refresh_from_db()
        self.assertEqual(
            (self.finding.status, self.finding.applicability, self.finding.analyst_applicability),
            ("new", "unknown", "unassessed"),
        )
        self.assertFalse(any(link_state(link).values()))

    def test_cve_updates_preserve_snapshots_and_restricted_policy(self):
        link = self.link()
        record = self.finding.record
        record.shareable = False
        record.save()
        self.finding.analyst_applicability = "not_affected"
        self.finding.save()
        payload = {"cveMetadata": {"cveId": "CVE-2021-44228", "state": "PUBLISHED"}, "new_evidence": True}
        persist_lookup(self.admin, self.installation, record.source, record.external_id, payload)
        record.refresh_from_db()
        self.finding.refresh_from_db()
        link = RiskLink.objects.select_related("finding__record", "risk_revision__risk").get(pk=link.pk)
        self.assertFalse(record.shareable)
        self.assertEqual(SourceRecordRevision.objects.filter(record=record).count(), 2)
        self.assertNotIn("new_evidence", link.evidence_revision.payload)
        self.assertEqual(self.finding.analyst_applicability, "not_affected")
        self.assertTrue(link_state(link)["evidence_changed"])

    def test_catalog_and_reference_changes_create_revisions_without_rewriting_links(self):
        link = self.link()
        self.bundle["threat"]["name"] = "updated threat"
        resolve_risk(self.source.pk, uuid.UUID(RISK))
        link = RiskLink.objects.select_related("finding__record", "risk_revision__risk").get(pk=link.pk)
        self.assertEqual(link.risk_revision.payload["threat"]["name"], "threat")
        self.assertTrue(link_state(link)["catalog_changed"])
        self.assertEqual(MOSPRiskRevision.objects.count(), 2)

    def test_network_failure_does_not_replace_prior_mapping(self):
        link = self.link()
        self.network.side_effect = ConnectorError("outage")
        with self.assertRaises(ConnectorError):
            self.link()
        self.assertEqual(RiskLink.objects.get().pk, link.pk)
        self.assertEqual(MOSPRiskRevision.objects.count(), 1)

    def test_reader_unauthorized_analyst_and_cross_org_cannot_fetch_or_link(self):
        for user in [self.reader]:
            with self.assertRaises(PermissionDenied):
                self.link(user)
        foreign = self.record_finding()
        foreign.organization = self.b
        foreign.save()
        with self.assertRaises((PermissionDenied, ValidationError)):
            link_risk(self.admin, foreign, self.source.pk, uuid.UUID(RISK), "bad")
        self.network.assert_not_called()

    def test_withdrawal_preserves_reason_and_snapshot_and_new_mapping_can_be_created(self):
        link = self.link()
        withdraw_link(self.admin, link.pk, "Not appropriate for this asset")
        link.refresh_from_db()
        self.assertIsNotNone(link.withdrawn_at)
        self.assertTrue(link.reason.startswith("Scenario"))
        self.assertEqual(self.link().withdrawn_at, None)
        self.assertEqual(RiskLink.objects.count(), 2)

    def test_derived_html_api_counts_and_pinned_evidence_follow_visibility_revocation(self):
        link = self.link()
        self.login()
        for name, kwargs in [
            ("intelligence", {}),
            ("api-intelligence", {}),
            ("risk-link-evidence", {"pk": link.pk}),
        ]:
            self.assertEqual(self.client.get(self.url(name, **kwargs)).status_code, 200)
        record = self.finding.record
        record.shareable = False
        record.save()
        self.assertEqual(self.client.get(self.url("risk-link-evidence", pk=link.pk)).status_code, 404)
        response = self.client.get(self.url("api-intelligence")).json()
        self.assertEqual((response["pagination"]["count"], response["relationships"]), (0, []))
        self.assertNotContains(self.client.get(self.url("intelligence")), "CVE-2021-44228")
        self.login(self.analyst)
        self.assertEqual(self.client.get(self.url("risk-link-evidence", pk=link.pk)).status_code, 200)
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.url("intelligence")).status_code, 404)

    def test_foreign_org_urls_and_cross_finding_link_ids_do_not_leak(self):
        link = self.link()
        self.login()
        self.assertEqual(self.client.get(self.url("api-intelligence", self.b)).status_code, 404)
        self.assertEqual(self.client.get(self.url("risk-link-evidence", self.b, pk=link.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("risk-catalog") + "?finding=not-an-int").status_code, 404)
        self.assertEqual(
            self.client.post(
                self.url("withdraw-risk-link", self.b, pk=link.pk), {"reason": "bad"}
            ).status_code,
            404,
        )

    def test_forms_require_csrf_authorized_actor_and_nonempty_justification(self):
        self.login()
        url = self.url("create-risk-link", pk=self.finding.pk)
        response = self.client.post(url, {"source": self.source.pk, "risk_uuid": RISK, "reason": ""})
        self.assertEqual(response.status_code, 200)
        self.network.assert_not_called()
        self.login(self.reader)
        self.assertEqual(
            self.client.post(url, {"source": self.source.pk, "risk_uuid": RISK, "reason": "bad"}).status_code,
            403,
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(
            client.post(url, {"source": self.source.pk, "risk_uuid": RISK, "reason": "review"}).status_code,
            403,
        )

    def test_upstream_and_reason_html_is_escaped_and_unsupported_evidence_links_are_not_rendered(self):
        self.bundle["threat"]["name"] = '<script>alert("x")</script>'
        link = self.link()
        self.login()
        response = self.client.get(self.url("intelligence"))
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.assertEqual(
            self.client.get(self.url("risk-link-evidence", pk=link.pk))["Content-Type"], "application/json"
        )

    def test_link_model_rejects_evidence_from_a_different_finding_record(self):
        link = self.link()
        other = self.record_finding()
        link.evidence_revision = snapshot_evidence(other.record)
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_catalog_and_board_pagination_and_search_remain_scoped(self):
        self.link()
        self.login()
        response = self.client.get(self.url("risk-catalog") + "?q=Synthetic&finding=" + str(self.finding.pk))
        self.assertContains(response, "Synthetic risk")
        self.assertContains(response, "Select for CVE-2021-44228")
        data = self.client.get(self.url("api-intelligence")).json()
        self.assertEqual(data["relationships"][0]["risk_links"][0]["assessment"], "unassessed")
        self.assertEqual(data["relationships"][0]["asset"]["id"], str(self.asset.pk))
