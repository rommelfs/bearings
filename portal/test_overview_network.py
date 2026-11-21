"""Overview network facts use explicit scoped assignments, including non-primary IPs."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import Asset, AssetIssue, NetBoxInstance
from .inventory_presentation import decorate_addresses, host_network_summary


class OverviewNetworkTests(Fixture):
    def setUp(self):
        self.asset.object_type = "virtualization.virtualmachine"
        self.asset.external_id = "10"
        self.asset.save()
        self.sa.mode = "central"
        self.sa.tenant_id = 1
        self.sa.instance = NetBoxInstance.objects.create(
            name="Overview network fixture", base_url="https://netbox.example.invalid"
        )
        self.sa.save()
        AssetIssue.objects.create(
            organization=self.a, asset=self.asset, kind="eol", priority="high", title="Review support"
        )
        self.login()

    def address(self, name, external_id, **kwargs):
        return Asset.objects.create(
            organization=self.a,
            source=self.sa,
            network_host=self.asset,
            name=name,
            kind="ip_address",
            object_type="ipam.ipaddress",
            external_id=str(external_id),
            upstream_data={"dns_name": "host.example.invalid", "assignment": {"interface": "eth0"}},
            **kwargs,
        )

    def test_assigned_dual_stack_appears_without_primary_and_does_not_leak_foreign_records(self):
        self.address("192.0.2.10/24", 41)
        self.address("2001:db8::10/64", 42)
        Asset.objects.create(
            organization=self.b,
            source=self.sb,
            network_host=self.asset,
            name="198.51.100.99/24",
            kind="ip_address",
            object_type="ipam.ipaddress",
            upstream_data={"dns_name": "foreign.example.invalid"},
        )
        response = self.client.get(reverse("overview"))
        context = response.context["priority_assets"][0]["context"]
        self.assertEqual([a["prefix"] for a in context["addresses"]], ["192.0.2.10/24", "2001:db8::10/64"])
        self.assertEqual(context["assigned_address_count"], 2)
        self.assertContains(response, "All 2 assigned IP addresses")
        self.assertContains(response, "host.example.invalid")
        self.assertNotContains(response, "198.51.100.99")
        self.assertNotContains(response, "foreign.example.invalid")
        self.assertFalse(any(a["primary"] for a in context["addresses"]))

    def test_primary_is_deduplicated_and_missing_assignments_are_labelled(self):
        self.address("192.0.2.10/24", 41, missing_since=timezone.now())
        self.asset.upstream_data = {"primary_ip4": "192.0.2.10/24", "primary_ip4_id": 41}
        self.asset.save()
        response = self.client.get(reverse("overview"))
        addresses = response.context["priority_assets"][0]["context"]["addresses"]
        self.assertEqual(len(addresses), 1)
        self.assertTrue(addresses[0]["primary"])
        self.assertTrue(addresses[0]["last_known"])
        self.assertContains(response, "last-known assignment")

    def test_previews_are_bounded_and_summary_does_not_perform_queries(self):
        for index in range(20):
            self.address(f"192.0.2.{index + 1}/24", index + 1)
        assets = [Asset.objects.select_related("source__instance", "organization").get(pk=self.asset.pk)]
        with CaptureQueriesContext(connection) as queries:
            decorate_addresses(assets)
        self.assertEqual(len(queries), 1)
        self.assertEqual(len(assets[0].address_preview), 16)
        with self.assertNumQueries(0):
            summary = host_network_summary(assets[0])
        self.assertTrue(summary["addresses_truncated"])
        self.assertEqual(summary["assigned_address_count"], 20)
        self.assertEqual(len(summary["addresses"]), 16)

    def test_no_dns_is_inferred_from_the_host_name(self):
        asset = Asset.objects.select_related("source__instance").get(pk=self.asset.pk)
        with self.assertNumQueries(0):
            summary = host_network_summary(asset)
        self.assertEqual(summary["addresses"], [])
        self.assertEqual(summary["dns_names"], [])
