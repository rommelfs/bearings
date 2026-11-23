"""Forward-only stock histories enforce current scope and bulk policy changes."""

from datetime import timedelta
from unittest import skipUnless
from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from .tests import Fixture
from .models import NationalDailySnapshot, NationalHistoryPolicy, NationalState, SourceRecord, Membership
from .national_history import capture_daily, stock_history
from .national_snapshots import refresh_pending


@skipUnless(connection.vendor == "postgresql", "Historical policy guards require PostgreSQL")
class NationalHistoryTests(Fixture):
    def refresh(self):
        refresh_pending(limit=100)

    def snapshot(self):
        self.refresh()
        capture_daily()
        return NationalDailySnapshot.objects.get(organization=self.a)

    def test_first_capture_does_not_backfill_and_zero_stocks_are_real_samples(self):
        snap = self.snapshot()
        result = stock_history(self.analyst)
        self.assertEqual(result["complete_days"], 1)
        chart = result["charts"][0]
        self.assertTrue(chart["show_chart"])
        self.assertEqual(chart["rows"][-1]["counts"], [0, 0, 0, 0, 0])
        self.assertEqual(chart["rows"][0]["counts"], [None, None, None, None, None])
        self.assertEqual(snap.coverage_counts["inventory_assets"], 1)
        self.assertEqual(result["machine_chart"]["rows"][-1]["counts"], [None, 0.0])
        self.assertEqual(result["machine_chart"]["rows"][0]["counts"], [None, None])
        self.assertEqual(snap.operator_counts["machine_total"], 1)
        # Old raw review counts do not imply old machine measurements.
        old = dict(snap.operator_counts)
        old.pop("machine_metric_version")
        NationalDailySnapshot.objects.filter(pk=snap.pk).update(operator_counts=old)
        self.assertEqual(stock_history(self.analyst)["machine_chart"]["rows"][-1]["counts"], [None, None])
        NationalDailySnapshot.objects.filter(pk=snap.pk).update(operator_counts=snap.operator_counts)

        self.assertEqual(snap.coverage_counts["installations"], 1)
        self.assertEqual(capture_daily(), 0)

    def test_updating_current_day_keeps_prior_days_and_does_not_capture_dirty_summaries(self):
        snap = self.snapshot()
        NationalDailySnapshot.objects.filter(pk=snap.pk).update(day=timezone.localdate() - timedelta(days=1))
        finding = self.record_finding()
        self.assertTrue(NationalState.objects.get(organization=self.a).dirty)
        capture_daily()
        self.assertEqual(NationalDailySnapshot.objects.filter(organization=self.a).count(), 1)
        self.refresh()
        capture_daily()
        self.assertEqual(stock_history(self.analyst)["charts"][0]["rows"][-2]["counts"], [0, 0, 0, 0, 0])
        self.assertEqual(stock_history(self.analyst)["charts"][0]["rows"][-1]["counts"], [1, 0, 1, 0, 0])
        finding.status = "resolved"
        finding.save()
        self.refresh()
        # The previous hour's stock remains a labelled observation until due again.
        self.assertEqual(capture_daily(), 0)
        NationalDailySnapshot.objects.filter(day=timezone.localdate()).update(
            captured_at=timezone.now() - timedelta(hours=2)
        )
        capture_daily()
        self.assertEqual(stock_history(self.analyst)["charts"][0]["rows"][-1]["counts"], [0, 0, 0, 0, 0])
        self.assertEqual(NationalDailySnapshot.objects.filter(organization=self.a).count(), 2)

    def test_bulk_sharing_change_withholds_history_and_retains_raw_observations(self):
        finding = self.record_finding(shareable=True)
        self.snapshot()
        before = NationalHistoryPolicy.objects.get(organization=self.a).generation
        SourceRecord.objects.filter(pk=finding.record_id).update(shareable=False)
        self.assertNotEqual(NationalHistoryPolicy.objects.get(organization=self.a).generation, before)
        self.assertEqual(stock_history(self.analyst)["complete_days"], 0)
        self.assertTrue(NationalDailySnapshot.objects.filter(organization=self.a).exists())
        self.a.operator_visibility = False
        self.a.save()
        Membership.objects.create(organization=self.a, user=self.analyst, role="reader")
        self.refresh()
        capture_daily()
        self.assertEqual(stock_history(self.analyst)["charts"][0]["rows"][-1]["counts"], [0, 0, 0, 0, 0])
        self.assertEqual(stock_history(self.platform)["charts"][0]["rows"][-1]["counts"], [1, 0, 1, 0, 0])

    def test_new_companies_or_partial_capture_produce_gaps_and_revoked_orgs_are_omitted(self):
        self.snapshot()
        NationalDailySnapshot.objects.filter(
            organization=self.b
        ).delete()  # Simulate a capture still pending.
        self.b.operator_visibility = True
        self.b.save()
        self.assertEqual(stock_history(self.analyst)["complete_days"], 0)
        self.assertEqual(stock_history(self.analyst)["partial_days"], 1)
        self.refresh()
        capture_daily()
        self.assertEqual(stock_history(self.analyst)["companies"], 2)
        self.assertEqual(stock_history(self.analyst)["complete_days"], 1)
        self.b.operator_visibility = False
        self.b.save()
        self.assertEqual(stock_history(self.analyst)["companies"], 1)
        self.assertEqual(stock_history(self.analyst)["charts"][1]["rows"][-1]["counts"], [1, 1])

    def test_ownership_transfer_invalidates_old_scope_but_version_changes_do_not(self):
        from .models import Installation

        self.snapshot()
        before = NationalHistoryPolicy.objects.get(organization=self.a).generation
        Installation.objects.filter(pk=self.installation.pk).update(version="2.5.51")
        self.assertEqual(NationalHistoryPolicy.objects.get(organization=self.a).generation, before)
        Installation.objects.filter(pk=self.installation.pk).update(asset=self.other)
        self.assertNotEqual(NationalHistoryPolicy.objects.get(organization=self.a).generation, before)
        self.assertEqual(stock_history(self.analyst)["complete_days"], 0)

    def test_capture_coverage_agrees_with_live_indicators_and_history_queries_are_bounded(self):
        from django.test.utils import CaptureQueriesContext
        from .circl import dashboard

        self.snapshot()
        live = dashboard(self.analyst, section="summary")
        snap = NationalDailySnapshot.objects.get(organization=self.a)
        for name in ("inventory_assets", "installations", "unknown", "no_contact"):
            self.assertEqual(snap.coverage_counts[name], live["counts"][name])
        for name in ("stale", "missing", "errors", "synthetic"):
            self.assertEqual(snap.coverage_counts[name], live["sources"][name])
        with CaptureQueriesContext(connection) as before:
            stock_history(self.analyst)
        # Additional dates do not introduce one query per point/company.
        for days in range(1, 12):
            original = NationalDailySnapshot.objects.get(organization=self.a, day=timezone.localdate())
            original.pk = None
            original.day = timezone.localdate() - timedelta(days=days)
            original.save(force_insert=True)
        with CaptureQueriesContext(connection) as after:
            result = stock_history(self.analyst)
        self.assertEqual(result["complete_days"], 12)
        self.assertEqual(len(after), len(before))

    def test_raw_organization_reset_cannot_reassociate_old_history_with_reused_ids(self):
        from .models import Organization

        self.snapshot()
        old_id = self.a.pk
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("TRUNCATE portal_organization CASCADE")
        Organization.objects.create(pk=old_id, name="New scope", slug="new-scope", operator_visibility=True)
        self.assertEqual(stock_history(self.analyst)["complete_days"], 0)

    def test_refresh_command_automatically_starts_recording_without_web_writes(self):
        from io import StringIO
        from django.core.management import call_command

        output = StringIO()
        call_command("refresh_national", limit=500, stdout=output)
        self.assertTrue(NationalDailySnapshot.objects.filter(organization=self.a).exists())
        self.assertIn("Captured", output.getvalue())
        count = NationalDailySnapshot.objects.count()
        self.login(self.analyst)
        self.client.get(reverse("circl-panel", args=["history"]))
        self.assertEqual(NationalDailySnapshot.objects.count(), count)

    def test_private_operator_endpoint_and_timezone_separation(self):
        self.snapshot()
        self.login(self.reader)
        self.assertEqual(self.client.get(reverse("circl-panel", args=["history"])).status_code, 403)
        self.login(self.analyst)
        response = self.client.get(reverse("circl-panel", args=["history"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review indicators over time")
        self.assertIn("no-store", response["Cache-Control"])
        with timezone.override("Europe/Luxembourg"):
            self.assertEqual(stock_history(self.analyst)["complete_days"], 0)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock serialization")
class HistorySerializationTests(TransactionTestCase):
    def test_capture_and_bulk_sharing_write_serialize_without_revealing_old_counts(self):
        import threading
        from django.db import transaction, close_old_connections
        from .models import Organization, InventorySource, Asset, Product, Installation, Finding
        from .national_snapshots import InternalReader

        org = Organization.objects.create(
            name="Synthetic history race", slug="history-race", operator_visibility=True
        )
        source = InventorySource.objects.create(organization=org, mode="development")
        asset = Asset.objects.create(organization=org, source=source, name="synthetic")
        product = Product.objects.create(organization=org, name="Synthetic product")
        installed = Installation.objects.create(asset=asset, product=product, version="1")
        record = SourceRecord.objects.create(
            organization=org,
            source="fixture://race",
            external_id="CVE-2099-99999",
            payload={},
            shareable=True,
        )
        Finding.objects.create(organization=org, installation=installed, record=record, explanation="fixture")
        refresh_pending()
        capture_daily()
        NationalDailySnapshot.objects.update(captured_at=timezone.now() - timedelta(hours=2))
        started = threading.Event()
        errors = []

        def write():
            close_old_connections()
            try:
                with transaction.atomic():
                    Organization.objects.select_for_update().get(pk=org.pk)
                    started.set()
                    SourceRecord.objects.filter(pk=record.pk).update(shareable=False)
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        with transaction.atomic():
            NationalState.objects.select_for_update().get(organization=org)
            worker = threading.Thread(target=write)
            worker.start()
            self.assertTrue(started.wait(2))
            self.assertEqual(capture_daily(), 1)
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(stock_history(InternalReader())["complete_days"], 0)
        self.assertEqual(NationalDailySnapshot.objects.count(), 1)
