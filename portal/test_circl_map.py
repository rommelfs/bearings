"""Local-only map placement and derived severity retain current evidence/organization policy."""

from decimal import Decimal
from unittest.mock import patch
from django.core import signing
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from .tests import Fixture
from .models import AssetIssue, Membership, Organization, InventorySource, OrganizationLocation
from .geography import address_digest, local_location
from .circl_map_views import SALT

ADDRESS = "1 Example Road\nL-4968 Schouweiler\nLuxembourg"


class CIRCLMapTests(Fixture):
    def setUp(self):
        self.a.postal_address = ADDRESS
        self.a.save()
        self.login(self.analyst)

    def data(self):
        return self.client.get(reverse("circl-map-data"))

    def test_offline_geography_is_conservative_and_approximate(self):
        for address in [
            "",
            "Example address",
            "Luxembourg",
            "1234 Example Street\nLuxembourg",
            "L-4968 Schouweiler\nBelgium",
            "L-0000 Luxembourg",
            "L-4968 / L-4970 Luxembourg",
        ]:
            self.assertIsNone(local_location(address), address)
        point = local_location(ADDRESS)
        self.assertEqual(point["method"], "postal")
        self.assertAlmostEqual(point["lat"], 49.5789, places=3)
        self.assertEqual(local_location("Schouweiler\nLuxembourg")["method"], "place")
        self.assertIsNone(local_location("Rue Schouweiler\nLuxembourg"))

    def test_roles_private_no_store_and_no_external_requests(self):
        for user in [self.admin, self.editor, self.reader]:
            self.login(user)
            self.assertEqual(self.data().status_code, 403)
        self.client.logout()
        self.assertEqual(self.data().status_code, 302)
        self.login(self.analyst)
        with patch("httpx.Client.request") as http:
            response = self.data()
            http.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.json()["summary"]["companies"], 1)
        self.assertNotIn(self.b.name, response.content.decode())
        self.assertEqual(response.json()["points"][0]["level"], "no_open")
        self.a.name = '<img src=x onerror="alert(1)">'
        self.a.save(update_fields=["name"])
        response = self.data()
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertEqual(response.json()["points"][0]["name"], self.a.name)

    def test_severity_canonical_reviews_other_issues_accepted_and_exact_links(self):
        finding = self.record_finding()
        finding.record.payload = {
            "containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 10.0}}]}}
        }
        finding.record.save()
        finding.status = "accepted_risk"
        finding.save()
        # CVE issue proxies are not counted twice.
        AssetIssue.objects.get_or_create(
            finding=finding,
            defaults={
                "organization": self.a,
                "asset": self.asset,
                "installation": self.installation,
                "kind": "vulnerability",
                "title": "Proxy",
                "source_label": "Synthetic",
            },
        )
        other = AssetIssue.objects.create(
            organization=self.a,
            asset=self.asset,
            kind="eol",
            title="Support expired",
            source_label="Synthetic",
            priority="high",
            status="accepted_risk",
        )
        point = self.data().json()["points"][0]
        self.assertEqual((point["level"], point["reviews"], point["issues"]), ("critical", 1, 1))
        reviews = self.client.get(point["reviews_url"])
        self.assertEqual(reviews.context["page"].paginator.count, 1)
        issues = self.client.get(point["issues_url"])
        self.assertEqual([i.pk for i in issues.context["page"]], [other.pk])
        finding.analyst_applicability = "not_affected"
        finding.save()
        self.assertEqual(self.data().json()["points"][0]["level"], "high")
        other.status = "resolved"
        other.save()
        self.assertEqual(self.data().json()["points"][0]["level"], "no_open")

    def test_membership_does_not_leak_restricted_source_derived_severity(self):
        finding = self.record_finding(shareable=False)
        finding.record.payload = {
            "containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 10.0}}]}}
        }
        finding.record.save()
        AssetIssue.objects.create(
            organization=self.a,
            asset=self.asset,
            kind="exposure",
            title="Private",
            source_label="Synthetic",
            priority="critical",
            operator_only=True,
        )
        self.a.operator_visibility = False
        self.a.save()
        Membership.objects.create(user=self.analyst, organization=self.a, role="reader")
        point = self.data().json()["points"][0]
        self.assertEqual((point["reviews"], point["issues"], point["level"]), (0, 0, "no_open"))
        self.assertEqual(point["location_url"], "")
        Membership.objects.filter(user=self.analyst).delete()
        self.assertEqual(self.data().json()["summary"]["companies"], 0)

    def test_manual_point_permissions_address_binding_clear_and_range_validation(self):
        url = reverse("circl-map-location", args=[self.a.slug])
        self.login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login(self.analyst)
        response = self.client.get(url)
        token = response.context["form"].initial["token"]
        self.assertEqual(
            self.client.post(url, {"latitude": 100, "longitude": 6, "token": token}).status_code, 200
        )
        self.assertFalse(OrganizationLocation.objects.exists())
        self.assertEqual(
            self.client.post(
                url, {"latitude": "49.600000", "longitude": "6.100000", "token": token}
            ).status_code,
            302,
        )
        self.assertEqual(self.data().json()["points"][0]["method"], "manual")
        self.assertEqual(OrganizationLocation.objects.get().latitude, Decimal("49.600000"))
        Organization.objects.filter(pk=self.a.pk).update(postal_address="Different unresolved address")
        data = self.data().json()
        self.assertEqual(data["summary"]["stale_manual"], 1)
        self.assertEqual(data["summary"]["unlocated"], 1)
        self.assertEqual(data["points"], [])
        response = self.client.post(url, {"latitude": 50, "longitude": 7, "token": token})
        self.assertContains(response, "Address changed or form expired")
        self.a.refresh_from_db()
        token = signing.dumps({"org": self.a.pk, "address": address_digest(self.a.postal_address)}, salt=SALT)
        self.assertEqual(self.client.post(url, {"action": "clear", "token": token}).status_code, 302)
        self.assertFalse(OrganizationLocation.objects.exists())
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_inactive_assets_foreign_source_and_point_limit_priority(self):
        finding = self.record_finding()
        finding.record.payload = {
            "containers": {"cna": {"metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 10.0}}]}}
        }
        finding.record.save()
        self.asset.lifecycle = "retired"
        self.asset.save()
        self.assertEqual(self.data().json()["points"][0]["reviews"], 0)
        self.asset.lifecycle = "active"
        self.asset.source = self.sb
        self.asset.save()
        self.assertEqual(self.data().json()["points"][0]["reviews"], 0)
        self.asset.source = self.sa
        self.asset.save()
        for i in range(3):
            Organization.objects.create(
                name=f"Other {i}", slug=f"map-{i}", operator_visibility=True, postal_address=ADDRESS
            )
        with patch("portal.circl_map.MAX_POINTS", 1):
            payload = self.data().json()
        self.assertEqual(payload["summary"]["located"], 4)
        self.assertEqual(payload["summary"]["omitted"], 3)
        self.assertEqual(payload["points"][0]["id"], self.a.pk)
        self.a.postal_address = "Unresolved address"
        self.a.save()
        payload = self.data().json()
        self.assertEqual(payload["summary"]["unlocated_with_problems"], 1)
        self.assertEqual(payload["unlocated"][0]["level"], "critical")

    def test_map_queries_are_batched_and_unlocated_is_explicit(self):
        with CaptureQueriesContext(connection) as first:
            self.data()
        for i in range(12):
            org = Organization.objects.create(
                name=f"Geo company {i}",
                slug=f"geo-{i}",
                operator_visibility=True,
                postal_address=ADDRESS if i % 2 else "",
            )
            InventorySource.objects.create(organization=org, mode="development")
        with CaptureQueriesContext(connection) as many:
            payload = self.data().json()
        self.assertEqual(payload["summary"]["companies"], 13)
        self.assertEqual(payload["summary"]["missing_address"], 6)
        self.assertLessEqual(len(many), len(first) + 1)
        self.assertLessEqual(len(many), 22)
