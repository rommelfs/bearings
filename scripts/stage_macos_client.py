#!/usr/bin/env python3
"""Verify and stage the notarized app release from the trusted Bearings signing station."""

import argparse
import base64
import hashlib
import json
from io import BytesIO
import os
from pathlib import Path
import stat
from zipfile import ZipFile

if __package__:
    from .build_macos_client import ARCHITECTURES, ENVELOPE_SCHEMA, SCHEMA, next_sequence, read_key
else:
    from build_macos_client import ARCHITECTURES, ENVELOPE_SCHEMA, SCHEMA, next_sequence, read_key

MAX_ARCHIVE = 32 * 1024 * 1024


def read_artifact(directory, name, limit):
    fd = os.open(directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode) or mode & 0o022:
            raise ValueError(f"Expected a protected regular release file: {name}")
        body = file.read(limit + 1)
    if not 0 < len(body) <= limit:
        raise ValueError(f"Invalid macOS release file size: {name}")
    return body


def stage(source, output, server, key, previous=None):
    private = read_key(key)
    manifest = read_artifact(source, "update.json", 65536)
    envelope = json.loads(manifest)
    payload = base64.b64decode(envelope["payload"], validate=True)
    private.public_key().verify(base64.b64decode(envelope["signature"], validate=True), payload)
    record = json.loads(payload)
    sequence = record["sequence"]
    if (
        envelope["schema"] != ENVELOPE_SCHEMA
        or record["schema"] != SCHEMA
        or record["origin"] != server
        or type(sequence) is not int
        or not 1 <= sequence < (1 << 63) - 1
        or set(record["assets"]) != set(ARCHITECTURES)
    ):
        raise ValueError("The notarized release has the wrong format, origin or sequence")
    if previous is not None and manifest != previous.read_bytes():
        with previous.open("rb") as file:
            prior = json.loads(file.read(65537))
        prior_sequence = json.loads(base64.b64decode(prior["payload"], validate=True))["sequence"]
        # Authenticate the previous release and its origin, including the old unsigned-app format.
        next_sequence(private, previous, server)
        if sequence <= prior_sequence:
            raise ValueError("The macOS release must be newer than the published release")
    files = {"update.json": manifest}
    for arch, expected in record["assets"].items():
        name = f"bearings-macos-{arch}.zip"
        body = read_artifact(source, name, MAX_ARCHIVE)
        if expected != {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}:
            raise ValueError(f"Notarized archive does not match its signed manifest: {name}")
        with ZipFile(BytesIO(body)) as bundle:
            required = {
                "Bearings.app/Contents/" + part
                for part in (
                    "Info.plist",
                    "MacOS/bearings-macos",
                    "Resources/Bearings.icns",
                    "_CodeSignature/CodeResources",
                )
            }
            if not required <= set(bundle.namelist()):
                raise ValueError(f"Missing signed app components or icon: {name}")
        files[name] = body
    files["bearings-macos-source.zip"] = read_artifact(source, "bearings-macos-source.zip", MAX_ARCHIVE)
    output.mkdir()
    rows = []
    for name, body in files.items():
        (output / name).write_bytes(body)
        rows.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
    (output / "SHA256SUMS").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--server", required=True)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--previous-manifest", type=Path)
    args = parser.parse_args()
    stage(args.source, args.output, args.server, args.signing_key, args.previous_manifest)
