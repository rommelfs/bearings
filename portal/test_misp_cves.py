"""Regression for publicly documented MISP affected-version formats."""

from copy import deepcopy
from types import SimpleNamespace
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

    def test_public_formats_classify_current_and_older_releases(self):
        from .notifications import candidates
        from .remediation import work

        unspecified, comparator, current = [deepcopy(TOTP) for _ in range(3)]
        for record, identifier, version, bound, commit in (
            (unspecified, "CVE-2026-93296", "unspecified", "lessThan", "382188d2f"),
            (comparator, "CVE-2026-93295", "< 2.5.47", "lessThan", "120813344"),
            (current, "CVE-2026-132144", "0", "lessThanOrEqual", "a1fe5058dc"),
        ):
            record["cveMetadata"]["cveId"] = identifier
            cna = record["containers"]["cna"]
            cna["references"][0]["url"] = f"https://github.com/MISP/misp/commit/{commit}"
            entry = cna["affected"][0]
            entry["repo"] = "https://github.com/MISP/misp"
            entry["versions"] = [
                {
                    "version": version,
                    bound: "2.5.51" if record is current else "2.5.47",
                    "status": "affected",
                    "versionType": "semver",
                }
            ]
            if record is not current:
                entry["defaultStatus"] = "unaffected"

        mitre = advisory(
            "CVE-2025-66384",
            misp_cves.MITRE,
            [{"version": "0", "lessThan": "2.5.24", "versionType": "semver", "status": "affected"}],
            "https://github.com/MISP/MISP/compare/v2.5.23...v2.5.24",
            defaultStatus="unaffected",
        )
        for version in ("2.5.23", "2.5.46", "2.5.47", "2.5.51", "2.5.52"):
            self.installation.version = version
            for record, result in (
                (unspecified, "potential" if version in ("2.5.23", "2.5.46") else "not_affected"),
                (comparator, "potential" if version in ("2.5.23", "2.5.46") else "not_affected"),
                (mitre, "potential" if version == "2.5.23" else "not_affected"),
                (current, "not_affected" if version == "2.5.52" else "potential"),
            ):
                with self.subTest(version=version, cve=record["cveMetadata"]["cveId"]):
                    self.assertEqual(discovery.evaluate(self.watch, self.installation, record)[0], result)

        self.installation.version = "2.5.51"
        mismatch = deepcopy(comparator)
        mismatch["containers"]["cna"]["affected"][0]["versions"][0]["version"] = "< 2.5.48"
        self.assertEqual(discovery.evaluate(self.watch, self.installation, mismatch)[0], "unknown")
        mismatch["containers"]["cna"] = []
        self.assertEqual(discovery.evaluate(self.watch, self.installation, mismatch)[0], "unknown")

        self.refresh(unspecified, comparator, mitre, current)
        for state, expected in (("attention", [current]), ("cleared", [unspecified, comparator, mitre])):
            response = self.client.get(self.url("intelligence"), {"state": state})
            self.assertEqual(
                {row.record.external_id for row in response.context["page"]},
                {item["cveMetadata"]["cveId"] for item in expected},
            )
            if state == "cleared":
                self.assertNotContains(response, "Notify about this CVE")
            else:
                self.assertContains(response, "Notify about this CVE")

        self.assertEqual(
            list(work(self.analyst, self.a).values_list("record__external_id", flat=True)),
            ["CVE-2026-132144"],
        )
        self.assertFalse(candidates(self.analyst, "circl", {"cve": "CVE-2026-93295"}).exists())

        positive = Finding.objects.get(record__external_id="CVE-2026-132144")
        heading = "Installed version in the published affected range"
        review = self.url("intelligence")
        home = reverse("home")
        for response in (
            self.client.get(home),
            self.client.get(review, {"state": "affected"}),
            self.client.get(review, {"finding": positive.pk}),
            self.client.get(reverse("review-evidence", args=[positive.pk])),
        ):
            self.assertContains(response, heading)
            self.assertNotContains(response, "Manual assessment:")
        group = self.client.get(review, {"view": "machine"})
        self.assertEqual(list(group.context["page"])[0]["affected_cves"], 1)

        positive.analyst_applicability = "not_affected"
        positive.save(update_fields=["analyst_applicability"])
        conflict = self.client.get(review, {"state": "affected"})
        self.assertContains(conflict, heading)
        self.assertContains(conflict, "Current affected version conflicts with a saved assessment")
        self.assertFalse(work(self.analyst, self.a, cve=positive.record.external_id).exists())

        self.installation.version = "2.5.52"
        self.installation.save(update_fields=["version"])
        self.assertNotContains(self.client.get(home), heading)
        self.assertNotContains(self.client.get(review, {"state": "affected"}), "CVE-2026-132144")

    def test_remediation_verification_consumes_current_application_proof(self):
        from .remediation import verification_for

        self.installation.version = "2.5.47"
        self.installation.save(update_fields=["version"])
        self.refresh(TOTP)
        finding = Finding.objects.get()
        case = SimpleNamespace(finding=finding, snapshot={"finding_ids": [finding.pk]})
        self.assertEqual(
            verification_for(self.analyst, case)[finding.pk],
            "Installed version in the published affected range",
        )

        self.installation.version = "2.5.48"
        self.installation.save(update_fields=["version"])
        self.assertEqual(verification_for(self.analyst, case)[finding.pk], "Verification pending")
        self.refresh(TOTP)
        self.assertEqual(
            verification_for(self.analyst, case)[finding.pk],
            "Installed version outside the published affected range",
        )

    def test_generic_fallback_is_not_a_current_misp_version_match(self):
        record = deepcopy(CIRCL)
        cna = record["containers"]["cna"]
        cna["providerMetadata"]["orgId"] = "unsupported"
        cna["affected"][0]["versions"][0].update(version="2.5.0", lessThanOrEqual="2.5.51")
        self.refresh(record)
        self.assertEqual(Finding.objects.get().discovery.result, "potential")
        url = self.url("intelligence")
        self.assertContains(self.client.get(url), "CVE-2026-10868")
        self.assertNotContains(self.client.get(url, {"state": "affected"}), "CVE-2026-10868")
        self.assertNotContains(
            self.client.get(reverse("home")), "Installed version in the published affected range"
        )

    def test_legacy_mitre_requires_matching_fixed_release_and_placeholder_product(self):
        record = advisory(
            "CVE-2024-46918",
            misp_cves.MITRE,
            [{"version": "n/a", "status": "affected"}],
            "https://github.com/MISP/MISP/compare/v2.4.197...v2.4.198",
        )
        cna = record["containers"]["cna"]
        cna["affected"][0].update(vendor="n/a", product="n/a")
        cna["descriptions"] = [{"lang": "en", "value": "An issue was discovered in MISP before 2.4.198."}]
        self.assertEqual(discovery.evaluate(self.watch, self.installation, record)[0], "not_affected")
        self.installation.version = "2.4.197"
        self.assertEqual(discovery.evaluate(self.watch, self.installation, record)[0], "unknown")
        self.installation.version = "2.5.51"
        cna["descriptions"][0]["value"] = "An issue was discovered in MISP before 2.4.199."
        self.assertEqual(discovery.evaluate(self.watch, self.installation, record)[0], "unknown")

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
        self.assertNotContains(current, "CVE-2026-900001")
        unclear = self.client.get(review, {"state": "unresolved"})
        self.assertContains(unclear, "CVE-2026-900001")
        self.assertNotContains(unclear, "Notify about this CVE")
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
