"""Refusal and resource-budget checks for the destructive-volume-free scale harness."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.test import SimpleTestCase, TransactionTestCase
from . import models as m
from .scale_benchmark import RequestProfile, guard, seed


class ScaleGuardTests(SimpleTestCase):
    def test_normal_application_database_is_refused(self):
        with patch.dict("os.environ", {"BEARINGS_SCALE_TEST": "0"}):
            with self.assertRaises(CommandError):
                guard()

    def test_opt_in_alone_cannot_enable_normal_settings(self):
        with patch.dict(
            "os.environ", {"BEARINGS_SCALE_TEST": "1", "DJANGO_SETTINGS_MODULE": "config.settings"}
        ):
            with self.assertRaises(CommandError):
                guard()

    def test_query_budget_stops_sql_before_execution(self):
        execute = Mock(return_value=None)
        profile = RequestProfile(queries=1)
        profile(execute, "SELECT 1", (), False, {})
        with self.assertRaises(OperationalError):
            profile(execute, "SELECT 2", (), False, {})
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(profile.guard, "query_count")

    def test_expired_wall_budget_stops_next_query(self):
        execute = Mock()
        with patch("portal.scale_benchmark.perf_counter", side_effect=[0, 13]):
            profile = RequestProfile(seconds=12)
            with self.assertRaises(OperationalError):
                profile(execute, "SELECT 1", (), False, {})
        execute.assert_not_called()
        self.assertEqual(profile.guard, "wall_time")


class ScaleFixtureTests(TransactionTestCase):
    def test_small_fixture_has_consistent_owned_records_and_one_owner_company(self):
        if connection.vendor != "postgresql":
            self.skipTest("The scale lab deliberately requires PostgreSQL")
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS bearings_scale_manifest")
        try:
            with (
                tempfile.TemporaryDirectory() as temporary,
                patch("portal.scale_benchmark.OUTPUT", Path(temporary)),
            ):
                seed(2, 10)
                self.assertEqual(m.Organization.objects.count(), 2)
                self.assertEqual(m.Asset.objects.count(), 20)
                self.assertEqual(m.Installation.objects.count(), 20)
                self.assertEqual(m.Finding.objects.count(), 12)
                self.assertEqual(m.AssetIssue.objects.count(), 18)
                self.assertEqual(m.DiscoveryRevision.objects.count(), 24)
                self.assertEqual(m.Membership.objects.values("user").distinct().count(), 2)
                self.assertFalse(m.ProductWatch.objects.filter(enabled=True).exists())
                for issue in m.AssetIssue.objects.select_related(
                    "asset__source",
                    "installation__product",
                    "finding__record",
                    "finding__installation__asset",
                ):
                    issue.full_clean()
                with self.assertRaisesMessage(CommandError, "already has a manifest"):
                    seed(2, 10)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS bearings_scale_manifest")
