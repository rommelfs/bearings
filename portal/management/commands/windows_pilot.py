"""Export an authorized Windows 11 pilot observation without inventory names."""

import json
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from portal.overview_queries import read_snapshot
from portal.windows_pilot import inspect


class Command(BaseCommand):
    help = "Read one scoped Windows pilot observation; no scan, policy change or CVE verdict"

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--organization", required=True)
        parser.add_argument("--device", required=True, type=uuid.UUID)

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options["actor"], is_active=True)
            with read_snapshot():
                result = inspect(actor, options["organization"], options["device"])
        except (ObjectDoesNotExist, PermissionDenied, ValidationError, ValueError, TypeError, KeyError):
            raise CommandError("Pilot observation unavailable, inconsistent or outside actor scope") from None
        self.stdout.write(json.dumps(result, indent=2))
