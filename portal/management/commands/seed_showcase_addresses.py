import os
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from portal.demo_addresses import fill_showcase_addresses


class Command(BaseCommand):
    help = (
        "Add fictional Luxembourg addresses once to existing provenance-owned development showcase companies"
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")
        parser.add_argument(
            "--automatic", action="store_true", help="Respect the bundled BEARINGS_SHOWCASE switch"
        )

    def handle(self, *args, **options):
        if options["automatic"] and os.getenv("BEARINGS_SHOWCASE", "1") != "1":
            self.stdout.write("Automatic showcase address completion disabled.")
            return
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not actor:
            raise CommandError("Existing active platform superuser required")
        try:
            count = fill_showcase_addresses(actor)
        except (PermissionDenied, ValidationError):
            raise CommandError(
                "Synthetic address extension refused; only DEBUG showcase data is eligible"
            ) from None
        self.stdout.write(
            f"Added {count} SYNTHETIC addresses; real/edited addresses, decisions and removed datasets preserved. No network or mail."
        )
