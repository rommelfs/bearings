"""Synthetic signing transfer and fixed release input boundaries."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.macos_signing import ARTIFACTS, serve, unpack


class MacSigningTests(unittest.TestCase):
    def test_transfer_admits_only_exact_release_filenames(self):
        def package(extra=None):
            payload = BytesIO()
            with ZipFile(payload, "w") as bundle:
                for name in ARTIFACTS:
                    bundle.writestr(name, name)
                if extra is not None:
                    bundle.writestr(extra, b"unexpected")
            payload.seek(0)
            return payload

        with TemporaryDirectory() as directory:
            root = Path(directory)
            unpack(package(), root / "release")
            self.assertEqual({p.name for p in (root / "release").iterdir()}, ARTIFACTS.keys())
            with self.assertRaises(ValueError):
                unpack(package("../unexpected"), root / "other")
            self.assertFalse((root / "unexpected").exists())

    def test_signer_rejects_different_origin_and_git_options(self):
        origin = "https://bearings.example.invalid"
        for revision, requested in (("--help", origin), ("1" * 40, "https://elsewhere.example.invalid")):
            with self.assertRaises(ValueError):
                serve(
                    {"origin": origin}, {"revision": revision, "origin": requested, "previous": ""}, BytesIO()
                )
