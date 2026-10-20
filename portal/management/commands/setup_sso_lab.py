import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from social_django.models import UserSocialAuth
from config.oidc import identity_uid


class Command(BaseCommand):
    help = "Bind explicitly enabled synthetic SSO subjects to existing lab accounts"

    def handle(self, *args, **options):
        if (
            not settings.DEBUG
            or os.getenv("BEARINGS_DEV_STACK") != "1"
            or os.getenv("BEARINGS_SSO_LAB") != "1"
        ):
            raise CommandError("SSO fixture setup requires the explicitly enabled isolated lab")
        manifest = json.loads(Path("/run/bearings/secrets/oidc-lab.json").read_text())
        if manifest["issuer"] != settings.SSO_ISSUER:
            raise CommandError("SSO lab issuer mismatch")
        for name in ["company-admin", "circl-analyst"]:
            if UserSocialAuth.objects.filter(
                provider="oidc", uid=identity_uid(settings.SSO_ISSUER, manifest["users"][name])
            ).exists():
                continue  # A disabled tombstone remains revoked across retained-volume restarts.
            call_command(
                "link_oidc_identity", actor="platform-admin", username=name, subject=manifest["users"][name]
            )
