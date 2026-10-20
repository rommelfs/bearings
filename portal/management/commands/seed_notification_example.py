"""Explicit synthetic contact readiness and CVE reviews; no real email verification or delivery."""

import os
from datetime import timedelta
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from django.utils import timezone
from portal.models import Contact, Installation, Organization
from portal.services import persist_lookup


class Command(BaseCommand):
    help = "Prepare synthetic notification examples, preserving contact policy and analyst decisions"

    def add_arguments(self, parser):
        parser.add_argument("--bundled", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Notification fixtures require local DEBUG mode")
        if options["bundled"]:
            if os.getenv("BEARINGS_DEV_STACK") != "1":
                raise CommandError("Bundled examples require the isolated development stack")
            import json
            from pathlib import Path
            from docker.dev.smoke import lab_sources

            config = json.loads(Path("/run/bearings/secrets/connections.json").read_text())
            if config.get("mode") != "bundled":
                raise CommandError("Notification examples refuse external inventory")
            sources = lab_sources(config)
            orgs = [source.organization for source in sources.values()]
        else:
            call_command("seed_demo", no_users=True)
            orgs = [Organization.objects.get(slug="example-labs")]
        for org in orgs:
            Contact.objects.get_or_create(
                organization=org,
                email="notifications-" + org.slug + "@example.invalid",
                defaults={
                    "name": "SYNTHETIC security notification team",
                    "role": "Synthetic security team",
                    "scope": "SYNTHETIC lab only; reachability and role review are simulated",
                    "notification_enabled": True,
                    "reachable_at": timezone.now(),
                    "reviewed_at": timezone.now(),
                    "next_review": timezone.localdate() + timedelta(days=180),
                },
            )
            installs = Installation.objects.filter(
                asset__organization=org, product__identifier="pkg:maven/org.apache.logging.log4j/log4j-core"
            )
            for installation in installs:
                persist_lookup(
                    None,
                    installation,
                    "fixture://notification-example/SYNTHETIC",
                    "CVE-2021-44228",
                    {
                        "fixture": True,
                        "note": "Synthetic minimal example, not a fetched Vulnerability-Lookup response",
                        "cveMetadata": {"cveId": "CVE-2021-44228"},
                        "containers": {
                            "cna": {
                                "title": "SYNTHETIC review fixture: Apache Log4j remote code execution",
                                "metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 10.0}}],
                            }
                        },
                    },
                )
        self.stdout.write(
            "Synthetic Critical Log4j reviews and simulated eligible contacts prepared. Use Notifications, severity Critical. Existing policies/decisions preserved; no messages created or sent."
        )
