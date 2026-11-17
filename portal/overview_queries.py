"""Bound dashboard query latency without caching scoped data or changing global DB settings."""

from contextlib import contextmanager
from time import perf_counter
from django.db import connection, transaction


class QueryTiming:
    def __init__(self):
        self.seconds = 0
        self.slowest = 0

    def __call__(self, execute, sql, params, many, context):
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed = perf_counter() - started
            self.seconds += elapsed
            self.slowest = max(self.slowest, elapsed)


@contextmanager
def overview_queries():
    """Avoid JIT compilation on small interactive dashboard queries.

    Complex authorization joins can cross PostgreSQL's estimated-cost thresholds,
    spending seconds compiling code for a bounded page. Keep the setting local to
    this transaction and restore it even when the caller has an outer transaction.
    SQL text, parameters and query results are never retained by the timer.
    """
    timing = QueryTiming()
    with connection.execute_wrapper(timing):
        if connection.vendor != "postgresql":
            yield timing
            return
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SHOW jit")
                previous = cursor.fetchone()[0]
                cursor.execute("SET LOCAL jit = off")
            # An exception rolls back the transaction/savepoint and its SET LOCAL.
            yield timing
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('jit', %s, true)", [previous])
