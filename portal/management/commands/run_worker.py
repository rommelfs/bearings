"""Independent non-lab scheduling; no setup/seed/provisioning command is invoked."""

import signal
from threading import Event
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections

JOBS = [
    ("process_jobs", {"limit": 5}),
    ("process_agent_reports", {"limit": 25}),
    ("process_netbox_exports", {"limit": 2}),
    ("sync_distro_cves", {"limit": 5}),
    ("remind_inventory", {"limit": 5}),
    ("process_flowintel", {"all": True, "due": True}),
    ("process_rt_tickets", {"all": True, "due": True}),
    ("prepare_notifications", {"due": True}),
    ("prepare_followups", {"limit": 25}),
    ("process_notifications", {"limit": 5}),
    ("sync_netbox", {"all": True, "due": True}),
    ("sync_mosp", {"all": True, "due": True}),
    ("sync_vulnerabilities", {"due": True, "limit": 2}),
    ("sync_misp", {"all": True, "due": True, "limit": 1}),
]


class Command(BaseCommand):
    help = "Run configured inventory/intelligence work independently of web and national refresh; no lab provisioning"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        stopped = Event()
        previous = {}
        if not options["once"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *_: stopped.set())
        try:
            while not stopped.is_set():
                for name, parameters in JOBS:
                    if stopped.is_set():
                        break
                    try:
                        call_command(name, stdout=self.stdout, stderr=self.stderr, **parameters)
                    except Exception as exc:
                        self.stderr.write(
                            f"{name} deferred ({type(exc).__name__}); retained work needs review"
                        )
                        connections.close_all()
                if options["once"]:
                    return
                stopped.wait(5)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
