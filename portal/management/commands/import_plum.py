import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError, PermissionDenied
from portal import plum
from portal.models import Organization, PlumInstance


class Command(BaseCommand):
    help = "Import an existing scoped Plum InfoIP JSON/full export (no scan submission)"

    def add_arguments(self, parser):
        parser.add_argument("--instance", required=True)
        parser.add_argument("--organization", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--file", required=True)

    def handle(self, *args, **options):
        path = Path(options["file"])
        try:
            with path.open("rb") as handle:
                raw = handle.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024:
                raise CommandError("32 MiB import limit; export bounded customer/time partitions")
            payload = json.loads(raw)
            actor = get_user_model().objects.get(username=options["actor"], is_active=True)
            source = PlumInstance.objects.get(name=options["instance"])
            org = Organization.objects.get(slug=options["organization"])
            rows = (
                plum.import_export(actor, org, source, payload)
                if isinstance(payload, dict) and "results" in payload
                else [plum.ingest(actor, org, source, payload)]
            )
        except (
            ValidationError,
            PermissionDenied,
            ValueError,
            OSError,
            Organization.DoesNotExist,
            PlumInstance.DoesNotExist,
            get_user_model().DoesNotExist,
        ) as exc:
            raise CommandError(
                "Scoped import failed; check JSON/schema, source permission and historical assignments. No scans submitted."
            ) from exc
        self.stdout.write(
            f"Imported/reused {len(rows)} scoped observation snapshots. Existing data retained; no scans submitted."
        )
