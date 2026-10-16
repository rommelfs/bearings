"""Import contracts exercise real paging/scope validation with synthetic HTTP responses."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase
from .models import InventorySource, Organization
import copy
import io
from datetime import timedelta
from unittest.mock import patch
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone
from .tests import Fixture
from .connectors.http import ConnectorError
from .connectors.netbox import write_asset
from .inventory import refresh_inventory
from .models import Asset, InventoryWrite, NetBoxInstance, Installation
from .services import process_write, query_inventory


class InventoryImportTests(Fixture):
    def setUp(self):
        self.alpha = NetBoxInstance.objects.create(
            name="alpha", base_url="https://alpha.example.invalid", token_env_var="NETBOX_ALPHA_TOKEN"
        )
        self.beta = NetBoxInstance.objects.create(
            name="beta",
            base_url="https://beta.example.invalid",
            token_env_var="NETBOX_BETA_TOKEN",
            access_mode="read_write",
        )
        for source, instance, tenant in [(self.sa, self.alpha, 7), (self.sb, self.beta, 9)]:
            source.mode, source.instance, source.tenant_id = "external", instance, tenant
            source.save()
        self.records = {
            "devices": [{"id": 1, "name": "imported server", "status": {"value": "active"}}],
            "virtual-machines": [{"id": 1, "name": "imported VM"}],
            "ip-addresses": [
                {"id": 1, "address": "192.0.2.10/24", "role": {"value": "loopback", "label": "Loopback"}}
            ],
            "prefixes": [{"id": 1, "prefix": "192.0.2.0/24"}],
        }
        env = patch.dict(
            "os.environ", {"NETBOX_ALPHA_TOKEN": "synthetic-alpha", "NETBOX_BETA_TOKEN": "synthetic-beta"}
        )
        env.start()
        self.addCleanup(env.stop)
        approved = patch("portal.connectors.netbox.approved_base", side_effect=lambda url, private=False: url)
        approved.start()
        self.addCleanup(approved.stop)
        self.http = patch("portal.connectors.netbox.request_json", side_effect=self.response).start()
        self.addCleanup(patch.stopall)

    def response(self, method, url, **kwargs):
        rows = copy.deepcopy(self.records[url.rstrip("/").split("/")[-1]])
        for row in rows:
            row.setdefault("tenant", {"id": kwargs["params"]["tenant_id"]})
        return {"count": len(rows), "results": rows, "next": None}

    def imported(self, kind="server", source=None):
        return Asset.objects.get(source=source or self.sa, kind=kind, external_id="1")

    def test_all_four_types_are_idempotent_and_isolated_across_instances(self):
        for source in [self.sa, self.sb]:
            self.assertEqual(refresh_inventory(source.pk)["created"], 4)
            result = refresh_inventory(source.pk)
            self.assertEqual((result["created"], result["unchanged"]), (0, 4))
        self.assertNotEqual(self.imported().pk, self.imported(source=self.sb).pk)
        self.assertEqual(self.sa.asset_set.exclude(external_id="").count(), 4)
        self.assertEqual(self.imported("ip_address").upstream_data["address"], "192.0.2.10/24")
        self.assertEqual(self.imported("prefix").source_url, "https://alpha.example.invalid/ipam/prefixes/1/")
        self.assertTrue(all(c.args[0] == "GET" for c in self.http.call_args_list))
        keys = {c.kwargs["headers"]["Authorization"] for c in self.http.call_args_list}
        self.assertEqual(keys, {"Bearer synthetic-alpha", "Bearer synthetic-beta"})

    def test_refresh_updates_upstream_fields_preserving_local_assessments(self):
        refresh_inventory(self.sa.pk)
        asset = self.imported()
        asset.criticality, asset.lifecycle, asset.kind, asset.responsible_team = (
            "high",
            "retired",
            "laptop",
            "local team",
        )
        asset.save()
        installation = Installation.objects.create(asset=asset, product=self.product, version="1.2")
        finding = self.record_finding()
        finding.installation = installation
        finding.analyst_applicability = "not_affected"
        finding.save()
        self.records["devices"][0].update(name="upstream changed", status={"value": "offline"})
        result = refresh_inventory(self.sa.pk)
        asset.refresh_from_db()
        finding.refresh_from_db()
        self.assertEqual(result["updated"], 1)
        self.assertEqual((asset.name, asset.upstream_data["status"]), ("upstream changed", "offline"))
        self.assertEqual(
            (asset.criticality, asset.lifecycle, asset.kind, asset.responsible_team),
            ("high", "retired", "laptop", "local team"),
        )
        self.assertEqual(asset.installations.get().version, "1.2")
        self.assertEqual(finding.analyst_applicability, "not_affected")

    def test_missing_retained_reviewed_and_reappearing_without_identity_change(self):
        refresh_inventory(self.sa.pk)
        asset = self.imported()
        row = self.records["devices"].pop()
        self.assertEqual(refresh_inventory(self.sa.pk)["missing"], 1)
        asset.refresh_from_db()
        missing = asset.missing_since
        self.assertIsNotNone(missing)
        self.login()
        self.assertEqual(
            self.client.post(
                self.url("review-missing-asset", pk=asset.pk), {"reason": "Checking reassignment"}
            ).status_code,
            302,
        )
        asset.refresh_from_db()
        reviewed = asset.missing_reviewed_at
        refresh_inventory(self.sa.pk)
        asset.refresh_from_db()
        self.assertEqual((asset.missing_since, asset.missing_reviewed_at), (missing, reviewed))
        self.records["devices"].append(row)
        self.assertEqual(refresh_inventory(self.sa.pk)["reappeared"], 1)
        asset.refresh_from_db()
        self.assertIsNone(asset.missing_since)
        self.assertIsNone(asset.missing_reviewed_at)
        self.assertEqual(self.imported().pk, asset.pk)

    def test_failure_on_last_endpoint_rolls_back_every_projection_and_success(self):
        refresh_inventory(self.sa.pk)
        self.sa.refresh_from_db()
        success, summary = self.sa.last_import_success, self.sa.import_summary
        self.records["devices"][0]["name"] = "must not persist"

        def fail(method, url, **kwargs):
            if "/prefixes/" in url:
                raise ConnectorError("untrusted secret payload must not persist")
            return self.response(method, url, **kwargs)

        self.http.side_effect = fail
        with self.assertRaises(ConnectorError):
            refresh_inventory(self.sa.pk)
        self.sa.refresh_from_db()
        self.assertEqual(self.imported().name, "imported server")
        self.assertEqual((self.sa.last_import_success, self.sa.import_summary), (success, summary))
        self.assertNotIn("secret", self.sa.import_error)
        self.assertFalse(self.sa.asset_set.filter(missing_since__isnull=False).exists())

    def test_invalid_or_wrong_tenant_data_discard_entire_import(self):
        for kind, invalid in [
            ("devices", {"id": 1, "name": "bad", "tenant": {"id": 9}}),
            ("devices", {"id": 1, "name": "x" * 181}),
            ("virtual-machines", {"id": 1, "name": "VM", "status": 12}),
            ("ip-addresses", {"id": 1, "address": "invalid"}),
            ("prefixes", {"id": 1, "prefix": "192.0.2.7/24"}),
        ]:
            with self.subTest(kind=kind):
                before = copy.deepcopy(self.records)
                self.records[kind] = [invalid]
                with self.assertRaises(ConnectorError):
                    refresh_inventory(self.sa.pk)
                self.assertFalse(self.sa.asset_set.exclude(external_id="").exists())
                self.records = before

    def test_pagination_is_complete_before_import_and_partial_pages_do_not_mark_missing(self):
        def pages(method, url, **kwargs):
            if "/dcim/devices/" not in url:
                return self.response(method, url, **kwargs)
            offset = kwargs["params"]["offset"]
            return {
                "count": 2,
                "results": [{"id": offset + 1, "name": f"page {offset}", "tenant": {"id": 7}}],
                "next": url + "?tenant_id=7&limit=100&offset=1" if offset == 0 else None,
            }

        self.http.side_effect = pages
        self.assertEqual(refresh_inventory(self.sa.pk)["created"], 5)
        self.http.side_effect = lambda *a, **k: {"count": 2, "results": [], "next": None}
        with self.assertRaises(ConnectorError):
            refresh_inventory(self.sa.pk)
        self.assertFalse(self.sa.asset_set.filter(missing_since__isnull=False).exists())

    def test_lost_write_ack_is_adopted_before_retry_without_duplicate(self):
        self.asset.kind, self.asset.state = "laptop", "failed"
        self.asset.save()
        job = InventoryWrite.objects.create(asset=self.asset)
        self.records["devices"][0]["custom_fields"] = {"bearings_id": str(self.asset.pk)}
        self.assertEqual(refresh_inventory(self.sa.pk)["reconciled"], 1)
        self.asset.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual((self.asset.external_id, self.asset.state), ("1", "synced"))
        self.assertIsNotNone(job.completed_at)
        with patch("portal.services.write_asset") as write:
            process_write(job.pk, force=True)
            write.assert_not_called()
        self.assertEqual(
            self.sa.asset_set.filter(object_type="dcim.device").exclude(external_id="").count(), 1
        )

    def test_identity_conflict_rolls_back_adoption_and_job_completion(self):
        job = InventoryWrite.objects.create(asset=self.asset)
        self.records["devices"][0]["custom_fields"] = {"bearings_id": str(self.asset.pk)}
        self.records["devices"].append(
            {"id": 2, "name": "conflicting", "custom_fields": {"bearings_id": str(self.asset.pk)}}
        )
        with self.assertRaises(ConnectorError):
            refresh_inventory(self.sa.pk)
        self.asset.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(self.asset.external_id, "")
        self.assertIsNone(job.completed_at)
        self.assertFalse(self.sa.asset_set.exclude(external_id="").exists())

    def test_foreign_bearings_marker_does_not_adopt_another_organization_asset(self):
        self.records["devices"][0]["custom_fields"] = {"bearings_id": str(self.other.pk)}
        refresh_inventory(self.sa.pk)
        self.other.refresh_from_db()
        self.assertEqual(self.other.external_id, "")
        self.assertNotEqual(self.imported().pk, self.other.pk)

    def test_due_schedule_pause_manual_queue_and_failure_throttling(self):
        self.sa.import_enabled = False
        self.sa.save()
        self.assertIsNone(refresh_inventory(self.sa.pk, due=True))
        self.http.assert_not_called()
        self.sa.import_requested = True
        self.sa.save()
        self.assertIsNotNone(refresh_inventory(self.sa.pk, due=True))
        self.assertIsNone(refresh_inventory(self.sa.pk, due=True))
        self.sa.refresh_from_db()
        self.assertFalse(self.sa.import_requested)
        self.assertFalse(self.sa.import_stale)
        self.sa.import_enabled = True
        self.sa.last_import_attempt = timezone.now() - timedelta(minutes=16)
        self.sa.save()
        self.http.side_effect = ConnectorError("outage")
        with self.assertRaises(ConnectorError):
            refresh_inventory(self.sa.pk, due=True)
        self.assertIsNone(refresh_inventory(self.sa.pk, due=True))

    def test_cli_continues_other_sources_after_failure(self):
        self.alpha.enabled = False
        self.alpha.save()
        with self.assertRaises(CommandError):
            call_command("sync_netbox", all=True, stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(self.sb.asset_set.exclude(external_id="").count(), 4)
        self.assertFalse(self.sa.asset_set.exclude(external_id="").exists())
        self.assertTrue(all(c.args[0] == "GET" for c in self.http.call_args_list))

    def test_query_health_is_separate_from_import_and_network_assets_cannot_be_submitted(self):
        query_inventory(self.sa, ["devices"])
        self.sa.refresh_from_db()
        self.assertIsNone(self.sa.last_import_success)
        self.assertFalse(self.sa.asset_set.exclude(external_id="").exists())
        refresh_inventory(self.sa.pk)
        with self.assertRaises(ConnectorError):
            write_asset(self.imported("prefix"))

    def test_portal_import_queue_and_missing_reviews_enforce_membership_csrf(self):
        refresh_inventory(self.sa.pk)
        asset = self.imported()
        self.records["devices"] = []
        refresh_inventory(self.sa.pk)
        self.login(self.reader)
        self.assertEqual(self.client.post(self.url("request-inventory-import")).status_code, 403)
        self.assertEqual(
            self.client.post(self.url("review-missing-asset", pk=asset.pk), {"reason": "bad"}).status_code,
            403,
        )
        self.login()
        self.assertEqual(self.client.get(self.url("request-inventory-import")).status_code, 405)
        self.assertEqual(self.client.post(self.url("request-inventory-import", self.b)).status_code, 404)
        self.assertEqual(
            self.client.post(
                self.url("review-missing-asset", pk=self.other.pk), {"reason": "bad"}
            ).status_code,
            404,
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url("request-inventory-import")).status_code, 403)
        self.assertEqual(self.client.post(self.url("request-inventory-import")).status_code, 302)
        self.sa.refresh_from_db()
        self.assertTrue(self.sa.import_requested)
        self.http.reset_mock()
        self.client.post(self.url("request-inventory-import"))
        self.http.assert_not_called()  # web queues only, never calls the network

    def test_upstream_fields_escaped_and_raw_custom_fields_not_exposed(self):
        self.records["devices"][0].update(
            name='<script>alert("x")</script>',
            custom_fields={"private_note": "must not leak"},
            url="javascript:alert(1)",
        )
        refresh_inventory(self.sa.pk)
        self.login()
        response = self.client.get(self.url("organization"))
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        response = self.client.get(self.url("api-inventory"))
        self.assertNotContains(response, "must not leak")
        self.assertNotContains(response, "javascript:")
        self.assertContains(response, "last_success")
        self.assertEqual(self.client.get(self.url("api-inventory", self.b)).status_code, 404)

    def test_large_inventory_is_paginated_within_the_visible_organization(self):
        refresh_inventory(self.sa.pk)
        Asset.objects.bulk_create(
            [
                Asset(organization=self.a, source=self.sa, name=f"bulk-{i:03}", kind="server")
                for i in range(101)
            ]
        )
        self.login()
        response = self.client.get(self.url("organization"))
        self.assertEqual(len(response.context["inventory_page"]), 50)
        response = self.client.get(self.url("api-inventory")).json()
        self.assertEqual((response["pagination"]["count"], len(response["assets"])), (106, 100))
        response = self.client.get(self.url("api-inventory") + "?page=2").json()
        self.assertEqual(len(response["assets"]), 6)
        self.assertFalse(any(a["name"] == "beta-secret" for a in response["assets"]))

    def test_operator_configuration_does_not_overwrite_new_import_health(self):
        from types import SimpleNamespace
        from django.contrib import admin
        from .admin import SourceAdmin

        stale = type(self.sa).objects.get(pk=self.sa.pk)
        refresh_inventory(self.sa.pk)
        stale.import_enabled = False
        SourceAdmin(type(self.sa), admin.site).save_model(
            SimpleNamespace(user=self.platform),
            stale,
            SimpleNamespace(changed_data=["import_enabled"]),
            True,
        )
        self.sa.refresh_from_db()
        self.assertIsNotNone(self.sa.last_import_success)
        self.assertEqual(self.sa.import_summary["total"], 4)
        self.assertFalse(self.sa.import_enabled)

    def test_browser_links_use_a_separate_https_base_without_changing_api_target(self):
        from django.core.exceptions import ValidationError

        self.alpha.browser_url = "https://localhost:8443"
        self.alpha.full_clean()
        self.alpha.save()
        refresh_inventory(self.sa.pk)
        self.assertEqual(self.imported().source_url, "https://localhost:8443/dcim/devices/1/")
        self.assertTrue(
            all(c.args[1].startswith("https://alpha.example.invalid/") for c in self.http.call_args_list)
        )
        self.alpha.browser_url = "https://user:secret@netbox.example.invalid"
        with self.assertRaises(ValidationError):
            self.alpha.full_clean()


# Real concurrent transactions are meaningful on PostgreSQL, not SQLite's single-writer fallback.


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock validation")
class ConcurrentInventoryTests(TransactionTestCase):
    def setUp(self):
        org = Organization.objects.create(name="Concurrent", slug="concurrent")
        instance = NetBoxInstance.objects.create(
            name="concurrent",
            base_url="https://netbox.example.invalid",
            token_env_var="NETBOX_CONCURRENT_TOKEN",
        )
        self.source = InventorySource.objects.create(
            organization=org, mode="external", instance=instance, tenant_id=7
        )
        self.entered, self.release = Event(), Event()
        self.marker = None

    def query(self, source, kind):
        if kind != "devices":
            return []
        self.entered.set()
        if not self.release.wait(10):
            raise RuntimeError("Concurrency test release timeout")
        return [
            {
                "object_type": "dcim.device",
                "external_id": "1",
                "record": {"name": "concurrent device", "custom_fields": {"bearings_id": self.marker}},
            }
        ]

    def run_thread(self, function, *args, **kwargs):
        close_old_connections()
        try:
            return function(*args, **kwargs)
        finally:
            connections.close_all()

    def wait_for_source_lock(self):
        import time

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE '%%portal_inventorysource%%'"
                )
                if cursor.fetchone()[0]:
                    return
            time.sleep(0.01)
        self.fail("Second transaction did not wait for the source lock")

    def test_concurrent_due_imports_commit_one_snapshot(self):
        with patch("portal.inventory.query_objects", side_effect=self.query) as query:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.run_thread, refresh_inventory, self.source.pk, due=True)
                try:
                    self.assertTrue(self.entered.wait(5))
                    second = pool.submit(self.run_thread, refresh_inventory, self.source.pk, due=True)
                    self.wait_for_source_lock()
                finally:
                    self.release.set()
                self.assertEqual(first.result(timeout=10)["created"], 1)
                self.assertIsNone(second.result(timeout=10))
        self.assertEqual(query.call_count, 4)
        self.assertEqual(self.source.asset_set.count(), 1)

    def test_import_and_write_retry_share_source_lock_and_do_not_duplicate(self):
        asset = Asset.objects.create(
            organization=self.source.organization, source=self.source, name="pending", kind="server"
        )
        job = InventoryWrite.objects.create(asset=asset)
        self.marker = str(asset.pk)
        with (
            patch("portal.inventory.query_objects", side_effect=self.query),
            patch("portal.services.write_asset") as write,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.run_thread, refresh_inventory, self.source.pk)
                try:
                    self.assertTrue(self.entered.wait(5))
                    second = pool.submit(self.run_thread, process_write, job.pk, force=True)
                    self.wait_for_source_lock()
                finally:
                    self.release.set()
                self.assertEqual(first.result(timeout=10)["reconciled"], 1)
                second.result(timeout=10)
            write.assert_not_called()
        self.assertEqual(self.source.asset_set.count(), 1)
        job.refresh_from_db()
        self.assertIsNotNone(job.completed_at)
