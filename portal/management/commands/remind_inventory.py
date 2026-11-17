"""Queue and deliver due owner-review service messages, with current-policy checks."""

from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from portal.inventory_review import deliver_review_reminder, queue_review_reminders
from portal.models import InventoryReviewDelivery, InventoryReviewPolicy, PublicRegistrationBucket


class Command(BaseCommand):
    help = "Process periodic inventory-data reminders (local email sink by default; explicit service SMTP supported)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 100))
        now = timezone.now()
        policies = InventoryReviewPolicy.objects.filter(
            email_enabled=True, next_due__lte=timezone.localdate(), next_reminder_at__lte=now
        ).order_by("next_reminder_at", "pk")
        queued = sum(queue_review_reminders(pk) for pk in list(policies.values_list("pk", flat=True)[:limit]))
        deliveries = InventoryReviewDelivery.objects.filter(
            status__in=["pending", "error"], attempts__lt=3, next_attempt__lte=now
        ).order_by("next_attempt", "pk")
        for pk in list(deliveries.values_list("pk", flat=True)[:limit]):
            deliver_review_reminder(pk)
            Path("/tmp/bearings-worker-heartbeat").touch()
        PublicRegistrationBucket.objects.filter(expires_at__lt=now).delete()
        self.stdout.write(f"Queued {queued} review reminder messages; inspect delivery state for outcomes.")
