"""Freshness of inventory and of components present in the verified full report."""

from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone


def recent_device(prefix="", *, now=None):
    cutoff = (now or timezone.now()) - timedelta(hours=12)
    return Q(**{f"{prefix}inventory_verified_at__gte": cutoff}) | Q(
        **{f"{prefix}inventory_verified_at__isnull": True, f"{prefix}last_observed_at__gte": cutoff}
    )


def recent_component(prefix=""):
    cutoff = timezone.now() - timedelta(hours=12)
    return Q(**{f"{prefix}observed_at__gte": cutoff}) | Q(
        **{
            f"{prefix}last_report_id": F(f"{prefix}device__inventory_baseline_id"),
            f"{prefix}device__inventory_verified_at__gte": cutoff,
        }
    )


def inventory_applied(prefix=""):
    applied = F(f"{prefix}applied_sequence")
    return Q(**{f"{prefix}inventory_admitted_sequence": applied}) | Q(
        **{f"{prefix}inventory_admitted_sequence__isnull": True, f"{prefix}last_sequence": applied}
    )
