from django.core.management.base import BaseCommand, CommandError
from portal.netbox_export import process_pending


class Command(BaseCommand):
    help = "Export a bounded batch of explicitly enabled managed client inventories to their own NetBox"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 25:
            raise CommandError("Use limit 1–25")
        self.stdout.write(f"Processed {process_pending(options['limit'])} NetBox inventory exports")
