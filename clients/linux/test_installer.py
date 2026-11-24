# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unprivileged installer boundaries. Privileged flow is exercised in a disposable container."""

import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import os
import json
import pwd
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location("linux_installer", Path(__file__).with_name("install.py"))
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_sources_keep_python38_grammar_compatibility(self):
        for filename in ("install.py", "test_installer.py"):
            with self.subTest(filename=filename):
                ast.parse(Path(__file__).with_name(filename).read_text(), feature_version=8)

    def test_recovery_gate_resumes_only_after_pending_transaction_was_restored(self):
        for remains in (False, True):
            with ExitStack() as contexts:
                contexts.enter_context(self.subTest(pending_remains=remains))
                contexts.enter_context(patch.object(installer, "regular", side_effect=[True, True, remains]))
                contexts.enter_context(
                    patch.object(installer, "read_update_json", return_value={"active": True})
                )
                systemctl = contexts.enter_context(patch.object(installer, "systemctl"))
                contexts.enter_context(
                    patch.object(installer, "update_state", return_value=Path("/synthetic/pending.json"))
                )
                installer.prepare_recovery_gate()
                self.assertEqual(
                    systemctl.call_args_list[0].args, ("start", "bearings-linux-update-recover-boot.service")
                )
                self.assertEqual(systemctl.call_count, 1 if remains else 2)

    def test_local_source_is_bounded_and_rejects_symlinks_and_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grant.json"
            path.write_bytes(b"synthetic-public-fixture")
            self.assertEqual(installer.source(path, 100), path.read_bytes())
            with self.assertRaises(installer.InstallError):
                installer.source(path, 4)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(installer.InstallError):
                installer.source(link, 100)
            with self.assertRaises(installer.InstallError):
                installer.source(directory, 100)

    def test_existing_private_state_file_and_symlink_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key"
            path.write_bytes(b"synthetic-fixture")
            path.chmod(0o600)
            self.assertTrue(installer.regular(path, os.getuid(), private=True))
            path.chmod(0o644)
            with self.assertRaises(installer.InstallError):
                installer.regular(path, os.getuid(), private=True)
            path.unlink()
            path.symlink_to(Path(directory) / "missing")
            with self.assertRaises(installer.InstallError):
                installer.regular(path, os.getuid())

    def test_wrong_architecture_fails_before_any_system_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-client"
            path.write_bytes(b"\x7fELF\x02\x01" + b"\0" * 14)
            with patch.object(installer, "run") as run, self.assertRaises(installer.InstallError):
                installer.install(path, Path(directory) / "no-unit")
            run.assert_not_called()

    def test_registration_code_transport_and_invalid_input(self):
        import base64
        import json

        raw = json.dumps({"schema": "bearings.agent.grant.v1", "grant": "synthetic"}).encode()
        code = "bearings-enroll-v1." + base64.urlsafe_b64encode(raw).decode().rstrip("=")
        self.assertEqual(installer.decode_code(code), raw)
        for bad in ("not-a-code", "bearings-enroll-v1.@@@", "bearings-enroll-v1." + "x" * 17000):
            with self.assertRaises(installer.InstallError):
                installer.decode_code(bad)

    def test_ca_input_cannot_publish_a_private_key_or_arbitrary_file(self):
        for raw in (b"-----BEGIN PRIVATE KEY-----\nsynthetic\n-----END PRIVATE KEY-----", b"arbitrary data"):
            with self.assertRaises(installer.InstallError):
                installer.ca_context(raw)

    def test_hardening_digest_matches_the_distributed_unit(self):
        unit = Path(__file__).parent / "systemd/bearings-linux.service"
        self.assertEqual(hashlib.sha256(unit.read_bytes()).hexdigest(), installer.UNIT_SHA256)

    def test_only_exact_reviewed_units_can_be_upgraded(self):
        current = (Path(__file__).parent / "systemd/bearings-linux.service").read_bytes()
        previous = current.replace(
            b"# AF_NETLINK is required to read local interface/address metadata without probing.\n",
            b"",
        ).replace(b"AF_INET6 AF_NETLINK", b"AF_INET6")
        self.assertTrue(installer.reviewed_unit(current))
        self.assertTrue(installer.reviewed_unit(previous))
        self.assertFalse(installer.reviewed_unit(previous + b"\nUser=root\n"))
        families = next(
            line for line in current.decode().splitlines() if line.startswith("RestrictAddressFamilies=")
        )
        self.assertEqual(
            set(families.split("=", 1)[1].split()), {"AF_UNIX", "AF_INET", "AF_INET6", "AF_NETLINK"}
        )

    @unittest.skipUnless(os.geteuid() == 0, "credential drop needs disposable/root test runner")
    def test_child_credentials_drop_uid_gid_and_supplementary_groups(self):
        account = pwd.getpwnam("nobody")
        identity = installer.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import os,json; print(json.dumps([os.geteuid(),os.getegid(),os.getgroups()]))",
            ],
            account=account,
            capture=True,
        )
        self.assertEqual(json.loads(identity), [account.pw_uid, account.pw_gid, []])
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o711)
            protected = Path(directory) / "root-only"
            protected.write_bytes(b"synthetic root-only data")
            protected.chmod(0o600)
            with patch.dict(os.environ, {"SUDO_UID": str(account.pw_uid)}):
                with self.assertRaises(installer.InstallError):
                    installer.source(protected, 100)

    def test_command_failure_reports_phase_and_exit_without_secret_output(self):
        with patch.object(
            installer.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=1,
                stdout=b"sensitive output",
                stderr=b"sensitive diagnostics",
            ),
        ):
            with self.assertRaisesRegex(
                installer.InstallError, r"bearings-linux version failed \(exit 1\)"
            ) as error:
                installer.run(["/example/bearings-linux", "version"], capture=True)
            self.assertNotIn("sensitive", str(error.exception))

    def test_systemctl_failure_names_the_fixed_operation_without_raw_output(self):
        with patch.object(
            installer.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1, stdout=b"private", stderr=b"private"),
        ):
            with self.assertRaisesRegex(
                installer.InstallError, r"systemctl enable bearings-linux-update-recover-boot.service failed"
            ) as error:
                installer.systemctl("enable", "--now", "bearings-linux-update-recover-boot.service")
        self.assertNotIn("private", str(error.exception))

    def test_registration_failure_is_actionable_without_forwarding_untrusted_stderr(self):
        for raw, expected in [
            (b"server refused request (HTTP 403); input remains local\n", "HTTP 403"),
            (b"invalid rollout credential on stdin\n", "Invalid rollout-key format"),
            (
                b"another rollout is pending; inspect state without resetting the device key\n",
                "Another rollout is pending",
            ),
            (
                b"HTTPS delivery failed; check connectivity, trusted CA and configured proxy\n",
                "Verified HTTPS",
            ),
        ]:
            with patch.object(
                installer.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stdout=b"private", stderr=raw),
            ):
                with self.assertRaises(installer.InstallError) as error:
                    installer.run(
                        ["/usr/local/bin/bearings-linux", "bootstrap"], input=b"private rollout credential"
                    )
            self.assertIn("bootstrap failed", str(error.exception))
            self.assertIn(expected, str(error.exception))
            self.assertNotIn("private", str(error.exception))
        for raw in (
            b"secret",
            b"server refused request (HTTP 403); input remains local\nsecret",
            b"x" * 1025,
            b"\xff",
        ):
            self.assertEqual(installer.enrollment_failure(raw), "")

    def test_old_python_stops_before_any_system_command(self):
        with patch.object(installer.sys, "version_info", (3, 7, 17)):
            with patch.object(installer, "systemctl") as command:
                with self.assertRaisesRegex(installer.InstallError, "Python 3.8"):
                    installer.main()
            command.assert_not_called()

    def test_updater_self_copy_uses_only_the_executing_script_not_sudo_input_reads(self):
        with ExitStack() as contexts:
            source = contexts.enter_context(patch.object(installer, "source"))
            run = contexts.enter_context(patch.object(installer, "run", return_value=b"script"))
            self.assertEqual(installer.running_installer_source(), b"script")
        source.assert_not_called()
        self.assertEqual(
            run.call_args.args[0][-2:], [str(Path(installer.__file__).absolute()), str(128 * 1024)]
        )
        with patch.object(installer, "run", side_effect=installer.InstallError("child failed")):
            with self.assertRaisesRegex(installer.InstallError, "running installer"):
                installer.running_installer_source()

    def test_update_origin_rejected_before_account_or_system_changes(self):
        for origin in (
            "http://example.invalid",
            "https://user:secret@example.invalid",
            "https://example.invalid/path",
            "https://example.invalid/?token=x",
        ):
            with ExitStack() as contexts:
                account = contexts.enter_context(patch.object(installer, "lookup_account"))
                contexts.enter_context(self.assertRaises(installer.InstallError))
                installer.configure_updates(origin)
            account.assert_not_called()

    def test_install_updates_default_yes_and_explicit_choices_never_read_stdin(self):
        for option, automation, tty, expected in (
            (None, False, False, True),
            (None, True, True, True),
            (True, False, True, True),
            (False, False, True, False),
        ):
            with ExitStack() as contexts:
                contexts.enter_context(self.subTest(option=option, automation=automation, tty=tty))
                contexts.enter_context(patch.object(installer.sys.stdin, "isatty", return_value=tty))
                prompt = contexts.enter_context(patch("builtins.input"))
                self.assertEqual(installer.installation_updates(option, automation), expected)
                prompt.assert_not_called()

    def test_interactive_updates_accept_enter_yes_no_and_reprompt(self):
        for answers, expected in (
            ([""], True),
            (["yes"], True),
            (["ja"], True),
            (["n"], False),
            (["nein"], False),
            (["bad", "no"], False),
        ):
            with ExitStack() as contexts:
                contexts.enter_context(self.subTest(answers=answers))
                contexts.enter_context(patch.object(installer.sys.stdin, "isatty", return_value=True))
                contexts.enter_context(patch("builtins.input", side_effect=answers))
                self.assertEqual(installer.installation_updates(None), expected)
        with ExitStack() as contexts:
            contexts.enter_context(patch.object(installer.sys.stdin, "isatty", return_value=True))
            contexts.enter_context(patch("builtins.input", side_effect=EOFError))
            contexts.enter_context(self.assertRaises(installer.InstallError))
            installer.installation_updates(None)

    def test_unregistered_update_waits_without_download_or_registration(self):
        config = {"schema": "bearings.client-update.v1", "enabled": True, "server": "https://example.invalid"}
        with ExitStack() as contexts:
            contexts.enter_context(patch.object(installer, "recover_update", return_value=False))
            contexts.enter_context(patch.object(installer, "read_update_json", return_value=config))
            contexts.enter_context(patch.object(installer, "lookup_account", return_value=SimpleNamespace()))
            contexts.enter_context(patch.object(installer, "check_state"))
            contexts.enter_context(patch.object(installer, "enrolled", return_value=False))
            download = contexts.enter_context(patch.object(installer, "download"))
            status = contexts.enter_context(patch.object(installer, "update_status"))
            installer.automatic_update()
        download.assert_not_called()
        self.assertEqual(status.call_args.kwargs["result"], "awaiting_enrollment")

    def test_cli_requires_root_before_touching_system(self):
        with patch("sys.argv", ["install.py"]), patch.object(installer.os, "geteuid", return_value=1000):
            with patch.object(installer, "systemctl") as command, self.assertRaises(installer.InstallError):
                installer.main()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
