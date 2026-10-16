"""Operator runner for complete GET-only inventory imports."""

import uuid
from django.core.management.base import BaseCommand, CommandError
from portal.connectors.http import ConnectorError
from portal.inventory import due_sources, refresh_inventory
from portal.models import InventorySource


class Command(BaseCommand):
    help = "Import all four NetBox inventory types atomically per source (GET only; no deletion)"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true")
        group.add_argument("--source", type=uuid.UUID, action="append")
        parser.add_argument(
            "--due", action="store_true", help="Only queued/enabled sources whose interval is due"
        )

    def handle(self, *args, **options):
        sources = InventorySource.objects.filter(mode__in=["central", "external"])
        if options["source"]:
            sources = sources.filter(pk__in=options["source"])
            if sources.count() != len(set(options["source"])):
                raise CommandError("A selected source is missing or is not a live NetBox binding")
        if options["due"]:
            sources = sources.filter(pk__in=due_sources().values("pk"))
        failed = imported = 0
        for pk in sources.order_by("pk").values_list("pk", flat=True):
            try:
                result = refresh_inventory(pk, due=options["due"])
            except ConnectorError:
                failed += 1
                self.stderr.write(f"Source {pk}: import failed; projections retained, inspect import health")
                continue
            if result is not None:
                imported += 1
                self.stdout.write(f"Source {pk}: " + ", ".join(f"{k}={v}" for k, v in result.items()))
        if failed:
            raise CommandError(f"{failed} sources failed; remaining sources were still processed")
        if imported:
            self.stdout.write(f"Imported {imported} sources (GET only; no deletions).")
