from django.core.management.base import BaseCommand
from django.utils import timezone
from portal.models import InventoryWrite
from portal.services import process_write


class Command(BaseCommand):
    help = "Process due durable inventory writes once; run periodically (single worker with SQLite)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retry-now", action="store_true", help="Operator-requested retry of unconfirmed writes"
        )

    def handle(self, *args, **options):
        jobs = InventoryWrite.objects.filter(completed_at__isnull=True)
        if not options["retry_now"]:
            jobs = jobs.filter(next_attempt__lte=timezone.now())
        for pk in list(jobs.values_list("pk", flat=True)[:100]):
            process_write(pk, force=options["retry_now"])
        self.stdout.write("Due inventory jobs processed; inspect source health and asset state for outcomes.")
