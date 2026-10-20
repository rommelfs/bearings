import os
import uuid
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q
from django.utils import timezone
from portal import flowintel
from portal.connectors.http import ConnectorError
from portal.models import FlowIntelCase


class Command(BaseCommand):
    help = "Process one bounded FlowIntel write step per case; reconcile/read status without retrying uncertain POSTs"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--all", action="store_true")
        group.add_argument("--case", type=uuid.UUID)
        parser.add_argument("--due", action="store_true")

    def handle(self, *args, **options):
        cases = FlowIntelCase.objects.exclude(state="draft").filter(instance__enabled=True)
        if os.getenv("BEARINGS_DEV_STACK") == "1" and os.getenv("BEARINGS_FLOWINTEL") != "1":
            cases = cases.exclude(instance__name="bundled-flowintel")
        if options["case"]:
            cases = cases.filter(pk=options["case"])
        if options["due"]:
            now = timezone.now()
            cases = cases.filter(
                Q(state__in=["queued", "building"])
                | Q(state="linked", last_attempt__lt=now - timedelta(minutes=10))
                | Q(state="linked", last_attempt__isnull=True)
                | Q(
                    state__in=["uncertain", "creating", "working"],
                    last_attempt__lt=now - timedelta(minutes=2),
                )
            )
        for pk in list(cases.order_by("last_attempt", "created_at").values_list("pk", flat=True)[:10]):
            try:
                case = flowintel.load(pk)
                if case.state in {"queued", "building"}:
                    flowintel.process(pk)
                    case.refresh_from_db()
                    if case.state == "linked":
                        flowintel.refresh(pk)
                elif case.state == "linked":
                    flowintel.refresh(pk)
                elif case.state in {"uncertain", "creating", "working"}:
                    if case.state == "uncertain":
                        FlowIntelCase.objects.filter(pk=pk).update(last_attempt=timezone.now())
                    flowintel.reconcile(pk)
            except (ConnectorError, ValidationError, PermissionDenied):
                FlowIntelCase.objects.filter(pk=pk).update(
                    error="FlowIntel permission, verification or transport failed; last-known state retained.",
                    last_attempt=timezone.now(),
                )
            if os.getenv("BEARINGS_DEV_STACK") == "1":
                Path("/tmp/bearings-worker-heartbeat").touch()
