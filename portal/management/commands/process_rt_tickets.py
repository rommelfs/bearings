import uuid
from datetime import timedelta
from pathlib import Path
import os
from django.core.management.base import BaseCommand
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils import timezone
from portal import rt
from portal.connectors.http import ConnectorError
from portal.models import RTTicket


class Command(BaseCommand):
    help = "Process approved RT ticket hand-offs and read-only reconciliation/status feedback"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true")
        group.add_argument("--ticket", type=uuid.UUID)
        parser.add_argument("--due", action="store_true")

    def handle(self, *args, **options):
        qs = RTTicket.objects.filter(instance__enabled=True).exclude(state__in=["draft", "blocked"])
        if options["ticket"]:
            qs = qs.filter(pk=options["ticket"])
        if options["due"]:
            now = timezone.now()
            qs = qs.filter(
                Q(state="queued")
                | Q(state="linked", last_attempt__lt=now - timedelta(minutes=10))
                | Q(state="linked", last_attempt__isnull=True)
                | Q(state__in=["uncertain", "creating"], last_attempt__lt=now - timedelta(minutes=2))
            )
        for pk in list(qs.order_by("last_attempt", "created_at").values_list("pk", flat=True)[:10]):
            try:
                row = rt.load(pk)
                if row.state == "queued":
                    rt.process(pk)
                elif row.state == "linked":
                    rt.refresh(pk)
                else:
                    rt.reconcile(pk)
            except (ConnectorError, PermissionDenied, ValidationError):
                RTTicket.objects.filter(pk=pk).update(
                    error="RT access, verification or transport failed; last-known state retained.",
                    last_attempt=timezone.now(),
                )
            if os.getenv("BEARINGS_DEV_STACK") == "1":
                Path("/tmp/bearings-worker-heartbeat").touch()
