import os
import uuid
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from portal.models import Organization
from portal.federation import create_grant


class Command(BaseCommand):
    help = "Create explicit company export grant; write bearer credential to a new private file"

    def add_arguments(self, parser):
        for name in ["actor", "organization", "client", "output"]:
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--inventory", action="store_true")
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        path = Path(options["output"])
        try:
            actor = get_user_model().objects.get(username=options["actor"], is_active=True)
            org = Organization.objects.get(slug=options["organization"])
            client = uuid.UUID(options["client"])
            with transaction.atomic():
                row, token = create_grant(actor, org, client, options["inventory"], options["days"])
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write(token + "\n")
        except (
            ValueError,
            ValidationError,
            PermissionDenied,
            OSError,
            Organization.DoesNotExist,
            get_user_model().DoesNotExist,
        ):
            raise CommandError(
                "Grant not created; check actor, organization, client UUID and new private output path"
            ) from None
        self.stdout.write(
            f"Grant/export identity {row.pk}; credential written to private file. No secret printed."
        )
