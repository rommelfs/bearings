"""Operator-only CLI: query configured bindings without writing to any NetBox."""

import uuid
from django.core.management.base import BaseCommand, CommandError
from portal.connectors.http import ConnectorError
from portal.connectors.netbox import OBJECT_TYPES
from portal.models import InventorySource
from portal.services import query_inventory


class Command(BaseCommand):
    help = (
        "Query live NetBox bindings (GET only); report counts/health without changing inventory projections"
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true", help="Query every configured live source")
        group.add_argument(
            "--source", type=uuid.UUID, action="append", help="Source binding UUID; repeat to select several"
        )
        parser.add_argument(
            "--object-type",
            choices=OBJECT_TYPES,
            action="append",
            help="Repeat for several types; default devices",
        )

    def handle(self, *args, **options):
        sources = InventorySource.objects.exclude(mode="development").select_related("instance")
        if options["source"]:
            sources = sources.filter(pk__in=options["source"])
            if sources.count() != len(set(options["source"])):
                raise CommandError("A selected source is missing or is not a live NetBox binding")
        types = list(dict.fromkeys(options["object_type"] or ["devices"]))
        failed, attempted = 0, 0
        for source in sources.order_by("pk"):
            attempted += 1
            try:
                results = query_inventory(source, types)
            except ConnectorError:
                failed += 1
                self.stderr.write(f"Source {source.pk}: query failed; inspect read health in the workspace")
                continue
            counts = ", ".join(f"{key}={len(rows)}" for key, rows in results.items())
            self.stdout.write(f"Source {source.pk}: {counts}; no external writes or local inventory imports")
        if failed:
            raise CommandError(
                f"{failed} of {attempted} sources failed; remaining sources were still queried"
            )
        self.stdout.write(f"Queried {attempted} sources (GET only).")
