from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from portal.connectors.http import ConnectorError
from portal.discovery import sync_watch
from portal.models import ProductWatch


class Command(BaseCommand):
    help = "Refresh explicit enabled product watches; retain last-known evidence on failures"

    def add_arguments(self, parser):
        parser.add_argument("--due", action="store_true")
        parser.add_argument("--watch", type=int)
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Use --limit between 1 and 100")
        if not options["watch"]:
            from portal.product_matching import enroll_products

            enroll_products()
        qs = ProductWatch.objects.filter(enabled=True)
        if options["watch"]:
            qs = qs.filter(pk=options["watch"])
        if options["due"]:
            from datetime import timedelta
            from django.db.models import Q, ExpressionWrapper, DurationField, IntegerField
            from django.db.models.functions import Cast
            from django.utils import timezone

            qs = qs.annotate(
                interval=ExpressionWrapper(
                    Cast("interval_minutes", IntegerField()) * timedelta(minutes=1),
                    output_field=DurationField(),
                )
            ).filter(
                Q(requested=True)
                | Q(last_attempt__isnull=True)
                | Q(last_attempt__lte=timezone.now() - F("interval"))
            )
        failed = False
        for pk in qs.order_by(F("last_attempt").asc(nulls_first=True), "pk").values_list("pk", flat=True)[
            : options["limit"]
        ]:
            try:
                sync_watch(pk, due=options["due"])
            except ConnectorError:
                failed = True
        if failed:
            raise CommandError(
                "A product watch failed; inspect discovery health. Last complete evidence retained."
            )
        self.stdout.write("Product watch refresh complete; no notification approved or sent.")
