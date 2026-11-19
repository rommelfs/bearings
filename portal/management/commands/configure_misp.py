"""Local operator configuration channel. JSON stdin contains metadata, never an API-key value."""

import json
import sys
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from portal.access import audit
from portal.models import MISPInstance


class Command(BaseCommand):
    help = "Configure/disable a MISP cache source from operator JSON stdin; no upstream request"

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options["actor"], is_active=True, is_superuser=True)
            values = json.load(sys.stdin)
            with transaction.atomic():
                source = MISPInstance.objects.select_for_update().filter(name=values["name"]).first()
                if source is None:
                    source = MISPInstance(name=values["name"])
                source.base_url, source.token_env_var = values["base_url"], values["token_env_var"]
                source.owner = get_user_model().objects.get(username=values["owner"], is_active=True)
                source.misp_user_id = int(values["misp_user_id"])
                source.allow_private = values.get("allow_private", False)
                source.enabled, source.last_success, source.last_attempt = False, None, None
                source.generation, source.syncing_until = uuid.uuid4(), None
                source.full_clean()
                source.error = "Awaiting an operator-enabled complete refresh after credential configuration"
                source.save()
                source.events.update(review_digest="")
                audit(actor, None, "misp.credentials_configured", source.pk)
            self.stdout.write(json.dumps({"source": source.pk}))
        except (get_user_model().DoesNotExist, KeyError, ValueError, TypeError, ValidationError):
            raise CommandError(
                "MISP configuration refused; check active platform actor, HTTPS source and credential reference"
            ) from None
