"""Regression for the two publicly documented MISP affected-version formats."""

from copy import deepcopy
from unittest.mock import patch

from django.urls import reverse

from . import discovery, misp_cves
from .connectors.http import ConnectorError
from .models import Finding, ProductWatch, SourceRecord
from .tests import Fixture


def advisory(identifier, publisher, versions, url, **extra):
    return {
        "cveMetadata": {"cveId": identifier, "state": "PUBLISHED"},
        "containers": {
            "cna": {
                "providerMetadata": {"orgId": publisher},
                "references": [{"url": url}],
                "affected": [{"vendor": "MISP", "product": "MISP", "versions": versions, **extra}],
            }
        },
    }


GITHUB = advisory(
    "CVE-2026-44381",
    misp_cves.GITHUB,
    [{"version": "< 2.5.37", "status": "affected"}],
    "https://github.com/MISP/MISP/security/advisories/GHSA-4cxp-22wm-j6jr",
)
CIRCL = advisory(
    "CVE-2026-10868",
    misp_cves.CIRCL,
    [{"version": "0", "lessThanOrEqual": "2.5.38", "versionType": "semver", "status": "affected"}],
    "https://github.com/MISP/MISP/commit/1be8c413b7104a889dfd30c5b1986e3ab17238e8",
    defaultStatus="unaffected",
)


TOTP = advisory(
    "CVE-2026-103655",
    misp_cves.CIRCL,
    [{"version": "0", "lessThan": "2.5.48", "versionType": "semver", "status": "affected"}],
    "https://github.com/MISP/MISP/commit/a020fa47b",
    repo="https://github.com/MISP/MISP",
    modules=["app/Controller/UsersController.php (otp method)"],
    programFiles=["app/Controller/UsersController.php"],
)
TOTP["containers"]["cna"]["references"][0]["tags"] = ["patch"]
LDAP = deepcopy(TOTP)
LDAP["cveMetadata"]["cveId"] = "CVE-2026-90961"
LDAP["containers"]["cna"]["references"][0]["url"] = "https://github.com/MISP/MISP/commit/0ee058548"
LDAP["containers"]["cna"]["affected"][0]["versions"][0]["lessThan"] = "2.5.46"


class MispVersionTests(Fixture):
    def setUp(self):
        self.installation.version = "2.5.51"
        self.installation.save(update_fields=["version"])
        self.watch = ProductWatch.objects.create(
            product=self.product,
            vendor="misp",
            product_key="misp",
            source_url="https://vulnerability.circl.lu",
        )
        self.login(self.analyst)

    def refresh(self, *payloads):
        records = [(payload["cveMetadata"]["cveId"], payload) for payload in payloads]
        with patch("portal.discovery.product_records", return_value=(self.watch.source_url, records)):
            discovery.sync_watch(self.watch.pk)

    def test_published_boundaries(self):
        for version, gh_result, circl_result in (
            ("2.5.36", "potential", "potential"),
            ("2.5.37", "not_affected", "potential"),
            ("2.5.38", "not_affected", "potential"),
            ("2.5.39", "not_affected", "not_affected"),
            ("2.5.51", "not_affected", "not_affected"),
        ):
            with self.subTest(version=version):
                self.installation.version = version
                self.assertEqual(discovery.evaluate(self.watch, self.installation, GITHUB)[0], gh_result)
                self.assertEqual(discovery.evaluate(self.watch, self.installation, CIRCL)[0], circl_result)

    def test_circl_short_patch_reference_and_component_annotations(self):
        for advisory_record, old, boundary in ((TOTP, "2.5.47", "2.5.48"), (LDAP, "2.5.45", "2.5.46")):
            self.installation.version = old
            self.assertEqual(
                discovery.evaluate(self.watch, self.installation, advisory_record)[0], "potential"
            )
            for version in (boundary, "2.5.51"):
                self.installation.version = version
                self.assertEqual(
                    discovery.evaluate(self.watch, self.installation, advisory_record)[0], "not_affected"
                )
        unverified = deepcopy(TOTP)
        unverified["containers"]["cna"]["references"][0].pop("tags")
        self.assertEqual(discovery.evaluate(self.watch, self.installation, unverified)[0], "unknown")

    def test_same_version_exclusion_in_review_counts_detail_and_outreach(self):
        from .notifications import candidates
        from .overview import OverviewEvidence
        from .remediation import work

        self.refresh(TOTP, LDAP)
        identifier = TOTP["cveMetadata"]["cveId"]
        finding = Finding.objects.get(record__external_id=identifier)
        review = self.url("intelligence")
        filters = {"view": "cve", "asset": self.asset.pk}
        self.assertNotContains(self.client.get(review, filters), identifier)
        self.assertContains(self.client.get(review, {**filters, "state": "cleared"}), identifier)
        detail = self.client.get(review, {**filters, "finding": finding.pk})
        self.assertContains(detail, "Installed version outside the published affected range")
        self.assertNotContains(detail, "Notify about this CVE")
        national = self.client.get(
            reverse("circl-findings"), {"view": "records", "record": identifier, "assessment": "action"}
        )
        self.assertEqual(national.context["page"].paginator.count, 0)
        panel = self.client.get(reverse("circl-panel", args=["problems"]))
        self.assertContains(panel, "Cleared by current version evidence or a saved assessment.")
        totals = OverviewEvidence.for_page(self.analyst, [self.a]).review_totals[0][self.a.pk]
        self.assertEqual((totals["reviews"], totals["review_cleared"]), (0, 2))
        retained_issue = self.client.get(self.url("issue", pk=finding.asset_issue.pk))
        self.assertContains(retained_issue, "The current version is excluded by the vendor evidence")
        self.assertNotContains(retained_issue, "Prepare stakeholder notification")
        self.assertFalse(work(self.analyst, self.a, cve=identifier).exists())
        self.assertFalse(candidates(self.analyst, "circl", {"cve": identifier}).exists())

    def test_unsupported_rules_and_lookalike_references_cannot_clear(self):
        payload = deepcopy(GITHUB)
        cna = payload["containers"]["cna"]
        entry = cna["affected"][0]
        entry["versions"].append({"version": "2.x", "status": "affected"})
        self.assertEqual(discovery.evaluate(self.watch, self.installation, payload)[0], "unknown")
        entry["versions"].pop()
        cna["references"][0]["url"] += "?lookalike=1"
        self.assertEqual(discovery.evaluate(self.watch, self.installation, payload)[0], "unknown")
        self.installation.version = "2.5.51-beta"
        self.assertEqual(discovery.evaluate(self.watch, self.installation, GITHUB)[0], "unknown")

    def test_views_filter_catalogue_shells_and_keep_current_clearance_and_manual_work(self):
        unknown = deepcopy(GITHUB)
        unknown["cveMetadata"]["cveId"] = "CVE-2026-900001"
        unknown["containers"]["cna"].pop("providerMetadata")
        self.refresh(GITHUB, CIRCL, unknown)
        old = Finding.objects.get(record__external_id="CVE-2026-44381")
        self.assertEqual(old.discovery.result, "not_affected")
        self.assertFalse(old.discovery.inputs_changed)
        issues = reverse("issues")
        filters = {"organization": self.a.slug, "state": "active", "group_issue": old.asset_issue.pk}
        self.assertEqual(self.client.get(issues, filters).context["page"].paginator.count, 0)
        groups = self.client.get(reverse("company-actions"), {"view": "groups", "organization": self.a.slug})
        self.assertEqual(groups.context["page"].paginator.count, 0)
        review = self.url("intelligence")
        current = self.client.get(review)
        self.assertNotContains(current, "CVE-2026-44381")
        self.assertNotContains(current, "CVE-2026-10868")
        self.assertContains(current, "CVE-2026-900001")
        cleared = self.client.get(review, {"state": "cleared"})
        self.assertContains(cleared, "CVE-2026-44381")
        self.assertContains(cleared, "CVE-2026-10868")
        self.assertContains(cleared, "fixed or not affected")
        self.assertNotContains(cleared, "CVE-2026-900001")
        old.analyst_applicability = "affected"
        old.save(update_fields=["analyst_applicability"])
        self.assertEqual(self.client.get(issues, filters).context["page"].paginator.count, 1)

    def test_inventory_change_withdraws_saved_clearance_before_refresh(self):
        self.refresh(GITHUB)
        self.installation.version = "2.5.36"
        self.installation.save(update_fields=["version"])
        response = self.client.get(self.url("intelligence"), {"state": "cleared"})
        self.assertNotContains(response, "CVE-2026-44381")
        self.refresh(GITHUB)
        self.assertContains(
            self.client.get(reverse("issues"), {"organization": self.a.slug}), "CVE-2026-44381"
        )

    def test_newer_inventory_hides_a_stale_automatic_positive(self):
        self.installation.version = "2.5.36"
        self.installation.save(update_fields=["version"])
        self.refresh(GITHUB)
        url = reverse("issues")
        params = {"organization": self.a.slug}
        self.assertContains(self.client.get(url, params), "CVE-2026-44381")
        self.installation.version = "2.5.51"
        self.installation.save(update_fields=["version"])
        self.assertNotContains(self.client.get(url, params), "CVE-2026-44381")

    def test_refresh_replays_a_retained_cve_missing_from_the_index(self):
        with (
            patch("portal.misp_cves.RULE", "misp-vendor-versions/v1"),
            patch("portal.misp_cves.evaluate", return_value=None),
        ):
            self.refresh(TOTP)
        finding = Finding.objects.get()
        self.assertEqual(finding.discovery.result, "unknown")
        previous_observation = finding.record.ingested_at

        self.refresh()
        finding.refresh_from_db()
        self.watch.refresh_from_db()
        self.assertEqual(finding.discovery.result, "not_affected")
        self.assertEqual(finding.record.ingested_at, previous_observation)
        self.assertEqual(self.watch.summary["retained_missing"], 1)
        self.assertEqual(self.watch.summary["retained_reevaluated"], 1)
        self.assertNotContains(self.client.get(self.url("intelligence")), finding.record.external_id)

        self.refresh()
        self.watch.refresh_from_db()
        self.assertEqual(self.watch.summary["retained_reevaluated"], 0)
        self.assertEqual(finding.discovery.history.count(), 2)

    def test_index_failure_preserves_health_and_replays_only_bound_manual_evidence(self):
        identifier = TOTP["cveMetadata"]["cveId"]
        for source in (self.watch.source_url, "https://other.example.invalid"):
            record = SourceRecord.objects.create(
                organization=self.a, source=source, external_id=identifier, payload=TOTP, shareable=False
            )
            Finding.objects.create(
                organization=self.a,
                installation=self.installation,
                record=record,
                analyst_applicability="affected",
                explanation="Existing analyst assessment",
                status="under_review",
            )
        with (
            patch("portal.discovery.product_records", side_effect=ConnectorError("synthetic timeout")),
            self.assertRaises(ConnectorError),
        ):
            discovery.sync_watch(self.watch.pk)

        self.watch.refresh_from_db()
        self.assertTrue(self.watch.error)
        self.assertIsNone(self.watch.last_success)
        self.assertEqual(self.watch.summary["retained_reevaluated"], 1)
        bound = Finding.objects.get(record__source=self.watch.source_url)
        self.assertEqual(bound.discovery.result, "not_affected")
        self.assertEqual((bound.analyst_applicability, bound.status), ("affected", "under_review"))
        self.assertFalse(bound.record.shareable)
        self.assertFalse(
            Finding.objects.filter(
                record__source="https://other.example.invalid", discovery__isnull=False
            ).exists()
        )
