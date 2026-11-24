"""Synthetic publisher contracts: real signing/ZIPs, a fake compiler, no deployment."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("windows_builder", ROOT / "scripts/build_windows_client.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SignedWindowsReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.key = self.root / "release.key"
        self.seed = bytes(range(32))
        self.key.write_bytes(base64.b64encode(self.seed) + b"\n")
        self.key.chmod(0o600)
        self.go_root = self.root / "go"
        self.go_root.mkdir()
        (self.go_root / "LICENSE").write_text("Synthetic Go license")
        self.flags = []

    def command(self, *args, **kwargs):
        if args[:2] == ("git", "ls-files"):
            return "\n".join(
                str(path.relative_to(ROOT))
                for path in (ROOT / "clients/windows").iterdir()
                if path.suffix in {".go", ".ps1"} or path.name in {"go.mod", "go.sum"}
            )
        if args[:2] == ("git", "rev-parse"):
            return "a" * 40
        if args[:2] == ("git", "status"):
            return ""
        if args[1:] == ("version",):
            return "go version go1.27.4 synthetic"
        if args[1:] == ("env", "GOROOT"):
            return str(self.go_root)
        self.fail(f"Unexpected synthetic command: {args}")

    def compile(self, args, *, cwd, env, check):
        if args[1:3] == ["mod", "verify"]:
            return
        if args[1:3] == ["mod", "vendor"]:
            (cwd / "vendor").mkdir()
            return
        self.assertEqual(args[1], "build")
        flags = args[args.index("-ldflags") + 1]
        self.flags.append(flags)
        self.assertNotIn(base64.b64encode(self.seed).decode(), flags)
        Path(args[args.index("-o") + 1]).write_bytes(b"Synthetic PE fixture: " + env["GOARCH"].encode())

    def build(self, name="output", **kwargs):
        output = self.root / name
        with (
            patch.object(builder, "command", side_effect=self.command),
            patch.object(builder.subprocess, "run", side_effect=self.compile),
        ):
            builder.build(
                "/synthetic/go", output, "https://bearings.example.invalid", signing_key=self.key, **kwargs
            )
        return output

    def test_signed_release_binds_every_zip_and_executable_without_private_seed(self):
        output = self.build(release_sequence=101)
        envelope = json.loads((output / "update.json").read_bytes())
        payload = base64.b64decode(envelope["payload"], validate=True)
        Ed25519PrivateKey.from_private_bytes(self.seed).public_key().verify(
            base64.b64decode(envelope["signature"], validate=True), payload
        )
        release = json.loads(payload)
        self.assertEqual(release["sequence"], 101)
        self.assertEqual(release["origin"], "https://bearings.example.invalid")
        self.assertEqual(set(release["assets"]), {"amd64", "arm64", "386"})
        self.assertEqual(len(self.flags), 3)
        for arch, asset in release["assets"].items():
            package = output / asset["name"]
            self.assertEqual(asset["size"], package.stat().st_size)
            self.assertEqual(asset["sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
            with ZipFile(package) as archive:
                executable = archive.read("bearings-windows.exe")
            self.assertEqual(executable, b"Synthetic PE fixture: " + arch.encode())
            self.assertEqual(asset["exe_size"], len(executable))
            self.assertEqual(asset["exe_sha256"], hashlib.sha256(executable).hexdigest())
        with ZipFile(output / "bearings-windows-source.zip") as archive:
            self.assertIn("self_update.go", archive.namelist())
            metadata = archive.read("SOURCE.txt")
            self.assertIn(b"main.releasePublicKey=", metadata)
            self.assertNotIn(base64.b64encode(self.seed), metadata)
        for line in (output / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split()
            self.assertEqual(expected, hashlib.sha256((output / name).read_bytes()).hexdigest())

    def test_previous_release_prevents_clock_rollback_and_sequence_reuse(self):
        previous = self.build(release_sequence=101) / "update.json"
        with patch.object(builder.time, "time", return_value=90):
            output = self.build("next", previous_manifest=previous)
        release = json.loads(base64.b64decode(json.loads((output / "update.json").read_bytes())["payload"]))
        self.assertEqual(release["sequence"], 102)
        with self.assertRaisesRegex(ValueError, "must increase"):
            self.build("replay", previous_manifest=previous, release_sequence=101)
        self.assertFalse((self.root / "replay").exists())

    def test_replaced_private_key_cannot_publish_over_an_existing_release(self):
        previous = self.build(release_sequence=101) / "update.json"
        self.key.write_bytes(base64.b64encode(bytes(reversed(self.seed))))
        with self.assertRaises(InvalidSignature):
            self.build("wrong-key", previous_manifest=previous)
        self.assertFalse((self.root / "wrong-key").exists())

    def test_signing_key_permissions_and_symlinks_are_rejected(self):
        self.key.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode 0600"):
            self.build()
        self.key.chmod(0o600)
        link = self.root / "link"
        link.symlink_to(self.key)
        self.key = link
        with self.assertRaises(OSError):
            self.build()
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main()
