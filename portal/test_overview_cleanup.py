"""Overview must distinguish package automation, raw IP records and empty workspaces."""

import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import AgentComponent, AgentDevice, AgentReport, Asset, Membership, Organization, ProductWatch


class OverviewCleanupTests(Fixture):
    def package(self):
        self.product.identifier = "pkg:deb/ubuntu/nginx?arch=amd64"
        self.product.save()
        self.installation.version = "1.24.0-2ubuntu7.21"
        self.installation.save()

    def reporter(self, *, state="partial", queued=False):
        self.package()
        device = AgentDevice.objects.create(
            organization=self.a,
            asset=self.asset,
            source=self.sa,
            public_key="synthetic-overview-public-key",
            expires_at=timezone.now() + timedelta(days=1),
            last_observed_at=timezone.now(),
            distro_checked_at=timezone.now(),
            distro_requested=queued,
            distro_summary={"state": state},
        )
        report = AgentReport.objects.create(
            device=device,
            id=uuid.uuid4(),
            sequence=1,
            observed_at=timezone.now(),
            body=b"{}",
            body_hash="synthetic",
            component_count=1,
            status="applied",
        )
        AgentComponent.objects.create(
            device=device,
            key="dpkg:nginx:amd64",
            manager="dpkg",
            name="nginx",
            architecture="amd64",
            version=self.installation.version,
            observed_at=timezone.now(),
            last_report=report,
            installation=self.installation,
        )
        return device, report

    @override_settings(DISTRO_CVE_ENABLED=True)
    def test_package_routes_need_no_manufacturer_watch_and_do_not_claim_a_fresh_watch(self):
        self.package()
        self.login()
        response = self.client.get(reverse("overview"))
        state = response.context["companies"][0]
        self.assertEqual((state["package_products"], state["configured"], state["unmapped"]), (1, 1, 0))
        self.assertContains(response, "1 distribution package identities")
        self.assertNotContains(response, "need a manufacturer/product mapping")
        self.assertNotContains(response, "configured product watches current")
        self.assertEqual(state["package_clients"], 0)
        self.assertTrue(state["package_gaps"])
        self.assertFalse(ProductWatch.objects.exists())

    def test_device_summaries_are_scoped_queued_and_expired_without_false_current_results(self):
        device, report = self.reporter()
        self.login()
        state = self.client.get(reverse("overview")).context["companies"][0]
        self.assertEqual((state["package_clients"], state["package_uncertain"]), (1, 1))
        self.assertEqual(state["package_queued"], 0)
        report.status = "pending"
        report.save()
        state = self.client.get(reverse("overview")).context["companies"][0]
        self.assertEqual(state["package_queued"], 1)
        device.expires_at = timezone.now() - timedelta(seconds=1)
        device.save()
        state = self.client.get(reverse("overview")).context["companies"][0]
        self.assertEqual(state["package_unavailable"], 1)
        # A mismatched source is never counted merely because the product is visible.
        AgentDevice.objects.filter(pk=device.pk).update(source=self.sb)
        state = self.client.get(reverse("overview")).context["companies"][0]
        self.assertEqual(state["package_clients"], 0)

    def test_assigned_ip_records_do_not_inflate_host_or_missing_software_counts(self):
        self.installation.version = "known"
        self.installation.save()
        for identity, address in enumerate(("192.0.2.10/24", "2001:db8::10/64"), 1):
            Asset.objects.create(
                organization=self.a,
                source=self.sa,
                name=address,
                kind="ip_address",
                object_type="ipam.ipaddress",
                external_id=str(identity),
                network_host=self.asset,
            )
        self.login()
        state = self.client.get(reverse("overview")).context["companies"][0]
        self.assertEqual((state["assets"], state["without_software"]), (1, 0))

    def test_empty_workspaces_stay_accessible_but_are_not_reported_as_covered_or_merged(self):
        empty = Organization.objects.create(name=self.a.name, slug="synthetic-empty-workspace")
        Membership.objects.create(organization=empty, user=self.admin, role="admin")
        self.login()
        response = self.client.get(reverse("overview"))
        self.assertEqual([s["org"].pk for s in response.context["main_companies"]], [self.a.pk])
        self.assertEqual([s["org"].pk for s in response.context["pending_companies"]], [empty.pk])
        state = next(s for s in response.context["companies"] if s["org"].pk == empty.pk)
        self.assertEqual(state["status"], "No active inventory")
        self.assertTrue(state["coverage_gaps"])
        self.assertNotContains(response, "Coverage complete")
        empty.refresh_from_db()
        self.assertIsNone(empty.merged_into_id)
        selected = self.client.get(reverse("overview"), {"organization": empty.slug})
        self.assertEqual(len(selected.context["main_companies"]), 1)
        self.assertEqual(selected.context["pending_companies"], [])
        self.login(self.reader)
        self.assertNotContains(self.client.get(reverse("overview")), empty.slug)
        self.assertEqual(self.client.get(reverse("overview"), {"organization": empty.slug}).status_code, 404)
        owner = get_user_model().objects.create_user(username="synthetic-setup-only")
        Membership.objects.create(organization=empty, user=owner, role="admin")
        self.client.force_login(owner)
        own = self.client.get(reverse("overview"))
        self.assertEqual(own.context["main_companies"], [])
        self.assertContains(own, 'class="overview-pending-workspaces" open')

    @override_settings(DISTRO_CVE_ENABLED=False)
    def test_disabled_package_matching_is_not_presented_as_active_or_missing_manual_mapping(self):
        self.package()
        self.login()
        response = self.client.get(reverse("overview"))
        self.assertContains(response, "disabled by platform configuration")
        self.assertNotContains(response, "need a manufacturer/product mapping")
        self.assertTrue(response.context["companies"][0]["package_gaps"])

    def test_explicit_supplemental_watch_does_not_double_count_a_package_identity(self):
        self.reporter(state="ready")
        ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="nginx",
            source_url="https://vulnerability.circl.lu",
            last_success=timezone.now(),
            requested=False,
        )
        self.login()
        state = self.client.get(reverse("overview")).context["companies"][0]
        self.assertEqual((state["products"], state["configured"], state["watch_count"]), (1, 1, 1))
        self.assertEqual(state["unmapped"], 0)
