import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from portal.access import ANALYST_GROUP
from portal.models import (
    Asset,
    Contact,
    InfrastructureClaim,
    Installation,
    InventorySource,
    InventoryWrite,
    Membership,
    Organization,
    Product,
)
from portal.services import persist_lookup, process_write


class Command(BaseCommand):
    help = "Idempotently seed SYNTHETIC development data. Prompts for a password; no default credentials."

    def add_arguments(self, parser):
        parser.add_argument("--no-users", action="store_true", help="Seed data only (noninteractive checks)")

    @transaction.atomic
    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name=ANALYST_GROUP)
        user = None
        if not options["no_users"]:
            password = getpass.getpass("Password for new demo users (existing passwords unchanged): ")
            if len(password) < 12:
                raise CommandError("Use at least 12 characters")
            for name in ["company-admin", "circl-analyst"]:
                account, created = get_user_model().objects.get_or_create(
                    username=name, defaults={"email": f"{name}@example.invalid"}
                )
                if created:
                    account.set_password(password)
                    account.save()
                if name == "circl-analyst":
                    account.groups.add(group)
                else:
                    user = account
        org, _ = Organization.objects.get_or_create(
            slug="example-labs", defaults={"name": "Example Labs (SYNTHETIC)", "operator_visibility": True}
        )
        if user:
            Membership.objects.get_or_create(organization=org, user=user, defaults={"role": "admin"})
        source, _ = InventorySource.objects.get_or_create(organization=org, defaults={"mode": "development"})
        if source.mode != "development":
            raise CommandError("Demo seed refuses to write against a central NetBox source")
        contact, _ = Contact.objects.get_or_create(
            organization=org,
            email="security@example.invalid",
            defaults={
                "name": "Synthetic security team",
                "availability": "Weekdays 09:00–17:00 Europe/Luxembourg",
            },
        )
        InfrastructureClaim.objects.get_or_create(
            organization=org,
            kind="domain",
            value="example.invalid",
            defaults={
                "status": "verified",
                "method": "SYNTHETIC fixture verification, no real authority asserted",
                "reviewed_at": timezone.now(),
            },
        )
        asset, _ = Asset.objects.get_or_create(
            organization=org,
            source=source,
            name="demo-web-01",
            defaults={"kind": "server", "criticality": "high"},
        )
        job, _ = InventoryWrite.objects.get_or_create(asset=asset)
        process_write(job.pk)
        product, _ = Product.objects.get_or_create(
            organization=org,
            name="Apache Log4j",
            identifier="pkg:maven/org.apache.logging.log4j/log4j-core",
        )
        installation, _ = Installation.objects.get_or_create(
            asset=asset, product=product, defaults={"version": "2.14.1"}
        )
        persist_lookup(
            user,
            installation,
            "fixture://vulnerability-lookup/SYNTHETIC",
            "CVE-2021-44228",
            {
                "cveMetadata": {"cveId": "CVE-2021-44228"},
                "fixture": True,
                "note": "Synthetic minimal record; not a live API response",
            },
        )
        self.stdout.write(
            "Synthetic example-labs seeded. Development source only; no live integrations or scans."
        )
