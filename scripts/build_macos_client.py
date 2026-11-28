#!/usr/bin/env python3
"""Build macOS app archives and sign a manifest for updates from the same Bearings server."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import platform
import re
import shutil
import tempfile
import subprocess
import time


from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if __package__:
    from .build_windows_client import archive, build_server, command
else:
    from build_windows_client import archive, build_server, command

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "clients/linux"
ARCHITECTURES = {"arm64": "Apple Silicon", "amd64": "Intel"}
SCHEMA = "bearings.macos-release.v2"
LEGACY_SCHEMA = "bearings.macos-release.v1"
LOGO = ROOT / "portal/static/portal/brand/bearings-mark.webp"
ENVELOPE_SCHEMA = "bearings.macos-release-envelope.v2"
LEGACY_ENVELOPE = "bearings.macos-release-envelope.v1"


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
        envelope["schema"] not in {ENVELOPE_SCHEMA, LEGACY_ENVELOPE}
        or record["schema"] not in {SCHEMA, LEGACY_SCHEMA}
        or record["origin"] != server
        or type(record["sequence"]) is not int
        or not 1 <= record["sequence"] < (1 << 63) - 1
    ):
        raise ValueError("Previous macOS release does not match the publisher")
    return max(sequence, record["sequence"] + 1)


def make_icon(work, output):
    iconset = work / "Bearings.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            filename = f"icon_{size}x{size}" + ("@2x.png" if scale == 2 else ".png")
            subprocess.run(
                [
                    "/usr/bin/sips",
                    "-s",
                    "format",
                    "png",
                    "-z",
                    str(size * scale),
                    str(size * scale),
                    LOGO,
                    "--out",
                    iconset / filename,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
    subprocess.run(["/usr/bin/iconutil", "-c", "icns", "-o", output, iconset], check=True)


def notarize(app, output, identity, profile):
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--timestamp", "--options", "runtime", "--sign", identity, app],
        check=True,
    )
    args = ["/usr/bin/ditto", "-c", "-k", "--keepParent", app, output]
    subprocess.run(args, check=True)
    result = command(
        "/usr/bin/xcrun",
        "notarytool",
        "submit",
        str(output),
        "--keychain-profile",
        profile,
        "--wait",
        "--output-format",
        "json",
    )
    record = json.loads(result)
    if record.get("status") != "Accepted":
        raise ValueError(f"Apple notarization was not accepted for submission {record.get('id', 'unknown')}")
    subprocess.run(["/usr/bin/xcrun", "stapler", "staple", app], check=True)
    subprocess.run(["/usr/bin/xcrun", "stapler", "validate", app], check=True)
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", app], check=True)
    subprocess.run(["/usr/sbin/spctl", "--assess", "--type", "execute", app], check=True)
    output.unlink()
    subprocess.run(args, check=True)


def build(compiler, output, server, signing_key, *, identity, team, profile, previous_manifest=None):
    if platform.system() != "Darwin":
        raise ValueError(
            "Build the public macOS release on a Mac with Developer ID Application and notarytool"
        )
    if not re.fullmatch(r"[A-Z0-9]{10}", team) or not identity.startswith("Developer ID Application:"):
        raise ValueError("Supply a Developer ID Application identity and its ten-character Apple team ID")
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
        f"-X main.macReleaseKey={public} -X main.macSequence={sequence} -X main.macAppleTeam={team}"
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
    if output.exists():
        raise ValueError("Use a new output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        work = Path(temporary)
        staging = work / "release"
        staging.mkdir()
        icon = work / "Bearings.icns"
        make_icon(work, icon)
        assets = {}
        for arch in ARCHITECTURES:
            app = work / arch / "Bearings.app"
            contents = app / "Contents"
            binary = contents / "MacOS/bearings-macos"
            binary.parent.mkdir(parents=True)
            resources = contents / "Resources"
            resources.mkdir()
            shutil.copyfile(icon, resources / icon.name)
            shutil.copyfile(CLIENT / "macos_app.plist", contents / "Info.plist")
            subprocess.run(
                [compiler, "build", "-trimpath", "-buildvcs=false", "-ldflags", flags, "-o", binary, "."],
                cwd=CLIENT,
                env={**env, "GOARCH": arch},
                check=True,
            )
            name = staging / f"bearings-macos-{arch}.zip"
            notarize(app, name, identity, profile)
            verify = command("/usr/bin/codesign", "-dv", "--verbose=4", str(app), stderr=subprocess.STDOUT)
            if f"TeamIdentifier={team}" not in verify.splitlines():
                raise ValueError("Apple signing team does not match the embedded update requirement")
            size = name.stat().st_size
            if not 0 < size <= 32 * 1024 * 1024:
                raise ValueError("macOS distributable archive exceeds its size limit")
            assets[arch] = {"sha256": hashlib.sha256(name.read_bytes()).hexdigest(), "size": size}
        finish_release(compiler, staging, env, source, private, server, sequence, assets)
        staging.rename(output)


def finish_release(compiler, output, env, source, private, server, sequence, assets):
    go_root = Path(command(compiler, "env", "GOROOT", env=env))
    archive(
        output / "bearings-macos-source.zip",
        {
            **source,
            "README.md": (ROOT / "docs/integrations/macos-agent.md").read_bytes(),
            "LICENSE": (ROOT / "LICENSE").read_bytes(),
            "LICENSE-Go": (go_root / "LICENSE").read_bytes(),
            "bearings-mark.webp": LOGO.read_bytes(),
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
    parser.add_argument("--apple-identity", required=True)
    parser.add_argument("--apple-team", required=True)
    parser.add_argument("--notary-profile", required=True)
    args = parser.parse_args()
    build(
        args.go,
        args.output,
        args.server,
        args.signing_key,
        identity=args.apple_identity,
        team=args.apple_team,
        profile=args.notary_profile,
        previous_manifest=args.previous_manifest,
    )
