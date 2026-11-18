import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from portal.demo_access import scope_company_admin


class Command(BaseCommand):
    help = "Restrict the existing bundled company-admin fixture to one existing company grant; no accounts or passwords changed"

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")
        parser.add_argument("--config", default="/run/bearings/secrets/connections.json")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_superuser=True, is_active=True)
            .first()
        )
        if not actor:
            raise CommandError("Existing active platform superuser required")
        try:
            config = json.loads(Path(options["config"]).read_text())
            count = scope_company_admin(actor, config)
        except (OSError, ValueError, KeyError, PermissionDenied, ValidationError) as error:
            raise CommandError(
                "; ".join(error.messages)
                if isinstance(error, ValidationError)
                else "Bundled profile validation failed; no grant changed"
            ) from None
        self.stdout.write(
            f"Single-company demo profile applied: {count} extra fixture grants removed; unrelated policies/passwords/SSO unchanged."
        )
