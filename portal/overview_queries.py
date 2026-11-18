"""Bound dashboard query latency without caching scoped data or changing global DB settings."""

from contextlib import contextmanager
from time import perf_counter
from django.db import connection, transaction, OperationalError


class QueryTiming:
    def __init__(self, budget_ms=None):
        self.deadline = perf_counter() + budget_ms / 1000 if budget_ms else None
        self.seconds = 0
        self.slowest = 0

    def __call__(self, execute, sql, params, many, context):
        if self.deadline and perf_counter() >= self.deadline:
            raise OperationalError("Overview section time budget exceeded")
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed = perf_counter() - started
            self.seconds += elapsed
            self.slowest = max(self.slowest, elapsed)


@contextmanager
def overview_queries(*, query_timeout_ms=None, budget_ms=None, planning_limit=None):
    """Bound compilation, optional join planning and execution for dashboard queries.

    Complex authorization joins can spend more time planning/compiling than
    executing a bounded page. Keep settings local to this transaction and restore
    them even when the caller has an outer transaction. SQL text, parameters and
    query results are never retained by the timer.
    """
    timing = QueryTiming(budget_ms)
    with connection.execute_wrapper(timing):
        if connection.vendor != "postgresql":
            yield timing
            return
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SHOW jit")
                previous = cursor.fetchone()[0]
                cursor.execute("SET LOCAL jit = off")
                previous_planning = None
                if planning_limit is not None:
                    if not 1 <= planning_limit <= 8:
                        raise ValueError("Invalid overview planning limit")
                    cursor.execute(
                        "SELECT current_setting('join_collapse_limit'), current_setting('from_collapse_limit')"
                    )
                    previous_planning = cursor.fetchone()
                    cursor.execute(
                        "SELECT set_config('join_collapse_limit',%s,true), set_config('from_collapse_limit',%s,true)",
                        [str(planning_limit), str(planning_limit)],
                    )
                previous_timeout = None
                if query_timeout_ms is not None:
                    if not 1 <= query_timeout_ms <= 30000:
                        raise ValueError("Invalid overview query timeout")
                    cursor.execute("SHOW statement_timeout")
                    previous_timeout = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, true)", [f"{query_timeout_ms}ms"]
                    )
            # An exception rolls back the transaction/savepoint and its SET LOCAL.
            yield timing
            with connection.cursor() as cursor:
                if previous_planning is not None:
                    cursor.execute(
                        "SELECT set_config('join_collapse_limit',%s,true), set_config('from_collapse_limit',%s,true)",
                        previous_planning,
                    )
                if previous_timeout is not None:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true)", [previous_timeout])
                cursor.execute("SELECT set_config('jit', %s, true)", [previous])
