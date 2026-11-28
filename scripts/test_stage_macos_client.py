"""Exercise Linux-side publication without pretending test archives are Apple-notarized."""

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.build_macos_client import CLIENT, ENVELOPE_SCHEMA, LEGACY_SCHEMA, SCHEMA
from scripts.stage_macos_client import stage

ORIGIN = "https://bearings.example.invalid"


class MacOSPublicationTests(unittest.TestCase):
    def test_bearings_icon_uses_standard_icns_png_sizes(self):
        data = (CLIENT / "Bearings.icns").read_bytes()
        self.assertEqual(struct.unpack_from(">4sI", data), (b"icns", len(data)))
        offset = 8
        for kind, pixels in ((b"ic07", 128), (b"ic08", 256)):
            actual, size = struct.unpack_from(">4sI", data, offset)
            self.assertEqual(actual, kind)
            png = data[offset + 8 : offset + size]
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack_from(">II", png, 16), (pixels, pixels))
            offset += size
        self.assertEqual(offset, len(data))

    def test_staging_requires_authenticated_new_format_and_untampered_archives(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = Ed25519PrivateKey.generate()
            seed = root / "key"
            seed.write_bytes(base64.b64encode(key.private_bytes_raw()))
            seed.chmod(0o600)
            source = root / "source"
            source.mkdir()
            body = BytesIO()
            with ZipFile(body, "w") as bundle:
                for part in (
                    "Info.plist",
                    "MacOS/bearings-macos",
                    "Resources/Bearings.icns",
                    "_CodeSignature/CodeResources",
                ):
                    bundle.writestr("Bearings.app/Contents/" + part, "synthetic")
            raw = body.getvalue()
            architectures = ("arm64", "amd64")
            for arch in architectures:
                (source / f"bearings-macos-{arch}.zip").write_bytes(raw)
            (source / "bearings-macos-source.zip").write_bytes(b"source")
            manifest = source / "update.json"

            def write_manifest(schema, sequence):
                payload = json.dumps(
                    {
                        "schema": schema,
                        "origin": ORIGIN,
                        "sequence": sequence,
                        "assets": {
                            arch: {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
                            for arch in architectures
                        },
                    }
                ).encode()
                manifest.write_text(
                    json.dumps(
                        {
                            "schema": ENVELOPE_SCHEMA,
                            "payload": base64.b64encode(payload).decode(),
                            "signature": base64.b64encode(key.sign(payload)).decode(),
                        }
                    )
                )

            write_manifest(LEGACY_SCHEMA, 4)
            with self.assertRaises(ValueError):
                stage(source, root / "wrong", ORIGIN, seed)
            write_manifest(SCHEMA, 5)
            stage(source, root / "reviewed", ORIGIN, seed)
            previous = root / "reviewed/update.json"
            write_manifest(SCHEMA, 3)
            with self.assertRaises(ValueError):
                stage(source, root / "older", ORIGIN, seed, previous)
            write_manifest(SCHEMA, 6)
            (source / "bearings-macos-amd64.zip").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                stage(source, root / "tampered", ORIGIN, seed, previous)
