"""Production settings are opt-in, fail closed and keep lab provisioning out of workers."""

from io import StringIO
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.http import HttpResponse
from django.test import SimpleTestCase, RequestFactory
from .production_edge import ClientAddress
from .management.commands.run_worker import JOBS

ROOT = Path(__file__).resolve().parents[1]


class ProductionTests(SimpleTestCase):
    def test_installer_probes_unprivileged_sandbox_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "systemd-run"
            output = Path(directory) / "args.json"
            runner.write_text(
                f"#!{sys.executable}\n"
                "import json,os,sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['PROBE_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
                "sys.exit(int(os.environ['PROBE_EXIT']))\n"
            )
            runner.chmod(0o700)
            for code in (0, 226):
                result = subprocess.run(
                    ["bash", str(ROOT / "deploy/ubuntu24/check-sandbox.sh")],
                    env={
                        **os.environ,
                        "PATH": directory + os.pathsep + os.environ["PATH"],
                        "PROBE_ARGS": str(output),
                        "PROBE_EXIT": str(code),
                    },
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, code)
                args = json.loads(output.read_text())
                for setting in (
                    "User=www-data",
                    "Group=www-data",
                    "NoNewPrivileges=yes",
                    "CapabilityBoundingSet=",
                    "ReadWritePaths=/var/tmp",
                    "PrivateTmp=yes",
                    "ProtectSystem=strict",
                    "ProtectHome=yes",
                    "ProtectKernelTunables=yes",
                    "ProtectKernelModules=yes",
                    "ProtectControlGroups=yes",
                ):
                    self.assertIn("--property=" + setting, args)
                self.assertEqual(args[-1], "/usr/bin/true")

    def config(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "config.production",
                "DJANGO_DEBUG": "0",
                "DJANGO_SECRET_KEY": "synthetic-production-test-secret-" + "x" * 50,
                "DATABASE_URL": "postgresql://bearings@/bearings",
                "BEARINGS_DATA_DIR": directory,
                "BEARINGS_PUBLIC_URL": "https://bearings.circl.lu",
                "DJANGO_ALLOWED_HOSTS": "bearings.circl.lu",
                "BEARINGS_PUBLIC_REGISTRATION": "0",
                "BEARINGS_SERVICE_MAIL_TRANSPORT": "file",
                "BEARINGS_DEV_STACK": "0",
                "BEARINGS_SSO_LAB": "0",
                **overrides,
            }
            return subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import django;django.setup();from django.conf import settings;assert settings.SECURE_SSL_REDIRECT;assert settings.CSRF_TRUSTED_ORIGINS==['https://bearings.circl.lu'];assert not settings.PUBLIC_REGISTRATION_ENABLED;import logging;log=logging.getLogger('django.request');assert not log.propagate;assert len(log.handlers)==1;assert type(log.handlers[0].formatter).__name__=='SafeRequestErrorFormatter'",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_production_profile_and_fail_closed_settings(self):
        self.assertEqual(self.config().returncode, 0)
        for change in (
            {"DJANGO_DEBUG": "1"},
            {"DATABASE_URL": ""},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"BEARINGS_PUBLIC_URL": "http://bearings.circl.lu"},
            {"DJANGO_SECRET_KEY": "REPLACE_" + "x" * 80},
            {"BEARINGS_DEV_STACK": "1"},
            {"BEARINGS_PUBLIC_REGISTRATION": "1"},
        ):
            with self.subTest(change=change):
                self.assertNotEqual(self.config(**change).returncode, 0)

    def test_edge_overwrites_peer_address_and_rejects_missing_or_multiple_ips(self):
        factory = RequestFactory()
        response = ClientAddress(lambda request: HttpResponse(request.META["REMOTE_ADDR"]))(
            factory.get("/", HTTP_X_REAL_IP="198.51.100.20", HTTP_X_FORWARDED_FOR="untrusted-input")
        )
        self.assertEqual(response.content, b"198.51.100.20")
        for value in ("", "198.51.100.1,198.51.100.2", "bad", "fe80::1%eth0"):
            self.assertEqual(
                ClientAddress(lambda request: HttpResponse("unexpected"))(
                    factory.get("/", HTTP_X_REAL_IP=value)
                ).status_code,
                400,
            )

    def test_worker_has_no_lab_setup_and_preserves_progress_after_failure(self):
        calls = []

        def run(name, **kwargs):
            calls.append(name)
            if name == "sync_netbox":
                raise CommandError("synthetic-secret-must-not-be-logged")

        out, err = StringIO(), StringIO()
        with patch("portal.management.commands.run_worker.call_command", side_effect=run):
            call_command("run_worker", once=True, stdout=out, stderr=err)
        self.assertEqual(calls, [name for name, _ in JOBS])
        self.assertNotIn("synthetic-secret", err.getvalue())
        self.assertNotIn("seed_demo", calls)
        self.assertNotIn("setup_dev_stack", calls)
        self.assertEqual(dict(JOBS)["process_jobs"]["limit"], 5)

    def test_write_poll_rejects_unbounded_limits_before_database_access(self):
        for limit in (0, 101):
            with self.assertRaises(CommandError):
                call_command("process_jobs", limit=limit, stdout=StringIO())
