"""Operator deployment boundaries; no host users, services or network operations."""

import configparser
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import ssl
import socket
import unittest
import uuid
from types import SimpleNamespace
import io
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_ecosystem", ROOT / "deploy/ubuntu24/ecosystem.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def fixture():
    return {
        "admin_email": "operator@example.invalid",
        "lxc_compatible": True,
        "secrets": {
            name: "synthetic-private-" + name
            for name in (
                "bearings_oidc",
                "netbox_oidc",
                "flowintel_oidc",
                "netbox_key",
                "netbox_pepper",
                "flowintel_key",
                "flowintel_admin",
                "keycloak_admin",
                "keycloak_db",
                "unused_db",
            )
        },
    }


class NativeDeploymentTests(unittest.TestCase):
    def test_client_publish_rejects_dirty_source_before_downloading(self):
        with (
            patch.object(native, "run", return_value=SimpleNamespace(stdout="modified source")),
            patch.object(native.urllib.request, "urlopen") as download,
        ):
            with self.assertRaisesRegex(ValueError, "clean reviewed checkout"):
                native.prepare_linux_client()
        download.assert_not_called()

    def test_client_compiler_checksum_failure_never_extracts_or_publishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            apps = Path(temporary)
            with (
                patch.object(native, "APPS", apps),
                patch.object(native.platform, "machine", return_value="x86_64"),
                patch.object(native, "run", return_value=SimpleNamespace(stdout="")),
                patch.object(
                    native.urllib.request, "urlopen", return_value=io.BytesIO(b"synthetic-invalid-archive")
                ),
                patch.object(native.tarfile, "open") as extract,
                patch.object(native, "write") as publish,
            ):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    native.prepare_linux_client()
            extract.assert_not_called()
            publish.assert_not_called()
            self.assertEqual(list(apps.iterdir()), [])

    def test_failed_client_build_preserves_active_release_and_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apps = root / "apps"
            releases = root / "releases"
            apps.mkdir()
            releases.mkdir()
            tool = apps / ("go-" + native.GO_VERSION + "-amd64")
            tool.mkdir()
            kept = releases / "old"
            kept.mkdir()
            (kept / "kept").write_text("original")

            def run(args, **kwargs):
                if str(args[0]) == "git":
                    return SimpleNamespace(stdout="")
                if args[-1] == "version":
                    return SimpleNamespace(stdout=f"go version go{native.GO_VERSION} linux/amd64")
                raise subprocess.CalledProcessError(1, ["synthetic-client-build"])

            with (
                patch.object(native, "APPS", apps),
                patch.object(native, "CLIENT_RELEASES", releases),
                patch.object(native.platform, "machine", return_value="x86_64"),
                patch.object(native, "protected_read", return_value=native.GO_SHA256["amd64"]),
                patch.object(native, "directory"),
                patch.object(native, "run", side_effect=run),
                patch.object(native, "write") as publish,
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    native.prepare_linux_client()
            publish.assert_not_called()
            self.assertEqual(list(releases.iterdir()), [kept])
            self.assertEqual((kept / "kept").read_text(), "original")

    def test_combined_client_publish_switches_both_paths_and_preserves_prior_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apps, releases, config = (root / path for path in ("apps", "releases", "config"))
            old = releases / "old"
            old.mkdir(parents=True)
            env = root / "bearings.env"
            current = (
                "DJANGO_SECRET_KEY=synthetic-retained-key\n"
                f"BEARINGS_LINUX_CLIENT_DIR={old}\nBEARINGS_WINDOWS_CLIENT_DIR={old}\n"
            )
            env.write_text(current)
            builds = []

            def run(args, **kwargs):
                if str(args[0]) == "git":
                    return SimpleNamespace(stdout="")
                self.assertEqual(env.read_text(), current)
                self.assertNotEqual(args[0], "systemctl")
                builds.append(Path(args[1]).name)
                target = args[-1]
                target.mkdir()
                output = target / "SHA256SUMS"
                output.write_text("synthetic manifest")
                output.chmod(0o600)

            with (
                patch.object(native, "APPS", apps),
                patch.object(native, "CLIENT_RELEASES", releases),
                patch.object(native, "CONFIG", config),
                patch.object(native, "BEARINGS_ENV", env),
                patch.object(native, "protected_read", side_effect=Path.read_text),
                patch.object(native, "directory", side_effect=lambda path, **_: path.mkdir(exist_ok=True)),
                patch.object(native, "client_compiler", return_value="/synthetic/go"),
                patch.object(native, "run", side_effect=run),
            ):
                native.prepare_clients(restart=False)

            self.assertEqual(builds, ["build_linux_client.py", "build_windows_client.py"])
            self.assertTrue(old.is_dir())
            self.assertEqual((config / "bearings-before-client-builds.env").read_text(), current)
            published = next(path for path in releases.iterdir() if path != old)
            self.assertIn(f'BEARINGS_LINUX_CLIENT_DIR="{published / "linux"}"', env.read_text())
            self.assertIn(f'BEARINGS_WINDOWS_CLIENT_DIR="{published / "windows"}"', env.read_text())
            self.assertIn("DJANGO_SECRET_KEY=synthetic-retained-key", env.read_text())
            self.assertEqual((published / "windows/SHA256SUMS").stat().st_mode & 0o777, 0o644)

    def test_failed_windows_build_keeps_both_environment_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apps, releases = root / "apps", root / "releases"

            def run(args, **kwargs):
                if str(args[0]) == "git":
                    return SimpleNamespace(stdout="")
                if Path(args[1]).name == "build_linux_client.py":
                    args[-1].mkdir()
                    return SimpleNamespace(stdout="")
                raise subprocess.CalledProcessError(1, ["synthetic-windows-build"])

            with (
                patch.object(native, "APPS", apps),
                patch.object(native, "CLIENT_RELEASES", releases),
                patch.object(native, "directory", side_effect=lambda path, **_: path.mkdir(exist_ok=True)),
                patch.object(native, "client_compiler", return_value="/synthetic/go"),
                patch.object(native, "run", side_effect=run),
                patch.object(native, "write") as publish,
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    native.prepare_clients()
            publish.assert_not_called()
            self.assertEqual(list(releases.iterdir()), [])

    def test_mail_environment_preserves_keys_and_quotes_bracket_relay_and_subject(self):
        before = 'DJANGO_SECRET_KEY=retained-secret\nOTHER="retained value"\nSMTP_HOST=old\n'
        result = native.merge_environment(
            before,
            {
                "SMTP_HOST": "[cped.circl.lu]",
                "BEARINGS_MAIL_SUBJECT_PREFIX": "[CIRCL BEARINGS]",
                "SMTP_USER": "",
            },
        )
        self.assertIn('DJANGO_SECRET_KEY=retained-secret\nOTHER="retained value"\n', result)
        self.assertIn('SMTP_HOST="[cped.circl.lu]"\n', result)
        self.assertIn('BEARINGS_MAIL_SUBJECT_PREFIX="[CIRCL BEARINGS]"\n', result)
        self.assertNotIn("SMTP_HOST=old", result)
        for value in ["x\ny", "$(whoami)", "x`id`", 'a"b', "a%u"]:
            with self.assertRaises(ValueError):
                native.merge_environment(before, {"SMTP_HOST": value})

    def test_staged_mail_uses_actual_settings_names_without_releasing_delivery(self):
        before = "DJANGO_SETTINGS_MODULE=config.production\nDJANGO_SECRET_KEY=kept\n"
        with (
            patch.object(native, "protected_read", return_value=before),
            patch.object(native, "write") as write,
            patch.object(native, "run"),
            patch.object(Path, "exists", return_value=True),
            patch("builtins.print"),
        ):
            native.configure_mail()
        result = write.call_args.args[1]
        for expected in [
            'SMTP_HOST="[cped.circl.lu]"',
            'SMTP_PORT="25"',
            'SMTP_STARTTLS="1"',
            'SMTP_PASSWORD=""',
            'DJANGO_DEFAULT_FROM_EMAIL="info@circl.lu"',
            'BEARINGS_SERVICE_MAIL_TRANSPORT="file"',
            'BEARINGS_PUBLIC_REGISTRATION="0"',
        ]:
            self.assertIn(expected, result)
        self.assertIn("DJANGO_SECRET_KEY=kept", result)

    def test_captured_service_credentials_never_allocate_a_terminal(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(native, "run") as run:
            native.service_run("netbox", ["synthetic-check"], capture=True)
        self.assertIn("--pipe", run.call_args.args[0])
        self.assertNotIn("--pty", run.call_args.args[0])
        self.assertTrue(run.call_args.kwargs["capture"])

    def test_batch_commands_from_terminal_use_pipes_and_password_prompts_keep_pty(self):
        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(native, "run") as run:
            for args in (
                ["migrate", "--noinput"],
                ["collectstatic", "--noinput"],
                ["check"],
                ["shell", "-c", "print('synthetic')"],
                ["createsuperuser", "--noinput"],
            ):
                native.django("netbox", args)
                self.assertIn("--pipe", run.call_args.args[0])
                self.assertNotIn("--pty", run.call_args.args[0])
            native.django("netbox", ["createsuperuser", "--username", "platform-admin"])
            self.assertIn("--pty", run.call_args.args[0])
            native.service_run("flowintel", ["synthetic-init"])
            self.assertIn("--pipe", run.call_args.args[0])

    def test_explicit_self_signed_flag_is_relay_bound_and_keeps_starttls(self):
        with (
            patch.object(native, "protected_read", return_value="DJANGO_SECRET_KEY=kept\n"),
            patch.object(native, "write") as write,
            patch.object(native, "run"),
            patch.object(Path, "exists", return_value=True),
            patch("builtins.print"),
        ):
            native.configure_mail(allow_self_signed=True)
        result = write.call_args.args[1]
        for expected in [
            'SMTP_TLS_VERIFY="0"',
            'SMTP_TLS_UNVERIFIED_HOST="cped.circl.lu"',
            'SMTP_STARTTLS="1"',
            'BEARINGS_SERVICE_MAIL_TRANSPORT="file"',
        ]:
            self.assertIn(expected, result)

    def test_plan_requires_no_root_and_does_not_mutate(self):
        with patch.object(native, "run", side_effect=AssertionError("unexpected mutation")):
            with patch.object(sys, "argv", ["ecosystem.py", "plan"]), patch("builtins.print") as output:
                native.main()
        result = json.loads(output.call_args.args[0])
        self.assertEqual(len(result["urls"]), 3)
        self.assertNotIn("secrets", result)

    def test_realm_has_exact_callbacks_pkce_and_no_fixture_users_or_password_grants(self):
        result = native.realm(fixture())
        self.assertEqual(result["users"], [])
        self.assertFalse(result["registrationAllowed"])
        for client in result["clients"]:
            self.assertEqual(len(client["redirectUris"]), 1)
            self.assertNotIn("*", client["redirectUris"][0])
            self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
            self.assertFalse(client["directAccessGrantsEnabled"])
            self.assertFalse(client["serviceAccountsEnabled"])
            self.assertFalse(client["publicClient"])

    def test_activation_preserves_private_environment_and_refuses_existing_identity_repoint(self):
        state = fixture()
        original = "DJANGO_SECRET_KEY='private key # keep exactly'\nBEARINGS_PUBLIC_REGISTRATION=0\n"
        result = native.bearings_env(state, original)
        self.assertIn(original, result)
        self.assertIn("BEARINGS_SSO_ENABLED=1", result)
        self.assertEqual(native.bearings_env(state, result), result)
        for existing in (
            "OIDC_ISSUER=https://other.example/realm",
            "OIDC_CLIENT_SECRET=other",
            "BEARINGS_SSO_ENABLED = 0",
        ):
            with self.subTest(existing=existing), self.assertRaises(ValueError):
                native.bearings_env(state, original + existing + "\n")

    def test_generated_environment_does_not_accept_injection(self):
        for value in ("a\nOTHER=value", "$(id)", "has spaces", 'x"y', "x%y"):
            with self.assertRaises(ValueError):
                native.environment({"TEST": value})

    def test_atomic_private_write_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "secret"
            native.write(path, "retained")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            link = Path(temporary) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                native.write(link, "replace")
            self.assertEqual(path.read_text(), "retained")

    def test_sandbox_compatibility_is_explicit_and_retains_identity_capability_controls(self):
        for compatible in (True, False):
            state = {**fixture(), "lxc_compatible": compatible}
            text = native.unit("netbox", "/usr/bin/true", "/", state)
            unit = configparser.ConfigParser(interpolation=None)
            unit.read_string(text)
            self.assertEqual(unit["Unit"]["Requires"], "bearings-netbox-redis.service")
            self.assertEqual(unit["Service"]["User"], "bearings_netbox")
            self.assertEqual(unit["Service"]["NoNewPrivileges"], "yes")
            self.assertEqual(unit["Service"]["CapabilityBoundingSet"], "")
            self.assertEqual("ProtectSystem=strict" in text, not compatible)
            self.assertEqual("ReadWritePaths=" in text, not compatible)

    def test_bootstrap_exposes_only_challenges_and_tls_preserves_forwarding_boundary(self):
        for name in native.HOSTS:
            plain = native.nginx(name, tls=False)
            self.assertNotIn("proxy_pass", plain)
            self.assertIn("listen [::]:80;", plain)
            self.assertIn("return 404", plain)
            text = native.nginx(name, tls=True)
            self.assertIn("listen [::]:80;", text)
            self.assertIn("listen [::]:443 ssl;", text)
            self.assertIn("proxy_set_header Host $http_host;", text)
            self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", text)
            self.assertIn("access_log off;", text)
            self.assertNotIn("$proxy_add_x_forwarded_for", text)
        self.assertIn("internal;", native.nginx("netbox", tls=True))

    def test_issuer_transport_errors_are_actionable_without_leaking_exception_details(self):
        from urllib.error import URLError, HTTPError

        cases = (
            (URLError(ssl.SSLCertVerificationError("private-error-value")), "IPv4/IPv6 vhosts"),
            (URLError(socket.gaierror("private-error-value")), "DNS resolution failed"),
            (URLError(TimeoutError("private-error-value")), "connection timed out"),
            (URLError(ConnectionRefusedError("private-error-value")), "connection refused"),
            (URLError("private-error-value"), "proxy configuration"),
            (HTTPError(native.ISSUER, 502, "private-error-value", {}, None), "HTTP 502"),
        )
        for error, expected in cases:
            with (
                self.subTest(expected=expected),
                patch.object(native.urllib.request, "build_opener") as build,
            ):
                build.return_value.open.side_effect = error
                with self.assertRaises(ValueError) as raised:
                    native.verify_issuer()
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("private-error-value", str(raised.exception))
                self.assertIn("SSO remains unchanged", str(raised.exception))

    def test_reload_readiness_retries_only_transient_failures_with_finite_attempts(self):
        with patch.object(
            native, "verify_issuer", side_effect=[native.IssuerNotReady("old worker"), None]
        ) as check:
            with patch.object(native.time, "sleep") as pause:
                native.wait_for_issuer()
        self.assertEqual(check.call_count, 2)
        check.assert_called_with(timeout=2)
        pause.assert_called_once_with(0.25)
        with patch.object(
            native, "verify_issuer", side_effect=native.IssuerNotReady("still invalid")
        ) as check:
            with patch.object(native.time, "sleep") as pause, self.assertRaises(native.IssuerNotReady):
                native.wait_for_issuer()
        self.assertEqual(check.call_count, 8)
        self.assertEqual(pause.call_count, 7)
        with patch.object(native, "verify_issuer", side_effect=ValueError("wrong issuer")) as check:
            with patch.object(native.time, "sleep") as pause, self.assertRaises(ValueError):
                native.wait_for_issuer()
        self.assertEqual(check.call_count, 1)
        pause.assert_not_called()

    def test_issuer_check_keeps_https_identity_size_and_redirect_boundaries(self):
        for payload in (
            json.dumps({"issuer": native.ISSUER}).encode(),
            b'{"issuer":"https://wrong.example"}',
            b"[]",
            b"x" * 1000001,
        ):
            with (
                self.subTest(size=len(payload)),
                patch.object(native.urllib.request, "build_opener") as build,
            ):
                build.return_value.open.return_value.__enter__.return_value.read.return_value = payload
                if payload == json.dumps({"issuer": native.ISSUER}).encode():
                    native.verify_issuer()
                else:
                    with self.assertRaises(ValueError):
                        native.verify_issuer()
                build.return_value.open.assert_called_once_with(
                    native.ISSUER + "/.well-known/openid-configuration", timeout=15
                )
                self.assertIsInstance(build.call_args.args[0], native.NoRedirect)

    def test_readiness_does_not_accept_systemctl_start_alone(self):
        result = subprocess.CompletedProcess([], 7)
        with patch.object(native.subprocess, "run", return_value=result), patch.object(native.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "readiness failed"):
                native.wait_ready()

    def test_privileged_entry_refuses_developer_checkout_without_mutations(self):
        with (
            patch.object(sys, "argv", ["ecosystem.py", "install"]),
            patch.object(os, "geteuid", return_value=0),
        ):
            with patch.object(native, "run", side_effect=AssertionError("unexpected mutation")):
                with self.assertRaises(ValueError):
                    native.main()


class NativeManagedDeploymentTests(unittest.TestCase):
    def test_managed_plan_has_no_upstream_mutations_or_secret_output(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            receipt = {
                "key": str(uuid.uuid4()),
                "netbox": {"tenant": 42, "value": "synthetic-private-token"},
            }
            (config / "circl-connection.json").write_text(json.dumps(receipt))
            args = SimpleNamespace(
                actor="operator",
                netbox_actor="native-admin",
                host="synthetic.example.invalid",
                kind="vm",
                virtualization="lxc",
                apply=False,
                verify=False,
            )
            output = io.StringIO()
            with (
                patch.object(native, "CONFIG", config),
                patch.object(native, "protected_read", side_effect=lambda path: Path(path).read_text()),
                patch.object(
                    native,
                    "bearings_manage",
                    return_value=SimpleNamespace(stdout=json.dumps({"managed": False})),
                ) as manage,
                patch.object(native, "django") as upstream,
                patch.object(native, "write") as write,
                patch.object(native, "run") as run,
                patch("sys.stdout", output),
            ):
                native.managed_circl_inventory({"activated": True}, args)
                self.assertEqual(manage.call_count, 1)
                upstream.assert_not_called()
                write.assert_not_called()
                run.assert_not_called()
            self.assertNotIn(receipt["netbox"]["value"], output.getvalue())

    def test_verify_keeps_native_calls_captured_and_does_not_restart_services(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            saved = {
                "tenant": 42,
                "managed": True,
                "value": "synthetic-private-token",
                "defaults": {"virtualization_tags": {"lxc": 7}},
            }
            (config / "circl-connection.json").write_text(
                json.dumps({"key": str(uuid.uuid4()), "netbox": saved})
            )
            args = SimpleNamespace(
                actor="operator",
                netbox_actor="native-admin",
                host="synthetic.example.invalid",
                kind="vm",
                virtualization="lxc",
                apply=False,
                verify=True,
            )
            result = {
                key: True
                for key in [
                    "managed",
                    "uuid_match",
                    "tenant_match",
                    "import_match",
                    "agent_software_reviews_preserved",
                ]
            }
            output = io.StringIO()
            with (
                patch.object(native, "CONFIG", config),
                patch.object(native, "protected_read", side_effect=lambda path: Path(path).read_text()),
                patch.object(
                    native,
                    "bearings_manage",
                    side_effect=[
                        SimpleNamespace(stdout='{"managed":true}'),
                        SimpleNamespace(stdout=json.dumps(result)),
                    ],
                ) as manage,
                patch.object(
                    native, "django", return_value=SimpleNamespace(stdout=json.dumps(saved))
                ) as upstream,
                patch.object(native, "write"),
                patch.object(native, "run") as run,
                patch("sys.stdout", output),
            ):
                native.managed_circl_inventory({"activated": True}, args)
                run.assert_not_called()
                self.assertTrue(upstream.call_args.kwargs["capture"])
                self.assertNotIn(saved["value"], str(upstream.call_args.args))
                self.assertIn("--verify", manage.call_args.args[0])
                self.assertNotIn(saved["value"], manage.call_args.kwargs["input"])
            self.assertNotIn(saved["value"], output.getvalue())

    def test_inventory_export_verify_checks_retained_policy_without_applying_or_restarting(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            saved = {
                "tenant": 42,
                "managed": True,
                "value": "synthetic-private-token",
                "defaults": {},
                "export": {"inventory": True, "vrf": 7},
            }
            (config / "circl-connection.json").write_text(
                json.dumps({"key": str(uuid.uuid4()), "netbox": saved})
            )
            args = SimpleNamespace(
                actor="operator",
                netbox_actor="native-admin",
                host="synthetic.example.invalid",
                kind="vm",
                virtualization="lxc",
                apply=False,
                verify=True,
                export_inventory=True,
            )
            result = {
                key: True
                for key in (
                    "managed",
                    "uuid_match",
                    "tenant_match",
                    "import_match",
                    "agent_software_reviews_preserved",
                )
            }
            output = io.StringIO()
            with (
                patch.object(native, "CONFIG", config),
                patch.object(native, "protected_read", side_effect=lambda path: Path(path).read_text()),
                patch.object(
                    native,
                    "bearings_manage",
                    side_effect=[
                        SimpleNamespace(stdout=json.dumps({"source": str(uuid.uuid4())})),
                        SimpleNamespace(stdout=json.dumps({"current_policy": saved["export"]})),
                        SimpleNamespace(stdout=json.dumps(result)),
                    ],
                ) as manage,
                patch.object(
                    native, "django", return_value=SimpleNamespace(stdout=json.dumps(saved))
                ) as upstream,
                patch.object(native, "write"),
                patch.object(native, "run") as run,
                patch("sys.stdout", output),
            ):
                native.managed_circl_inventory({"activated": True}, args)
                run.assert_not_called()
                self.assertTrue(json.loads(upstream.call_args.kwargs["input"])["verify_only"])
                self.assertTrue(json.loads(upstream.call_args.kwargs["input"])["export_inventory"])
                self.assertTrue(
                    any(call.args[0][0] == "configure_netbox_export" for call in manage.call_args_list)
                )
                self.assertFalse(any("--apply" in call.args[0] for call in manage.call_args_list))
                self.assertNotIn(saved["value"], output.getvalue())


if __name__ == "__main__":
    unittest.main()
