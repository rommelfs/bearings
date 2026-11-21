from django.core.management.base import BaseCommand, CommandError
from portal.models import NotificationDelivery
from portal.outreach import prepare_followups


class Command(BaseCommand):
    help = "Prepare one reminder and one management escalation draft per unacknowledged original message; never send"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("Use --limit between 1 and 1000")
        from django.db.models import Q
        from django.db.models import F

        qs = (
            NotificationDelivery.objects.filter(
                status__in=["filed", "accepted"], batch__followup__isnull=True
            )
            .filter(
                Q(organization__outreach_policy__reminder_days__gt=0)
                | Q(organization__outreach_policy__escalation_days__gt=0)
            )
            .filter(Q(acknowledged_at__isnull=True) | Q(followups__batch__status="draft"))
            .distinct()
            .order_by(F("followup_checked_at").asc(nulls_first=True), "pk")
        )
        count = 0
        for pk in list(qs.values_list("pk", flat=True)[: options["limit"]]):
            count += prepare_followups(pk)
        self.stdout.write(f"Prepared {count} follow-up drafts. No message approved or sent.")
