"""Entry point guarded against use with operational or development databases."""

from django.core.management.base import BaseCommand
from portal.scale_benchmark import run


class Command(BaseCommand):
    help = "Seed/measure a dedicated PostgreSQL synthetic scale database (use scripts/scale_test.py)"

    def add_arguments(self, parser):
        parser.add_argument("phase", choices=["seed", "measure", "workflows"])
        parser.add_argument("--companies", type=int, default=40000)
        parser.add_argument("--assets-per-company", type=int, default=30)
        parser.add_argument("--label", default="baseline")
        parser.add_argument("--samples", type=int, default=3)
        parser.add_argument("--concurrency", type=int, default=4)
        parser.add_argument("--http-profile", choices=["national", "company", "full"], default="national")
        parser.add_argument("--http-repeats", type=int, default=4)
        parser.add_argument(
            "--churn",
            action="store_true",
            help="Commit one synthetic software change repeatedly while reading and refreshing",
        )

    def handle(self, *args, **options):
        run(options)
