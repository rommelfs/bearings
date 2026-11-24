import json
import os
import sys
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from portal.company_sso import plan, finalize


class Command(BaseCommand):
    help = "Guarded bundled-lab constituent SSO planning/finalization; never prints passwords or API tokens"

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")
        parser.add_argument("--username", required=True)
        parser.add_argument("--without-netbox", action="store_true")
        parser.add_argument("--finalize", action="store_true")

    def handle(self, *args, **options):
        if (
            not settings.DEBUG
            or not settings.SSO_ENABLED
            or os.getenv("BEARINGS_DEV_STACK") != "1"
            or os.getenv("BEARINGS_SSO_LAB") != "1"
        ):
            raise CommandError("This provisioner requires the explicit bundled SSO development lab")
        try:
            actor = get_user_model().objects.get(username=options["actor"], is_active=True, is_superuser=True)
            result = (
                finalize(actor, **json.load(sys.stdin))
                if options["finalize"]
                else plan(actor, options["username"], not options["without_netbox"])
            )
        except (ValidationError, PermissionDenied, ObjectDoesNotExist) as error:
            raise CommandError(
                "; ".join(error.messages)
                if isinstance(error, ValidationError)
                else "Company access plan denied"
            ) from None
        self.stdout.write(json.dumps(result))
