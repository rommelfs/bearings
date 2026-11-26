"""Regression for the two publicly documented MISP affected-version formats."""

from copy import deepcopy
from unittest.mock import patch

from django.urls import reverse

from . import discovery, misp_cves
from .models import Finding, ProductWatch
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
