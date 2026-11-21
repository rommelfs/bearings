"""Bounded worker for per-company derived national data; no upstream calls."""

import time
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from portal.national_snapshots import refresh_pending


class Command(BaseCommand):
    help = "Refresh dirty national summaries; --watch provides a dedicated incremental worker"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100000 or not 1 <= options["batch_size"] <= 1000:
            raise CommandError("Use limit 1–100000 and batch-size 1–1000")
        while True:
            total = refresh_pending(limit=options["limit"], batch_size=options["batch_size"])
            if total >= 5000:
                from portal.national_snapshots import DERIVED_MODELS
                from django.apps import apps

                with connection.cursor() as cursor:
                    for name in sorted(DERIVED_MODELS):
                        cursor.execute(
                            "ANALYZE "
                            + connection.ops.quote_name(apps.get_model("portal", name)._meta.db_table)
                        )
            self.stdout.write(f"Refreshed {total} company summaries; raw inventory remains authoritative.")
            if not options["watch"]:
                return
            time.sleep(1 if total else 2)
