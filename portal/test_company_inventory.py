"""Inventory rendering must not hydrate or render the company's complete CVE history."""

import base64
import uuid
from datetime import timedelta
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import (
    Asset,
    AgentDevice,
    AgentReport,
    AgentComponent,
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
        self.assertEqual(len(response.context["inventory_page"][0].software_preview), 1)
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

    def test_machine_card_groups_dual_stack_addresses_and_preserves_address_detail_links(self):
        addresses = [
            Asset.objects.create(
                organization=self.a,
                source=self.sa,
                kind="ip_address",
                object_type="ipam.ipaddress",
                external_id=str(i),
                name=name,
                network_host=self.asset,
                upstream_data={
                    "assignment": {"interface": "eth0"},
                    "dns_name": "synthetic-host.example.invalid",
                },
            )
            for i, name in enumerate(("192.0.2.10/24", "2001:db8::10/64"), 1)
        ]
        self.login()
        response = self.client.get(self.url("organization"))
        self.assertEqual(response.context["inventory_page"].paginator.count, 1)
        self.assertEqual(response.context["inventory_page"][0].assigned_address_count, 2)
        for address in addresses:
            self.assertContains(response, address.name)
            self.assertContains(response, reverse("asset", args=[self.a.slug, address.pk]))
        self.assertContains(response, "eth0")
        detail = self.client.get(self.url("asset", pk=addresses[0].pk))
        self.assertContains(detail, "Assigned to")
        self.assertEqual(detail.context["network_host"], self.asset)
        addresses[0].missing_since = timezone.now()
        addresses[0].save(update_fields=["missing_since"])
        self.assertContains(self.client.get(self.url("organization")), "last-known assignment")
        detail = self.client.get(self.url("asset", pk=addresses[0].pk))
        self.assertContains(detail, "Record missing-object review")
        self.assertEqual(self.client.get(self.url("asset", self.b, pk=addresses[0].pk)).status_code, 404)

    def test_many_addresses_have_bounded_preview_and_corrupt_cross_org_links_do_not_group(self):
        self.login()
        with CaptureQueriesContext(connection) as baseline:
            self.client.get(self.url("organization"))
        Asset.objects.bulk_create(
            [
                Asset(
                    organization=self.a,
                    source=self.sa,
                    name=f"192.0.2.{i}/24",
                    kind="ip_address",
                    object_type="ipam.ipaddress",
                    external_id=str(i),
                    network_host=self.asset,
                )
                for i in range(1, 101)
            ]
        )
        corrupt = Asset.objects.create(
            organization=self.a,
            source=self.sa,
            name="Independent address",
            kind="ip_address",
            object_type="ipam.ipaddress",
            network_host=self.other,
        )
        self.login()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url("organization"))
        self.assertLessEqual(len(queries), len(baseline) + 3)
        self.assertEqual(response.context["inventory_page"].paginator.count, 2)
        host = next(a for a in response.context["inventory_page"] if a.pk == self.asset.pk)
        self.assertEqual(host.assigned_address_count, 100)
        self.assertEqual(len(host.address_preview), 16)
        self.assertContains(response, corrupt.name)
        self.assertNotContains(response, self.other.name)
        response = self.client.get(self.url("asset", pk=corrupt.pk))
        self.assertIsNone(response.context["network_host"])

    def test_domain_code_link_matches_existing_company_admin_and_platform_permissions(self):
        target = reverse("company-members", args=[self.a.slug]) + "#domain-codes"
        self.login(self.reader)
        self.assertNotContains(self.client.get(self.url("organization")), target)
        self.login(self.platform)
        self.assertContains(self.client.get(self.url("organization")), target)

    def test_compact_two_hundred_host_inventory_keeps_packages_and_queries_bounded(self):
        self.asset.name = "host-000"
        self.asset.save()
        hosts = [
            self.asset,
            *Asset.objects.bulk_create(
                [
                    Asset(organization=self.a, source=self.sa, name=f"host-{i:03}", kind="server")
                    for i in range(1, 200)
                ]
            ),
        ]
        packages = Product.objects.bulk_create(
            [
                Product(
                    organization=self.a,
                    name=f"base-package-{i:03}",
                    identifier=f"pkg:deb/ubuntu/base-{i}?arch=amd64",
                )
                for i in range(20)
            ]
        )
        misp = Product.objects.create(
            organization=self.a, name="MISP", identifier="cpe:2.3:a:misp:misp:*:*:*:*:*:*:*:*"
        )
        extras = Product.objects.bulk_create(
            [Product(organization=self.a, name=n) for n in ("Vault", "Zabbix")]
        )
        Installation.objects.bulk_create(
            [
                Installation(asset=host, product=product, version="2.5.51" if product == misp else "1.0")
                for host in hosts
                for product in [*packages, misp, *extras]
            ]
        )
        AgentDevice.objects.bulk_create(
            [
                AgentDevice(
                    organization=self.a,
                    source=self.sa,
                    asset=host,
                    public_key=base64.b64encode(i.to_bytes(32, "big")).decode(),
                    expires_at=timezone.now() + timedelta(days=1),
                    last_observed_at=timezone.now(),
                    os={"id": "ubuntu", "version": "24.04"},
                )
                for i, host in enumerate(hosts)
            ]
        )
        self.login()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url("organization"))
        self.assertEqual(response.context["inventory_page"].paginator.count, 200)
        self.assertEqual(len(response.context["inventory_page"]), 50)
        self.assertLess(len(queries), 40)
        self.assertLess(len(response.content), 160000)
        self.assertContains(response, "Ubuntu 24.04", count=50)
        self.assertNotContains(response, "base-package-")
        self.assertNotContains(response, "Investigate a known CVE")
        for host in response.context["inventory_page"]:
            self.assertLessEqual(len(host.software_preview), 3)
            self.assertGreaterEqual(host.software_count, 23)
            self.assertEqual(host.additional_software_count, 4 if host.pk == self.asset.pk else 3)
        self.assertContains(response, "+1 more")
        self.assertContains(self.client.get(self.url("asset", pk=self.asset.pk)), "base-package-000")
        searched = self.client.get(self.url("organization"), {"inventory_q": "host-19"})
        self.assertEqual(searched.context["inventory_page"].paginator.count, 10)
        self.assertEqual(Installation.objects.filter(asset__organization=self.a).count(), 4601)

    def test_os_requires_scoped_metadata_or_recorded_os_and_marks_stale_reports(self):
        self.login()
        self.product.identifier = "pkg:deb/ubuntu/adduser?arch=all"
        self.product.save()
        response = self.client.get(self.url("organization"))
        self.assertEqual(response.context["inventory_page"][0].overview_os, "")
        self.assertEqual(response.context["inventory_page"][0].software_preview, [])
        device = AgentDevice.objects.create(
            organization=self.b,
            source=self.sb,
            asset=self.asset,
            public_key="synthetic-os-key",
            expires_at=timezone.now() + timedelta(days=1),
            last_observed_at=timezone.now(),
            os={"id": "ubuntu", "version": "24.04"},
        )
        self.assertEqual(
            self.client.get(self.url("organization")).context["inventory_page"][0].overview_os, ""
        )
        device.organization = self.a
        device.save()
        self.assertEqual(
            self.client.get(self.url("organization")).context["inventory_page"][0].overview_os, ""
        )
        device.source = self.sa
        device.last_observed_at = timezone.now() - timedelta(days=1)
        device.save()
        response = self.client.get(self.url("organization"))
        self.assertContains(response, "Ubuntu 24.04")
        self.assertContains(response, "Last-known OS")
        device.enabled = False
        device.save()
        self.installation.is_operating_system = True
        self.installation.version = "22.04"
        self.installation.save()
        self.product.name = "Ubuntu"
        self.product.save()
        response = self.client.get(self.url("organization"))
        self.assertEqual(response.context["inventory_page"][0].overview_os, "Ubuntu 22.04")

    def test_manifest_applications_take_priority_and_stale_versions_stay_labelled(self):
        self.login()
        for name in ("Application A", "Application B", "Application C"):
            p = Product.objects.create(organization=self.a, name=name)
            Installation.objects.create(asset=self.asset, product=p, version="1")
        product = Product.objects.create(organization=self.a, name="MISP")
        installed = Installation.objects.create(asset=self.asset, product=product, version="2.5.51")
        device = AgentDevice.objects.create(
            organization=self.a,
            source=self.sa,
            asset=self.asset,
            public_key="synthetic-key",
            expires_at=timezone.now() + timedelta(days=1),
        )
        report = AgentReport.objects.create(
            id=uuid.uuid4(),
            device=device,
            sequence=1,
            observed_at=timezone.now(),
            body=b"{}",
            body_hash="0" * 64,
            component_count=1,
        )
        AgentComponent.objects.create(
            device=device,
            installation=installed,
            key="manifest:misp:all",
            name="MISP",
            manager="manifest",
            version="2.5.51",
            observed_at=timezone.now() - timedelta(days=1),
            last_report=report,
        )
        response = self.client.get(self.url("organization"))
        previews = response.context["inventory_page"][0].software_preview
        self.assertEqual(previews[0].product.name, "MISP")
        self.assertEqual(len(previews), 3)
        self.assertContains(response, "Last-known version")
