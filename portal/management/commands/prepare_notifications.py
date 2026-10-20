from django.core.management.base import BaseCommand
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.db.models import F, Q
from datetime import timedelta
import os
from pathlib import Path
from portal.models import NotificationSubscription
from portal.subscriptions import prepare


class Command(BaseCommand):
    help = "Prepare changed subscription drafts without approving or sending messages"

    def add_arguments(self, parser):
        parser.add_argument("--due", action="store_true")

    def handle(self, *args, **options):
        qs = NotificationSubscription.objects.filter(enabled=True)
        if options["due"]:
            qs = qs.filter(
                Q(last_checked__isnull=True) | Q(last_checked__lt=timezone.now() - timedelta(minutes=10))
            )
        for pk in list(
            qs.order_by(F("last_checked").asc(nulls_first=True), "created_at").values_list("pk", flat=True)[
                :20
            ]
        ):
            try:
                prepare(pk, due=options["due"])
            except (ValidationError, PermissionDenied):
                NotificationSubscription.objects.filter(pk=pk).update(
                    last_checked=timezone.now(),
                    error="Subscription access, evidence, transport or recipient readiness needs review. No message approved or sent.",
                )
            if os.getenv("BEARINGS_DEV_STACK") == "1":
                Path("/tmp/bearings-worker-heartbeat").touch()
