"""Bound dashboard query latency without caching scoped data or changing global DB settings."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from time import perf_counter
from django.db import connection, transaction, OperationalError

logger = logging.getLogger(__name__)


class OverviewBudgetExceeded(OperationalError):
    pass


class QueryTiming:
    def __init__(self, budget_ms=None):
        self.deadline = perf_counter() + budget_ms / 1000 if budget_ms else None
        self.seconds = 0
        self.slowest = 0

    def __call__(self, execute, sql, params, many, context):
        if self.deadline and perf_counter() >= self.deadline:
            raise OverviewBudgetExceeded("Overview section time budget exceeded")
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
        settings = {"jit": "off"}
        if planning_limit is not None:
            if not 1 <= planning_limit <= 8:
                raise ValueError("Invalid overview planning limit")
            settings.update(join_collapse_limit=str(planning_limit), from_collapse_limit=str(planning_limit))
        if query_timeout_ms is not None:
            if not 1 <= query_timeout_ms <= 30000:
                raise ValueError("Invalid overview query timeout")
            settings["statement_timeout"] = f"{query_timeout_ms}ms"
        names = list(settings)
        read_sql = "SELECT " + ", ".join("current_setting(%s)" for _ in names)
        write_sql = "SELECT " + ", ".join("set_config(%s,%s,true)" for _ in names)

        def parameters(values):
            return [value for pair in zip(names, values) for value in pair]

        with transaction.atomic():
            # Read, apply and restore in three round trips regardless of how many
            # protections are enabled. Keep reads separate from writes so SQL
            # expression evaluation order cannot change the saved prior values.
            with connection.cursor() as cursor:
                cursor.execute(read_sql, names)
                previous = cursor.fetchone()
                cursor.execute(write_sql, parameters(settings.values()))
            # An exception rolls back the transaction/savepoint and its SET LOCAL.
            yield timing
            with connection.cursor() as cursor:
                cursor.execute(write_sql, parameters(previous))


def bounded_list(view):
    """Keep expensive global lists bounded and disable unsuitable per-request JIT."""
    from functools import wraps
    from django.http import HttpResponse
    from django.template.loader import get_template

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        from .access import audit, is_analyst

        started = perf_counter()
        try:
            if request.user.is_superuser or is_analyst(request.user):
                audit(request.user, None, "operator.list_read", target=view.__name__)
            with overview_queries(query_timeout_ms=5000, budget_ms=12000, planning_limit=4):
                response = view(request, *args, **kwargs)
        except OperationalError as exc:
            sqlstate = getattr(exc.__cause__, "sqlstate", None)
            reason = (
                "request_budget"
                if isinstance(exc, OverviewBudgetExceeded)
                else "query_cancelled"
                if sqlstate == "57014"
                else "database"
            )
            logger.warning(
                "Bounded view unavailable view=%s reason=%s elapsed_ms=%d",
                view.__name__,
                reason,
                (perf_counter() - started) * 1000,
            )
            # Render without request context processors, also when the DB is unavailable.
            response = HttpResponse(get_template("portal/query_unavailable.html").render({}), status=503)
            response["Retry-After"] = "5"
        response["Cache-Control"] = "private, no-store, max-age=0"
        return response

    return wrapped


READ_SNAPSHOT = ContextVar("bearings_read_snapshot", default=False)


@contextmanager
def read_snapshot():
    """Coherent cache/live partition for one bounded read, never a session-level setting."""
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        yield
        return
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        token = READ_SNAPSHOT.set(True)
        try:
            yield
        finally:
            READ_SNAPSHOT.reset(token)
