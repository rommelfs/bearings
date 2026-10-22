"""Explicit tracked synthetic multi-constituent exercise; no verification or delivery."""

from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from portal.demo_data import KEY, capture
from portal.models import Asset, Contact, DemoDataset, DemoObject, Installation, Organization, Product
from portal.services import persist_lookup


class Command(BaseCommand):
    help = (
        "Prepare tracked campaign examples for three fictional constituents, with simulated contacts for two"
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", default="platform-admin")

    @transaction.atomic
    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not settings.DEBUG or not actor:
            raise CommandError("Requires DEBUG and an existing active platform superuser")
        dataset = DemoDataset.objects.select_for_update().filter(key=KEY, state="active").first()
        if not dataset:
            raise CommandError(
                "An active tracked showcase is required; removed datasets are never recreated here"
            )
        ids = list(
            DemoObject.objects.filter(dataset=dataset, model_label="portal.organization").values_list(
                "object_pk", flat=True
            )
        )
        orgs = list(Organization.objects.filter(pk__in=ids, operator_visibility=True).order_by("name")[:3])
        if len(orgs) != 3:
            raise CommandError(
                "Requires three currently visible tracked fictional companies; no policy is changed"
            )

        def ensure_owned(row):
            if not DemoObject.objects.filter(
                dataset=dataset, model_label=row._meta.label_lower, object_pk=str(row.pk)
            ).exists():
                raise CommandError(
                    "A conflicting untracked record was preserved; example creation rolled back"
                )

        with capture(dataset):
            for index, org in enumerate(orgs):
                asset_ids = list(
                    DemoObject.objects.filter(dataset=dataset, model_label="portal.asset").values_list(
                        "object_pk", flat=True
                    )
                )
                asset = Asset.objects.filter(organization=org, pk__in=asset_ids).order_by("name").first()
                if asset is None:
                    raise CommandError("No tracked fictional asset found; no real inventory is adopted")
                product, _ = Product.objects.get_or_create(
                    organization=org, name="SYNTHETIC CIRCL Campaign Example"
                )
                ensure_owned(product)
                installation, _ = Installation.objects.get_or_create(
                    asset=asset, product=product, defaults={"version": "DEMO-1"}
                )
                ensure_owned(installation)
                finding = persist_lookup(
                    actor,
                    installation,
                    "fixture://circl-campaign/SYNTHETIC",
                    "CVE-2021-44228",
                    {
                        "cveMetadata": {"cveId": "CVE-2021-44228"},
                        "containers": {
                            "cna": {
                                "title": "SYNTHETIC campaign exercise; no real applicability assertion",
                                "metrics": [{"cvssV3_1": {"version": "3.1", "baseScore": 8.1}}],
                            }
                        },
                    },
                )
                ensure_owned(finding)
                if index < 2:
                    contact, _ = Contact.objects.get_or_create(
                        organization=org,
                        email=f"campaign-{org.slug}@example.invalid",
                        defaults={
                            "name": "SYNTHETIC campaign contact",
                            "role": "Synthetic security team",
                            "scope": "SYNTHETIC ONLY: simulated reachability, inclusion and review; not real verification",
                            "notification_enabled": True,
                            "reachable_at": timezone.now(),
                            "reviewed_at": timezone.now(),
                            "next_review": timezone.localdate() + timedelta(days=180),
                        },
                    )
                    ensure_owned(contact)
        self.stdout.write(
            "Tracked SYNTHETIC CIRCL campaign example retained/created for three companies. New simulated contacts for two; existing opt-outs and assessments preserved. Filter product: SYNTHETIC CIRCL Campaign Example, severity High. No messages or remote requests."
        )
