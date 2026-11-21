from django.core.management.base import BaseCommand, CommandError
from portal.distro_cves import run


class Command(BaseCommand):
    help = "Refresh at most one public vendor cache and evaluate bounded local Linux inventories"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Use limit 1–100")
        self.stdout.write(
            f"Evaluated {run(options['limit'])} Linux inventories against vendor advisories; inspect coverage/freshness."
        )
