from django.core.management.base import BaseCommand, CommandError
from portal.connectors.http import ConnectorError
from portal.intelligence import default_catalog, sync_catalog
from portal.models import MOSPSource


class Command(BaseCommand):
    help = "Refresh public CC0 MONARC risk catalog via MOSP GETs; retain previous data on failure"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true")
        group.add_argument("--source", type=int, action="append")
        parser.add_argument("--due", action="store_true")

    def handle(self, *args, **options):
        if not MOSPSource.objects.exists():
            default_catalog()
        sources = MOSPSource.objects.all()
        if options["source"]:
            sources = sources.filter(pk__in=options["source"])
            if sources.count() != len(set(options["source"])):
                raise CommandError("A selected MOSP source is missing")
        if options["due"]:
            sources = sources.filter(enabled=True)
        failed = 0
        for source in sources:
            try:
                count = sync_catalog(source.pk, due=options["due"])
            except ConnectorError:
                failed += 1
                self.stderr.write(f"MOSP source {source.pk}: refresh failed; retained catalog available")
                continue
            if count is not None:
                self.stdout.write(f"MOSP source {source.pk}: {count} public CC0 risk templates (GET only)")
        if failed:
            raise CommandError(f"{failed} catalog sources failed; remaining sources were processed")
