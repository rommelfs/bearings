from pathlib import Path
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand, CommandError
from portal.connectors.http import ConnectorError
from portal.misp import sync_source
from portal.models import MISPInstance


class Command(BaseCommand):
    help = "Refresh restricted local MISP cache using bounded complete read-only searches; no push or publication"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true")
        group.add_argument("--source", type=int, action="append")
        parser.add_argument("--due", action="store_true")
        parser.add_argument("--limit", type=int, default=1)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 10:
            raise CommandError("Use a source limit of 1–10")
        sources = MISPInstance.objects.order_by("last_attempt", "pk")
        if options["source"]:
            sources = sources.filter(pk__in=options["source"])
            if sources.count() != len(set(options["source"])):
                raise CommandError("A selected MISP source is missing")
        if options["due"]:
            sources = sources.filter(enabled=True)
        failed, attempted = 0, 0
        for source in sources.iterator():
            now = timezone.now()
            if source.syncing_until and source.syncing_until > now:
                continue
            if (
                options["due"]
                and not source.syncing_until
                and source.last_attempt
                and source.last_attempt
                > now
                - timedelta(
                    minutes=min(source.refresh_minutes, 5) if source.error else source.refresh_minutes
                )
            ):
                continue
            if attempted >= options["limit"]:
                break
            attempted += 1
            try:
                count = sync_source(source.pk, due=options["due"])
            except ConnectorError:
                failed += 1
                self.stderr.write(f"MISP source {source.pk}: refresh failed; cache access suspended")
                continue
            finally:
                if Path("/tmp/bearings-worker-heartbeat").exists():
                    Path("/tmp/bearings-worker-heartbeat").touch()
            if count is not None:
                self.stdout.write(f"MISP source {source.pk}: {count} cached events; no upstream mutation")
        if failed:
            raise CommandError("MISP refresh failed; source health recorded without upstream response bodies")
