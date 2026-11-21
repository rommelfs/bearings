from django.core.management.base import BaseCommand, CommandError
from portal.agents import process_pending


class Command(BaseCommand):
    help = "Project a bounded batch of authenticated Linux observations; never contacts a device or resolves findings"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Use limit 1–100")
        self.stdout.write(f"Processed {process_pending(options['limit'])} agent reports")
