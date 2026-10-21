"""Bundled RT startup identity, policy-retention and endpoint regressions."""

import json
import os
from pathlib import Path
import tempfile
import subprocess
from unittest.mock import patch
import uuid

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings

from scripts import dev
from . import tests
from .models import RTInstance


class RTStarterTests(SimpleTestCase):
    def test_perl_private_input_reader_removes_terminal_newline(self):
        source = (dev.ROOT / "docker/rt/RT_SiteConfig.pm").read_text().split("my $lab =", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-key"
            path.write_text("synthetic-only-input\n")
            subprocess.run(
                [
                    "perl",
                    "-e",
                    source + "die unless lab_file($ARGV[0]) eq 'synthetic-only-input';",
                    str(path),
                ],
                check=True,
                capture_output=True,
            )

    def test_optional_rt_profiles_are_independent_and_external_is_refused(self):
        self.assertNotIn(str(dev.ROOT / "compose.rt.yaml"), dev.compose("bundled", "test", True, True))
        base = dev.compose("bundled", "test", False, False, True)
        self.assertEqual(base[-1], str(dev.ROOT / "compose.rt.yaml"))
        combined = dev.compose("bundled", "test", True, True, True)
        self.assertEqual(combined[-1], str(dev.ROOT / "compose.rt-sso.yaml"))
        self.assertIn(str(dev.ROOT / "compose.flowintel-sso.yaml"), combined)
        with self.assertRaises(SystemExit):
            dev.compose("external", "test", False, False, True)

    def test_old_state_defaults_rt_off_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            text = json.dumps({"mode": "bundled", "project": "retained", "sso": True})
            path.write_text(text)
            with patch.object(dev, "STATE", path):
                self.assertFalse(dev.active()["rt"])
                self.assertTrue(dev.active()["sso"])
            self.assertEqual(path.read_text(), text)

    def test_rt_initialization_preserves_sso_inputs_and_refuses_endpoint_changes(self):
        from docker.rt.initialize import initialize

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["secrets", "rt-secrets", "tls"]:
                (root / name).mkdir()
            (root / "secrets/oidc-lab.json").write_text(
                json.dumps(
                    {
                        "issuer": "https://localhost:9444/realms/bearings-lab",
                        "users": {"company-admin": "company-sub", "circl-analyst": "circl-sub"},
                    }
                )
            )
            (root / "tls/ca.crt").write_text("synthetic-public-ca")

            def write(path, value, **kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)

            def secret(path):
                if not path.exists():
                    write(path, uuid.uuid4().hex)
                return path.read_text().strip()

            with (
                patch("docker.rt.initialize.os.chown"),
                patch.dict(os.environ, {"RT_PORT": "9445", "RT_RECOVERY_PORT": "9446"}),
            ):
                initialize(root, write, secret, sso=False)
                self.assertFalse((root / "rt-sso").exists())
                initialize(root, write, secret, sso=True)
                original = (root / "rt-sso/keycloak-client.json").read_text()
                initialize(root, write, secret, sso=True)
                self.assertEqual((root / "rt-sso/keycloak-client.json").read_text(), original)
                self.assertIn("OIDCProviderIssuer", (root / "rt-sso/apache-lab.conf").read_text())
                self.assertNotIn("OIDCProviderMetadataURL", (root / "rt-sso/apache-lab.conf").read_text())
                self.assertEqual(
                    json.loads(original)["redirectUris"], ["https://localhost:9445/NoAuth/bearings-oidc"]
                )
                with patch.dict(os.environ, RT_PORT="9555"), self.assertRaises(ValueError):
                    initialize(root, write, secret, sso=True)


class RTLabBindingTests(tests.Fixture):
    def files(self, path, *args, **kwargs):
        if path.name == "connections.json":
            return json.dumps(
                {
                    "mode": "bundled",
                    "connections": [{"access_mode": "read_write", "organization_slug": self.a.slug}],
                }
            )
        return json.dumps(
            {
                "base_url": "https://rt.bearings.test",
                "browser_url": "https://localhost:9445",
                "queues": {"company": 3, "circl": 4},
            }
        )

    @override_settings(DEBUG=True)
    def test_defaults_are_scoped_and_existing_disabled_policies_are_preserved(self):
        with (
            patch.dict(os.environ, BEARINGS_DEV_STACK="1", BEARINGS_RT="1"),
            patch.object(Path, "read_text", autospec=True, side_effect=self.files),
        ):
            call_command("setup_rt_lab")
            company = RTInstance.objects.get(name="bundled-rt-company")
            circl = RTInstance.objects.get(name="bundled-rt-circl")
            self.assertEqual(company.organization, self.a)
            self.assertIsNone(circl.organization)
            self.assertNotEqual(company.token_env_var, circl.token_env_var)
            company.enabled = company.private_queue_confirmed = False
            company.save()
            call_command("setup_rt_lab")
            company.refresh_from_db()
            self.assertFalse(company.enabled)
            self.assertFalse(company.private_queue_confirmed)
            company.queue_id = 99
            company.save()
            with self.assertRaises(CommandError):
                call_command("setup_rt_lab")

    @override_settings(DEBUG=False)
    def test_setup_refuses_non_lab_before_creating_connections(self):
        with self.assertRaises(CommandError):
            call_command("setup_rt_lab")
        self.assertFalse(RTInstance.objects.exists())
