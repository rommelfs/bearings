"""Bind only the explicitly enabled synthetic RT reference queues."""

import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from portal.models import InventorySource, RTInstance


class Command(BaseCommand):
    help = "Prepare the bundled RT connections without resetting existing operator decisions"

    def handle(self, *args, **options):
        root = Path("/run/bearings/secrets")
        if (
            not settings.DEBUG
            or os.getenv("BEARINGS_DEV_STACK") != "1"
            or os.getenv("BEARINGS_RT") != "1"
            or json.loads((root / "connections.json").read_text()).get("mode") != "bundled"
        ):
            raise CommandError("RT initialization requires the explicitly enabled bundled lab")
        data = json.loads((root / "rt.json").read_text())
        if data["base_url"] != "https://rt.bearings.test":
            raise CommandError("Unrecognized RT endpoint")
        connections = json.loads((root / "connections.json").read_text())["connections"]
        rw = next(item for item in connections if item["access_mode"] == "read_write")
        company = InventorySource.objects.get(organization__slug=rw["organization_slug"]).organization
        for kind, organization in [("company", company), ("circl", None)]:
            defaults = {
                "base_url": data["base_url"],
                "browser_url": data["browser_url"],
                "queue_id": data["queues"][kind],
                "organization": organization,
                "token_env_var": "RT_BUNDLED_" + kind.upper() + "_TOKEN",
                "enabled": True,
                "allow_private": True,
                "private_queue_confirmed": True,
            }
            instance, created = RTInstance.objects.get_or_create(name="bundled-rt-" + kind, defaults=defaults)
            if not created and any(
                getattr(instance, field) != defaults[field]
                for field in ["base_url", "queue_id", "token_env_var", "organization"]
            ):
                raise CommandError("Retained RT binding differs; no source or policy was replaced")
            instance.full_clean()
        if os.getenv("BEARINGS_RTIR") == "1":
            rtir = json.loads((root / "rtir.json").read_text())
            defaults = {
                "base_url": data["base_url"],
                "browser_url": data["browser_url"],
                "queue_id": rtir["queues"]["investigation"],
                "incident_queue_id": rtir["queues"]["incident"],
                "organization": None,
                "product": "rtir",
                "token_env_var": "RT_BUNDLED_RTIR_TOKEN",
                "enabled": True,
                "allow_private": True,
                "private_queue_confirmed": True,
            }
            instance, created = RTInstance.objects.get_or_create(name="bundled-rtir-circl", defaults=defaults)
            if not created and any(
                getattr(instance, field) != defaults[field]
                for field in [
                    "base_url",
                    "queue_id",
                    "incident_queue_id",
                    "organization",
                    "product",
                    "token_env_var",
                ]
            ):
                raise CommandError("Retained RTIR identity differs; no source or policy replaced")
            instance.full_clean()
        self.stdout.write(
            "Bundled RT queues bound. Existing disabled/sharing policies preserved; no tickets exported."
        )
