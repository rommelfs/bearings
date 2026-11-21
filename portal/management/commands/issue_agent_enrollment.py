"""Operator-side issuance for an approved rollout; secret stdout must never enter CI logs."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from portal import agents, agent_enrollment_codes
from portal.models import Organization, Asset


class Command(BaseCommand):
    help = (
        "Issue one expiring public-key-bound code as an authorized actor; protect stdout/no_log in automation"
    )

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument(
            "--public-key", required=True, help="Public Ed25519 key only; never a private key"
        )
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--asset")
        target.add_argument("--new-host-kind", choices=["vm", "server", "desktop", "laptop"])

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(slug=options["organization"], merged_into__isnull=True)
            actor = get_user_model().objects.get(username=options["actor"], is_active=True)
            asset = Asset.objects.get(pk=options["asset"], organization=org) if options["asset"] else None
            grant, token = agents.create_enrollment(
                actor, org, asset, options["public_key"], options["new_host_kind"] or ""
            )
            code = agent_enrollment_codes.encode(agent_enrollment_codes.payload(grant, token))
        except (
            Organization.DoesNotExist,
            get_user_model().DoesNotExist,
            Asset.DoesNotExist,
            ValidationError,
            PermissionDenied,
            ValueError,
        ) as exc:
            raise CommandError("Enrollment not authorized or invalid; no code issued") from exc
        self.stdout.write(code)
