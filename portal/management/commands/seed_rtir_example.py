from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Exercise and retain one synthetic native RTIR Incident and three asset Investigations across two companies (bundled lab only)"

    def add_arguments(self, parser):
        parser.add_argument("--bundled", action="store_true", required=True)

    def handle(self, *args, **options):
        from docker.dev.rtir_smoke import main

        try:
            main()
        except (RuntimeError, AssertionError) as exc:
            raise CommandError(str(exc)) from None
