from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from portal.demo_showcase import seed


class Command(BaseCommand):
    help = "Create extensive tracked SYNTHETIC exploration data without network access, messages or passwords"

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")
        parser.add_argument("--companies", type=int, default=10)
        parser.add_argument("--assets-per-company", type=int, default=30)
        parser.add_argument(
            "--restore", action="store_true", help="Explicitly recreate a previously removed showcase"
        )

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not actor:
            raise CommandError("An existing active platform superuser is required; no account is provisioned")
        try:
            dataset, created = seed(
                actor,
                companies=options["companies"],
                assets_per_company=options["assets_per_company"],
                restore=options["restore"],
            )
        except (PermissionDenied, ValidationError, IntegrityError) as exc:
            raise CommandError(
                "; ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "Synthetic seed refused conflicting names or permissions; all changes rolled back"
            ) from None
        self.stdout.write(
            f"SYNTHETIC showcase {dataset.key}: {dataset.state}; "
            + ("created" if created else "retained without overwriting decisions")
            + f"; {dataset.entries.count()} tracked objects. No remote writes, scans or messages."
        )
