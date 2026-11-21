# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unprivileged installer boundaries. Privileged flow is exercised in a disposable container."""

import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("linux_installer", Path(__file__).with_name("install.py"))
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
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

    def test_cli_requires_root_before_touching_system(self):
        with patch("sys.argv", ["install.py"]), patch.object(installer.os, "geteuid", return_value=1000):
            with patch.object(installer, "systemctl") as command, self.assertRaises(installer.InstallError):
                installer.main()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
