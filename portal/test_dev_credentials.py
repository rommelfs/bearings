"""Credential directory follows published ports and never probes or provisions external services."""

import io
import json
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from django.test import SimpleTestCase
from scripts.dev_credentials import directory, published_origin


class CredentialDirectoryTests(SimpleTestCase):
    def runner(self):
        ports = {
            ("web", "8000"): 18000,
            ("bearings-tls", "443"): 19441,
            ("netbox-tls", "443"): 18443,
            ("netbox-tls", "444"): 19444,
            ("netbox-tls", "445"): 19445,
            ("netbox-tls", "446"): 19446,
            ("flowintel-tls", "443"): 19443,
        }

        def result(args, **kwargs):
            if args[0] == "port":
                return SimpleNamespace(stdout=f"127.0.0.1:{ports[tuple(args[1:])]}\n")
            if args[-2] == "-c":
                return SimpleNamespace(
                    stdout=json.dumps(
                        [
                            {"username": "additional-owner", "is_active": False},
                            {"username": "escape\u001b[31m", "is_active": True},
                        ]
                    )
                )
            return SimpleNamespace(stdout="")

        return Mock(side_effect=result)

    def test_all_selected_profiles_use_actual_custom_bindings_and_isolated_password_sources(self):
        run = self.runner()
        with redirect_stdout(io.StringIO()) as output:
            directory(
                {"mode": "bundled", "sso": True, "flowintel": True, "rt": True, "rtir": True},
                [],
                run,
                Path("unused"),
            )
        text = output.getvalue()
        for route in [
            "https://localhost:19441/accounts/login/",
            "https://localhost:19441/admin/",
            "https://localhost:19441/operator/registrations/?status=awaiting_email",
            "https://localhost:18443/login/",
            "https://localhost:19443/account/login",
            "https://localhost:19444/admin/master/console/",
            "https://localhost:19446/NoAuth/Login.html",
            "https://localhost:19445/RTIR/",
        ]:
            self.assertIn(route, text)
        for account in [
            "platform-admin",
            "company-admin",
            "circl-analyst",
            "unassigned-demo",
            "sso-admin",
            "netbox-admin",
            "platform-admin@example.com",
            "circl-analyst@example.com",
            "root",
            "additional-owner",
        ]:
            self.assertIn(account, text)
        self.assertNotIn("\u001b", text)
        paths = [call.args[0][-1] for call in run.call_args_list if "cat" in call.args[0]]
        self.assertEqual(
            set(paths),
            {
                "/run/bearings/secrets/demo_password",
                "/run/credentials/bootstrap_password",
                "/run/flowintel/demo_password",
                "/run/rt/demo_password",
            },
        )

    def test_external_mode_does_not_request_bundled_or_external_credentials(self):
        run = self.runner()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "connection.json"
            path.write_text(json.dumps({"base_url": "https://inventory.example.invalid/netbox"}))
            with redirect_stdout(io.StringIO()) as output:
                directory({"mode": "external"}, [], run, path)
            self.assertIn("https://inventory.example.invalid/netbox", output.getvalue())
            self.assertIn("http://localhost:18000/accounts/login/", output.getvalue())
            self.assertEqual(
                [c.args[0] for c in run.call_args_list if c.args[0][0] == "port"], [["port", "web", "8000"]]
            )
            self.assertEqual(
                [c.args[0][-1] for c in run.call_args_list if "cat" in c.args[0]],
                ["/run/bearings/secrets/demo_password"],
            )
            path.write_text(json.dumps({"base_url": "https://user:do-not-print@example.invalid"}))
            with redirect_stdout(io.StringIO()) as output:
                directory({"mode": "external"}, [], run, path)
            self.assertNotIn("do-not-print", output.getvalue())

    def test_missing_or_unexpected_publication_is_not_replaced_with_a_guessed_port(self):
        for stdout in ["", "bad binding", "example.invalid:443", "127.0.0.1:99999"]:
            with self.subTest(stdout=stdout):
                self.assertIsNone(
                    published_origin([], Mock(return_value=SimpleNamespace(stdout=stdout)), "web", 8000)
                )
        self.assertIsNone(
            published_origin([], Mock(side_effect=subprocess.CalledProcessError(1, ["port"])), "web", 8000)
        )
        run = self.runner()

        def fail(args, **kwargs):
            if "cat" in args:
                return SimpleNamespace(stdout="")
            raise subprocess.CalledProcessError(1, args)

        run.side_effect = fail
        with redirect_stdout(io.StringIO()) as output:
            directory({"mode": "bundled"}, [], run, Path("unused"))
        self.assertIn("not published", output.getvalue())
        self.assertIn("current account state could not be read", output.getvalue())
