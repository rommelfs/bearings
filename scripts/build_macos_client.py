#!/usr/bin/env python3
"""Build macOS app archives and sign a manifest for updates from the same Bearings server."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from build_windows_client import archive, build_server, command

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "clients/linux"
ARCHITECTURES = {"arm64": "Apple Silicon", "amd64": "Intel"}
SCHEMA = "bearings.macos-release.v1"
ENVELOPE_SCHEMA = "bearings.macos-release-envelope.v1"


def read_key(path):
    if path.resolve().is_relative_to(ROOT):
        raise ValueError("Keep the macOS release key outside the repository")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.geteuid()
            or info.st_size > 128
        ):
            raise ValueError("Use a private macOS publisher-owned signing key with mode 0600")
        seed = base64.b64decode(file.read().strip(), validate=True)
    return Ed25519PrivateKey.from_private_bytes(seed)


def next_sequence(private, previous_path, server):
    sequence = int(time.time())
    if previous_path is None:
        return sequence
    with previous_path.open("rb") as file:
        previous = file.read(65537)
    if len(previous) > 65536:
        raise ValueError("Previous macOS manifest exceeds its size limit")
    envelope = json.loads(previous)
    payload = base64.b64decode(envelope["payload"], validate=True)
    private.public_key().verify(base64.b64decode(envelope["signature"], validate=True), payload)
    record = json.loads(payload)
    if (
        envelope["schema"] != ENVELOPE_SCHEMA
        or record["schema"] != SCHEMA
        or record["origin"] != server
        or type(record["sequence"]) is not int
        or not 1 <= record["sequence"] < (1 << 63) - 1
    ):
        raise ValueError("Previous macOS release does not match the publisher")
    return max(sequence, record["sequence"] + 1)


def zip_app(path, executable):
    with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=9) as output:
        for name, body, mode in (
            ("Info.plist", (CLIENT / "macos_app.plist").read_bytes(), 0o644),
            ("MacOS/bearings-macos", executable, 0o755),
        ):
            item = ZipInfo("Bearings.app/Contents/" + name)
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | mode) << 16
            output.writestr(item, body, ZIP_DEFLATED, compresslevel=9)


def build(compiler, output, server, signing_key, previous_manifest=None):
    server = build_server(server)
    if not command(compiler, "version").startswith("go version go"):
        raise ValueError("Supply a Go language compiler")
    if command("git", "status", "--porcelain", cwd=ROOT):
        raise ValueError("Build from a clean, reviewed checkout")
    private = read_key(signing_key)
    sequence = next_sequence(private, previous_manifest, server)
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")
    revision = command("git", "rev-parse", "--short=12", "HEAD", cwd=ROOT)
    flags = (
        f"-s -w -X main.version={revision} -X main.macServer={server} "
        f"-X main.macReleaseKey={public} -X main.macSequence={sequence}"
    )
    tracked = command("git", "ls-files", "--", "clients/linux", cwd=ROOT).splitlines()
    source = {}
    for filename in tracked:
        path = ROOT / filename
        if path.is_symlink():
            raise ValueError("Refusing symlink in client source archive")
        if path.suffix in {".go", ".plist", ".mod"}:
            source["source/" + path.name] = path.read_bytes()
    if set(CLIENT.glob("*.go")) - {CLIENT / Path(name).name for name in source}:
        raise ValueError("Add all reviewed Go files to version control before building")
    env = {
        **os.environ,
        "GOOS": "darwin",
        "CGO_ENABLED": "0",
        "GOTOOLCHAIN": "local",
        "GOWORK": "off",
        "GOFLAGS": "",
        "GOPROXY": "off",
        "GOSUMDB": "off",
    }
    output.mkdir(parents=True, exist_ok=True)
    assets = {}
    for arch in ARCHITECTURES:
        binary = output / f"bearings-macos-{arch}"
        subprocess.run(
            [
                compiler,
                "build",
                "-trimpath",
                "-buildvcs=false",
                "-ldflags",
                flags,
                "-o",
                binary.resolve(),
                ".",
            ],
            cwd=CLIENT,
            env={**env, "GOARCH": arch},
            check=True,
        )
        executable = binary.read_bytes()
        assets[arch] = {"sha256": hashlib.sha256(executable).hexdigest(), "size": len(executable)}
        zip_app(binary.with_suffix(".zip"), executable)
    go_root = Path(command(compiler, "env", "GOROOT", env=env))
    archive(
        output / "bearings-macos-source.zip",
        {
            **source,
            "README.md": (ROOT / "docs/integrations/macos-agent.md").read_bytes(),
            "LICENSE": (ROOT / "LICENSE").read_bytes(),
            "LICENSE-Go": (go_root / "LICENSE").read_bytes(),
            "build_macos_client.py": Path(__file__).read_bytes(),
            "build_windows_client.py": Path(__file__).with_name("build_windows_client.py").read_bytes(),
        },
    )
    payload = json.dumps(
        {"schema": SCHEMA, "origin": server, "sequence": sequence, "assets": assets},
        separators=(",", ":"),
    ).encode()
    (output / "update.json").write_text(
        json.dumps(
            {
                "schema": ENVELOPE_SCHEMA,
                "payload": base64.b64encode(payload).decode("ascii"),
                "signature": base64.b64encode(private.sign(payload)).decode("ascii"),
            },
            separators=(",", ":"),
        )
    )
    records = []
    for path in sorted(output.iterdir()):
        path.chmod(0o644)
        records.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(records) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--server", required=True)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--previous-manifest", type=Path)
    args = parser.parse_args()
    build(args.go, args.output, args.server, args.signing_key, args.previous_manifest)
