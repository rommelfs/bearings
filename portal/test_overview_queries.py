"""Interactive PostgreSQL queries must not compile a dashboard or change other transactions."""

from unittest import skipUnless
from django.db import connection, DatabaseError, transaction
from django.test import TestCase
from .overview_queries import overview_queries


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL local JIT settings")
class OverviewQueryTests(TestCase):
    def setting(self):
        with connection.cursor() as cursor:
            cursor.execute("SHOW jit")
            return cursor.fetchone()[0]

    def test_prior_jit_setting_is_restored_inside_an_existing_transaction(self):
        for previous in ["on", "off"]:
            with self.subTest(previous=previous), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('jit', %s, true)", [previous])
                with overview_queries() as timing:
                    self.assertEqual(self.setting(), "off")
                self.assertEqual(self.setting(), previous)
                self.assertGreater(timing.seconds, 0)
                self.assertGreater(timing.slowest, 0)

    def test_failed_query_rolls_back_local_setting_and_keeps_connection_usable(self):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL jit = on")
        with self.assertRaises(DatabaseError), overview_queries():
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 / 0")
        self.assertEqual(self.setting(), "on")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_aggressive_optimizer_thresholds_do_not_compile_dashboard_queries(self):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL jit = on")
            for setting in ["jit_above_cost", "jit_inline_above_cost", "jit_optimize_above_cost"]:
                cursor.execute(f"SET LOCAL {setting} = 0")
        with overview_queries():
            with connection.cursor() as cursor:
                cursor.execute("EXPLAIN (ANALYZE, FORMAT JSON) SELECT sum(i) FROM generate_series(1, 10) i")
                plan = cursor.fetchone()[0][0]
                self.assertNotIn("JIT", plan)
        self.assertEqual(self.setting(), "on")

    def test_statement_timeout_is_local_restored_and_cancels_slow_query(self):
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            previous = cursor.fetchone()[0]
        with overview_queries(query_timeout_ms=25):
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                self.assertEqual(cursor.fetchone()[0], "25ms")
        with self.assertRaises(DatabaseError), overview_queries(query_timeout_ms=25):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(0.1)")
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], previous)
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
