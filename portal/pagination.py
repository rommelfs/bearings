"""Sort and page narrow primary keys before hydrating inventory/evidence payloads."""

from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery


def object_page(queryset, size, number, *, count=None, key_source=None):
    if key_source is None:
        keys = queryset.select_related(None).values_list("pk", flat=True)
    else:
        # A correlated, one-row eligibility probe lets PostgreSQL walk the local
        # ordering index instead of sorting hydrated multi-table results.
        eligible = queryset.order_by().filter(pk=OuterRef("pk")).values("pk")[:1]
        keys = key_source.filter(pk=Subquery(eligible)).values_list("pk", flat=True)
    paginator = Paginator(keys, size)
    if count is not None:
        paginator.count = count
    page = paginator.get_page(number)
    ids = list(page.object_list)
    # Reapply the original scope/filters when fetching records; never broaden by IDs alone.
    objects = {obj.pk: obj for obj in queryset.filter(pk__in=ids)}
    page.object_list = [objects[pk] for pk in ids if pk in objects]
    return page
