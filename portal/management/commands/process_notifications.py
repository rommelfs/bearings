from django.core.management.base import BaseCommand, CommandError
from portal.notifications import process_queued_notifications


class Command(BaseCommand):
    help = "Process already-approved queued messages once; never approve or retry uncertain attempts"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Use a worker limit of 1–100 messages per invocation")
        count = process_queued_notifications(options["limit"])
        self.stdout.write(
            f"Processed {count} previously approved queued messages; inspect recorded outcomes."
        )
