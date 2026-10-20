from django.core.management.base import BaseCommand, CommandError
from portal.models import CompanyInstance
from portal.federation import pull
from portal.connectors.http import ConnectorError


class Command(BaseCommand):
    help = "Read one bounded, explicitly granted company snapshot; no remote writes"

    def add_arguments(self, parser):
        parser.add_argument("--instance", required=True)

    def handle(self, *args, **options):
        try:
            source = CompanyInstance.objects.get(name=options["instance"])
            count = pull(source.pk)
        except (CompanyInstance.DoesNotExist, ConnectorError):
            raise CommandError(
                "Company read failed; check source health. Last-known records retained."
            ) from None
        self.stdout.write(f"Read {count} company-reported records; authoritative local inventory unchanged.")
