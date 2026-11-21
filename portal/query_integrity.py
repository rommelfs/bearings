"""Explicit same-company integrity predicates without independent-column selectivity guesses."""

from django.db.models import BooleanField, Case, Q, Value, When


def consistent(*conditions, **lookups):
    """Keep all checks in SQL while treating their correlated truth as one predicate.

    Company IDs along ownership paths are highly correlated, not independent
    random columns. Exposing each equality as a separate restriction can make
    PostgreSQL estimate a million valid rows as one and select huge nested loops.
    CASE preserves NULL rejection and the full predicate, without that estimate.
    """
    return Case(
        When(Q(*conditions, **lookups), then=Value(True)), default=Value(False), output_field=BooleanField()
    )
