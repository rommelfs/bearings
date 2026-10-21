import json
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from portal import demo_data
from portal.models import DemoDataset


class Command(BaseCommand):
    help = "Inspect tracked demo provenance, preview/purge synthetic data, or check production readiness"

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=["status", "plan", "purge", "check"])
        parser.add_argument("--dataset", default=demo_data.KEY)
        parser.add_argument("--actor", default="platform-admin")
        parser.add_argument(
            "--apply", action="store_true", help="Apply removal; otherwise purge is a preview"
        )
        parser.add_argument("--fingerprint", help="Exact reviewed removal-plan fingerprint")

    def handle(self, *args, **options):
        dataset = DemoDataset.objects.filter(key=options["dataset"]).first()
        if options["operation"] == "check":
            legacy = demo_data.unmanaged_fixtures()
            active = DemoDataset.objects.filter(state="active").exists()
            self.stdout.write(
                json.dumps({"active_demo_datasets": active, "unmanaged_fixtures": legacy}, indent=2)
            )
            if active or any(legacy.values()):
                raise CommandError(
                    "Synthetic data remains. Review tracked cleanup and legacy/backend lab fixtures before production."
                )
            self.stdout.write(
                "No registered demo datasets or recognized legacy fixtures remain. This is a data check, not production deployment certification."
            )
            return
        if not dataset:
            self.stdout.write(
                "No tracked dataset. Recognized legacy fixtures: "
                + json.dumps(demo_data.unmanaged_fixtures())
            )
            return
        plan, _ = demo_data.removal_plan(dataset)
        if options["operation"] == "purge" and options["apply"]:
            if not options["fingerprint"]:
                raise CommandError("Run demo_data plan and supply its --fingerprint before --apply")
            actor = (
                get_user_model()
                .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
                .first()
            )
            if not actor:
                raise CommandError("An existing active platform superuser is required")
            try:
                demo_data.purge(actor, dataset.key, options["fingerprint"])
            except (ValidationError, PermissionDenied) as exc:
                raise CommandError(
                    "; ".join(exc.messages)
                    if isinstance(exc, ValidationError)
                    else "Platform administrator required"
                ) from None
            self.stdout.write(
                "Tracked demo data removed; audit and removal tombstone retained. Automatic reseeding stays off. Legacy/backend fixtures: "
                + json.dumps(demo_data.unmanaged_fixtures())
            )
        else:
            self.stdout.write(json.dumps(plan, indent=2))
