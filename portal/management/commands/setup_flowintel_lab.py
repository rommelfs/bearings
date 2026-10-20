import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from portal.models import FlowIntelInstance


class Command(BaseCommand):
    help = "Bind only the explicitly enabled bundled FlowIntel lab; preserve existing operator policies"

    def handle(self, *args, **options):
        root = Path("/run/bearings/secrets")
        if (
            not settings.DEBUG
            or os.getenv("BEARINGS_DEV_STACK") != "1"
            or os.getenv("BEARINGS_FLOWINTEL") != "1"
            or json.loads((root / "connections.json").read_text()).get("mode") != "bundled"
        ):
            raise CommandError("FlowIntel initialization requires the optional bundled development profile")
        data = json.loads((root / "flowintel.json").read_text())
        if data.get("base_url") != "https://flowintel.bearings.test":
            raise CommandError("Unexpected FlowIntel lab endpoint; no credentials or identities changed")
        instance, created = FlowIntelInstance.objects.get_or_create(
            name="bundled-flowintel",
            defaults={**data, "token_env_var": "FLOWINTEL_BUNDLED_TOKEN", "allow_private": True},
        )
        if not created and any(
            getattr(instance, field) != data[field] for field in ["base_url", "service_org_id"]
        ):
            raise CommandError("FlowIntel source identity differs; existing binding preserved")
        if instance.token_env_var != "FLOWINTEL_BUNDLED_TOKEN":
            raise CommandError("FlowIntel credential reference changed; preserved")
        instance.full_clean()
        self.stdout.write(
            "Bundled FlowIntel connection prepared. Existing enabled/disabled policy preserved; no cases exported."
        )
