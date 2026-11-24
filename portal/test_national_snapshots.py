"""Current policy, bulk invalidation, and refresh/write serialization of national read models."""

import threading
from unittest import skipUnless
from django.db import connection, transaction, close_old_connections
from django.test import TransactionTestCase, override_settings
from .tests import Fixture
from .models import (
    Organization,
    Membership,
    InventorySource,
    Asset,
    Product,
    Installation,
    SourceRecord,
    Finding,
    NationalState,
    NationalVersion,
)
from .national_snapshots import refresh_pending, _refresh
from .circl import dashboard
from .access import organizations_for


@skipUnless(connection.vendor == "postgresql", "PostgreSQL statement triggers and row locks")
@override_settings(NATIONAL_SNAPSHOT_THRESHOLD=0)
class SnapshotTests(Fixture):
    def refresh(self):
        refresh_pending(limit=100)

    def test_summaries_equal_live_counts_and_shared_policy(self):
        self.record_finding(shareable=False)
        self.refresh()
        counts = dashboard(self.analyst, section="summary")["counts"]
        self.assertEqual(counts["reviews"], 1)
        self.assertEqual(counts["inventory_assets"], 1)
        self.assertEqual(counts["unknown"], 1)
        self.assertEqual(counts["organizations"], 1)
        Membership.objects.create(user=self.analyst, organization=self.b, role="reader")
        product = Product.objects.create(organization=self.b, name="Private product")
        inst = Installation.objects.create(asset=self.other, product=product, version="1")
        record = SourceRecord.objects.create(
            organization=self.b, source="fixture", external_id="private", payload={}, shareable=False
        )
        Finding.objects.create(organization=self.b, installation=inst, record=record, explanation="private")
        self.refresh()
        self.assertEqual(dashboard(self.analyst, section="summary")["counts"]["reviews"], 1)
        # Live operator permission chooses the prebuilt audience; no stale privileged cache.
        Organization.objects.filter(pk=self.b.pk).update(operator_visibility=True)
        self.assertEqual(dashboard(self.analyst, section="summary")["counts"]["reviews"], 2)
        Organization.objects.filter(pk=self.b.pk).update(operator_visibility=False)
        Membership.objects.filter(user=self.analyst, organization=self.b).delete()
        self.assertEqual(dashboard(self.analyst, section="summary")["counts"]["organizations"], 1)

    def test_bulk_version_change_hides_old_data_and_refreshes(self):
        self.refresh()
        self.login(self.analyst)
        Installation.objects.filter(pk=self.installation.pk).update(version="9.9.9")
        self.assertTrue(NationalState.objects.get(pk=self.a.pk).dirty)
        self.assertEqual(self.client.get("/circl/panels/versions/").status_code, 503)
        self.refresh()
        r = self.client.get("/circl/panels/versions/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["versions"][0]["version"], "9.9.9")
        self.assertNotContains(r, "pending refresh")

    def test_health_receipts_do_not_rebuild_unchanged_inventory(self):
        from django.utils import timezone

        self.refresh()
        Asset.objects.filter(pk=self.asset.pk).update(name="Renamed server", upstream_data={"new": "receipt"})
        InventorySource.objects.filter(pk=self.sa.pk).update(
            import_error="source unavailable", last_import_attempt=timezone.now()
        )
        self.assertFalse(NationalState.objects.get(pk=self.a.pk).dirty)
        # Actual version/ownership changes still invalidate in the same transaction.
        Installation.objects.filter(pk=self.installation.pk).update(version="changed")
        self.assertTrue(NationalState.objects.get(pk=self.a.pk).dirty)

    def test_direct_sql_and_rollback_are_transactional(self):
        self.refresh()
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute(
                    "UPDATE portal_installation SET version=%s WHERE id=%s", ["raw", self.installation.pk]
                )
            self.assertTrue(NationalState.objects.get(pk=self.a.pk).dirty)
            transaction.set_rollback(True)
        self.assertFalse(NationalState.objects.get(pk=self.a.pk).dirty)
        self.assertNotEqual(Installation.objects.get(pk=self.installation.pk).version, "raw")

    def test_administrative_truncate_invalidates_remaining_derived_rows(self):
        self.refresh()
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("TRUNCATE portal_installation CASCADE")
        self.assertTrue(NationalState.objects.get(pk=self.a.pk).dirty)
        self.login(self.analyst)
        self.assertEqual(self.client.get("/circl/panels/versions/").status_code, 503)

    def test_dirty_partial_results_are_explicit(self):
        self.refresh()
        Organization.objects.filter(pk=self.b.pk).update(operator_visibility=True)
        Installation.objects.filter(pk=self.installation.pk).update(version="changed")
        result = dashboard(self.analyst, section="summary")
        self.assertEqual(result["coverage"]["pending"], 1)
        self.assertEqual(result["counts"]["inventory_assets"], 1)
        self.login(self.analyst)
        self.assertContains(self.client.get("/circl/panels/summary/"), "totals below are incomplete")

    def test_inconsistent_product_cannot_reach_derived_counts(self):
        self.record_finding()
        self.refresh()
        foreign = Product.objects.create(organization=self.b, name="foreign")
        Installation.objects.filter(pk=self.installation.pk).update(product=foreign)
        self.refresh()
        data = dashboard(self.analyst, section="summary")["counts"]
        self.assertEqual(data["reviews"], 0)
        self.assertEqual(data["installations"], 0)
        self.assertEqual(dashboard(self.analyst, section="versions")["versions"], [])

    def test_prepared_counts_versions_and_earliest_trends_equal_live_queries(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import (
            ProductWatch,
            SourceRecordRevision,
            DiscoveryMatch,
            DiscoveryRevision,
            FindingHistory,
        )

        finding = self.record_finding()
        watch = ProductWatch.objects.create(
            product=self.product,
            vendor="example",
            product_key="example",
            source_url="https://vulnerability.circl.lu",
            enabled=False,
        )
        revision = SourceRecordRevision.objects.create(
            record=finding.record, content_hash="0" * 64, payload={}
        )
        match = DiscoveryMatch.objects.create(
            watch=watch,
            finding=finding,
            evidence_revision=revision,
            input_hash="0" * 64,
            explanation="fixture",
            result="potential",
        )
        for i, days in [(1, 20), (2, 1)]:
            DiscoveryRevision.objects.create(
                match=match,
                fingerprint=str(i) * 64,
                snapshot={},
                created_at=timezone.now() - timedelta(days=days),
            )
        FindingHistory.objects.create(
            finding=finding, previous_status="new", status="resolved", reason="fixture"
        )
        FindingHistory.objects.create(
            finding=finding, previous_status="resolved", status="resolved", reason="repeated"
        )
        Installation.objects.create(asset=self.asset, product=self.product, version="")
        with override_settings(NATIONAL_SNAPSHOT_THRESHOLD=100):
            live = dashboard(self.analyst)
        self.refresh()
        prepared = dashboard(self.analyst)
        for key in ["counts", "versions", "vulnerabilities", "trend", "sources"]:
            self.assertEqual(prepared[key], live[key], key)
        self.assertEqual(prepared["trend"]["new"], 1)
        self.assertEqual(prepared["trend"]["closures"], 1)
        self.assertEqual(prepared["versions"][0]["assets"], 1)
        self.assertEqual(prepared["versions"][0]["total"], 2)

    def test_research_projection_preserves_original_product_aliases_and_unknown_versions(self):
        from .circl import research

        alias = Product.objects.create(
            organization=self.a, name=self.product.name.lower(), identifier=self.product.identifier
        )
        Installation.objects.create(asset=self.asset, product=self.product, version="1.2.3")
        Installation.objects.create(asset=self.asset, product=alias, version="1.2.3")
        Installation.objects.create(asset=self.asset, product=alias, version="vendor-special")
        data = dict(
            product=self.product.name,
            product_match="exact",
            mode="range",
            minimum="1.0.0",
            maximum="2.0.0",
            bucket="matches",
        )
        with override_settings(NATIONAL_SNAPSHOT_THRESHOLD=100):
            raw, live_counts = research(self.analyst, data)
            live_ids = set(raw.values_list("pk", flat=True))
        self.refresh()
        prepared, counts = research(self.analyst, data)
        self.assertEqual(counts, live_counts)
        self.assertEqual(counts, dict(matches=2, unknown=1, unsupported=1))
        self.assertEqual(set(prepared.values_list("pk", flat=True)), live_ids)

    def test_new_organization_gets_dirty_state_and_merged_scope_stays_hidden(self):
        org = Organization.objects.create(name="New company", slug="new", operator_visibility=True)
        self.assertTrue(NationalState.objects.get(pk=org.pk).dirty)
        Organization.objects.filter(pk=org.pk).update(merged_into=self.a)
        self.assertNotIn(org.pk, organizations_for(self.analyst).values_list("pk", flat=True))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL concurrent refresh")
class ConcurrentSnapshotTests(TransactionTestCase):
    def test_write_committing_after_refresh_invalidates_the_new_snapshot(self):
        org = Organization.objects.create(name="Concurrent", slug="concurrent", operator_visibility=True)
        source = InventorySource.objects.create(organization=org, mode="manual")
        asset = Asset.objects.create(organization=org, source=source, name="server", kind="server")
        product = Product.objects.create(organization=org, name="Product")
        inst = Installation.objects.create(asset=asset, product=product, version="1.0")
        refresh_pending()
        started = threading.Event()
        errors = []

        def write():
            close_old_connections()
            try:
                started.set()
                Installation.objects.filter(pk=inst.pk).update(version="2.0")
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        NationalState.objects.filter(pk=org.pk).update(dirty=True)
        with transaction.atomic():
            NationalState.objects.select_for_update().get(pk=org.pk)
            worker = threading.Thread(target=write)
            worker.start()
            self.assertTrue(started.wait(2))
            _refresh([org.pk])
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(NationalState.objects.get(pk=org.pk).dirty)
        refresh_pending()
        self.assertFalse(NationalState.objects.get(pk=org.pk).dirty)
        self.assertEqual(NationalVersion.objects.get(organization=org).version, "2.0")


@skipUnless(connection.vendor == "postgresql", "PostgreSQL parent key lock race")
class ConcurrentProductSnapshotTests(TransactionTestCase):
    def test_parent_product_key_update_does_not_deadlock_refresh(self):
        import time

        org = Organization.objects.create(name="Key race", slug="key-race", operator_visibility=True)
        source = InventorySource.objects.create(organization=org, mode="manual")
        asset = Asset.objects.create(organization=org, source=source, name="asset", kind="server")
        product = Product.objects.create(organization=org, name="Before")
        Installation.objects.create(asset=asset, product=product, version="1.0")
        refresh_pending()
        started = threading.Event()
        errors = []
        pids = []

        def write():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.append(cursor.fetchone()[0])
                started.set()
                Product.objects.filter(pk=product.pk).update(name="After")
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        NationalState.objects.filter(pk=org.pk).update(dirty=True)
        with transaction.atomic():
            NationalState.objects.select_for_update().get(pk=org.pk)
            worker = threading.Thread(target=write)
            worker.start()
            self.assertTrue(started.wait(2))
            waiting = False
            for _ in range(100):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", [pids[0]])
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    waiting = True
                    break
                time.sleep(0.01)
            self.assertTrue(waiting)
            _refresh([org.pk])
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(NationalState.objects.get(pk=org.pk).dirty)
        refresh_pending()
        self.assertEqual(NationalVersion.objects.get(organization=org).name, "After")


@skipUnless(connection.vendor == "postgresql", "PostgreSQL repeatable read")
@override_settings(NATIONAL_SNAPSHOT_THRESHOLD=0)
class HybridSnapshotTests(TransactionTestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        from .access import ANALYST_GROUP

        self.actor = get_user_model().objects.create(username="hybrid-reader")
        self.actor.groups.add(Group.objects.get_or_create(name=ANALYST_GROUP)[0])
        self.inst = []
        for i in range(2):
            org = Organization.objects.create(
                name=f"Hybrid {i}", slug=f"hybrid-{i}", operator_visibility=True
            )
            source = InventorySource.objects.create(organization=org, mode="manual")
            asset = Asset.objects.create(
                organization=org, source=source, name=f"Hybrid server {i}", kind="server"
            )
            product = Product.objects.create(organization=org, name="Example")
            self.inst.append(Installation.objects.create(asset=asset, product=product, version="1.0.0"))
        refresh_pending()
        self.data = dict(
            product="Example", product_match="exact", mode="exact", version="1.0.0", bucket="matches"
        )

    def test_pending_company_is_combined_with_prepared_counts_without_missing_results(self):
        from .circl import research
        from .overview_queries import read_snapshot

        Installation.objects.filter(pk=self.inst[0].pk).update(version="2.0.0")
        data = {**self.data, "version": "2.0.0"}
        with read_snapshot():
            selected, counts = research(self.actor, data)
            self.assertEqual(counts["matches"], 1)
            self.assertEqual(list(selected.values_list("pk", flat=True)), [self.inst[0].pk])
        self.assertTrue(NationalState.objects.get(pk=self.inst[0].asset.organization_id).dirty)

    def test_writer_between_partition_queries_does_not_duplicate_or_lose_results(self):
        from .circl import research
        from .national_snapshots import research_projection
        from .overview_queries import read_snapshot

        errors = []

        def write():
            close_old_connections()
            try:
                Installation.objects.filter(pk=self.inst[0].pk).update(version="2.0.0")
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        with read_snapshot():
            self.assertIsNotNone(research_projection(self.actor, self.data))
            worker = threading.Thread(target=write)
            worker.start()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            selected, counts = research(self.actor, self.data)
            self.assertEqual(counts["matches"], 2)
            self.assertEqual(selected.count(), 2)
        with read_snapshot():
            selected, counts = research(self.actor, self.data)
            self.assertEqual(counts["matches"], 1)
            self.assertEqual(selected.count(), 1)

    def test_disposable_cache_reset_is_rebuilt_from_authoritative_inventory(self):
        from .models import NationalProductVersion

        NationalState.objects.all().delete()
        self.assertEqual(NationalState.objects.count(), 0)
        self.assertEqual(refresh_pending(), 2)
        self.assertEqual(NationalProductVersion.objects.count(), 2)
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE portal_nationalproductversion")
        self.assertEqual(NationalState.objects.filter(dirty=True).count(), 2)
        refresh_pending()
        self.assertEqual(NationalProductVersion.objects.count(), 2)

    def test_raw_organization_truncate_removes_private_derived_labels(self):
        from .models import NationalProductVersion

        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE portal_organization CASCADE")
        self.assertEqual(NationalState.objects.count(), 0)
        self.assertEqual(NationalProductVersion.objects.count(), 0)
        self.assertEqual(NationalVersion.objects.count(), 0)
