"""Inventory rendering must not hydrate or render the company's complete CVE history."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import (
    Asset,
    Product,
    Installation,
    SourceRecord,
    Finding,
    FindingHistory,
    Contact,
    InfrastructureClaim,
)


class CompanyInventoryTests(Fixture):
    def add_reviews(self, count, *, org=None, installation=None, shareable=True, status="new"):
        org = org or self.a
        installation = installation or self.installation
        offset = SourceRecord.objects.count()
        records = SourceRecord.objects.bulk_create(
            [
                SourceRecord(
                    organization=org,
                    source="fixture://inventory-performance",
                    external_id=f"CVE-2099-{10000 + offset + i}",
                    shareable=shareable,
                    payload={"synthetic": "not loaded into company inventory" * 200},
                )
                for i in range(count)
            ]
        )
        return Finding.objects.bulk_create(
            [
                Finding(
                    organization=org,
                    installation=installation,
                    record=record,
                    status=status,
                    explanation="Synthetic benchmark only",
                )
                for record in records
            ]
        )

    def test_growth_in_reviews_does_not_grow_queries_html_or_load_payloads_and_history(self):
        self.login()
        url = self.url("organization")
        with CaptureQueriesContext(connection) as baseline:
            initial = self.client.get(url)
        products = Product.objects.bulk_create(
            [
                Product(
                    organization=self.a,
                    name=f"Package {i:04}",
                    identifier=f"pkg:deb/ubuntu/synthetic-{i}?arch=amd64",
                )
                for i in range(1000)
            ]
        )
        Installation.objects.bulk_create(
            [Installation(asset=self.asset, product=p, version="1.0-1") for p in products]
        )
        findings = self.add_reviews(300)
        FindingHistory.objects.bulk_create(
            [
                FindingHistory(
                    finding=f,
                    actor=self.admin,
                    previous_status="new",
                    status="under_review",
                    reason="Synthetic history must stay in review workspace",
                )
                for f in findings
            ]
        )
        with CaptureQueriesContext(connection) as grown:
            response = self.client.get(url)
        self.assertEqual(response.context["finding_summary"]["total"], 300)
        self.assertEqual(response.context["finding_summary"]["pending"], 300)
        self.assertEqual(len(response.context["inventory_page"][0].software_preview), 10)
        self.assertEqual(response.context["inventory_page"][0].software_count, 1001)
        self.assertLessEqual(len(grown), len(baseline) + 3)
        self.assertLess(len(response.content), len(initial.content) + 30000)
        self.assertNotContains(response, "CVE-2099-")
        self.assertNotContains(response, "Synthetic history must stay")
        self.assertContains(response, reverse("intelligence", args=[self.a.slug]))
        self.assertFalse(any('FROM "portal_findinghistory"' in q["sql"] for q in grown))
        self.assertFalse(any('"portal_sourcerecord"."payload"' in q["sql"] for q in grown))

    def test_summary_preserves_raw_visibility_company_scope_and_workflow_meaning(self):
        self.add_reviews(2, status="new")
        self.add_reviews(1, status="confirmed")
        self.add_reviews(1, status="accepted_risk")
        self.add_reviews(1, status="resolved")
        self.add_reviews(1, shareable=False, status="confirmed")
        other_product = Product.objects.create(organization=self.b, name="Foreign")
        other_installation = Installation.objects.create(asset=self.other, product=other_product)
        self.add_reviews(5, org=self.b, installation=other_installation)
        self.login(self.reader)
        summary = self.client.get(self.url("organization")).context["finding_summary"]
        self.assertEqual(summary, {"total": 5, "pending": 2, "confirmed": 1, "accepted_risk": 1, "closed": 1})
        self.assertEqual(self.client.get(self.url("organization", self.b)).status_code, 404)
        self.login(self.platform)
        self.assertEqual(self.client.get(self.url("organization")).context["finding_summary"]["total"], 6)

    def test_contacts_scope_and_inventory_pages_remain_bounded_and_preserve_each_other(self):
        Contact.objects.bulk_create(
            [
                Contact(organization=self.a, name=f"Synthetic {i:03}", email=f"synthetic-{i}@example.invalid")
                for i in range(55)
            ]
        )
        InfrastructureClaim.objects.bulk_create(
            [
                InfrastructureClaim(
                    organization=self.a,
                    kind="domain",
                    value=f"synthetic-{i}.example.invalid",
                    valid_from=timezone.now(),
                )
                for i in range(55)
            ]
        )
        Asset.objects.bulk_create(
            [
                Asset(organization=self.a, source=self.sa, name=f"Synthetic {i:03}", kind="server")
                for i in range(55)
            ]
        )
        self.login()
        response = self.client.get(
            self.url("organization"), {"inventory_page": 2, "contact_page": 2, "scope_page": 2}
        )
        self.assertEqual(len(response.context["contact_page"]), 25)
        self.assertEqual(len(response.context["scope_page"]), 25)
        self.assertEqual(len(response.context["inventory_page"]), 6)
        self.assertContains(response, "inventory_page=2&amp;contact_page=3&amp;scope_page=2#contacts")
        self.assertContains(response, "inventory_page=2&amp;contact_page=2&amp;scope_page=3#scope")

    def test_agent_only_host_does_not_claim_a_netbox_binding(self):
        self.asset.object_type = "bearings.agent_host"
        self.asset.upstream_data = {"agent_observed_only": True}
        self.asset.save()
        self.login()
        self.assertContains(
            self.client.get(self.url("organization")),
            "Recorded in Bearings only · no confirmed NetBox object",
        )
        self.assertContains(
            self.client.get(self.url("asset", pk=self.asset.pk)),
            "This enrollment mode does not create a NetBox host",
        )

    def test_foreign_product_on_a_corrupt_installation_is_not_rendered_or_counted(self):
        foreign = Product.objects.create(organization=self.b, name="FOREIGN_PACKAGE_MUST_STAY_HIDDEN")
        Installation.objects.filter(pk=self.installation.pk).update(product=foreign)
        self.login()
        response = self.client.get(self.url("organization"))
        self.assertNotContains(response, foreign.name)
        asset = response.context["inventory_page"][0]
        self.assertEqual(asset.software_count, 0)
        response = self.client.get(self.url("asset", pk=self.asset.pk))
        self.assertNotContains(response, foreign.name)
        self.assertEqual(response.context["software_page"].paginator.count, 0)
