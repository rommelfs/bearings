#!/usr/bin/env python3
"""Build standalone Windows client ZIPs and their corresponding source from a reviewed checkout."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import base64
import json
import stat
import time
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "clients/windows"
ARCHITECTURES = {"amd64": "x64", "arm64": "arm64", "386": "x86"}


def archive(path, entries):
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for name, content in sorted(entries.items()):
            entry = ZipInfo(name)
            entry.external_attr = 0o644 << 16
            output.writestr(entry, content, compress_type=ZIP_DEFLATED, compresslevel=9)


def command(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def build_server(value):
    if not re.fullmatch(r"https://(?:[A-Za-z0-9.-]+|\[[A-Fa-f0-9:.]+\])(?::[0-9]{1,5})?/?", value):
        raise ValueError("Windows client server must be an ASCII HTTPS origin")
    parsed = urlsplit(value)
    port = parsed.port
    if port == 0:
        raise ValueError("Invalid HTTPS port")
    return "https://" + parsed.netloc.lower()


def build(compiler, output, server="", *, signing_key=None, release_sequence=None, previous_manifest=None):
    server = build_server(server) if server else ""
    version = command(compiler, "version")
    if not version.startswith("go version go"):
        raise ValueError("Supply the Go language compiler with --go")
    tracked = command("git", "ls-files", "--", "clients/windows", cwd=ROOT).splitlines()
    module = {
        Path(name).name: (ROOT / name).read_bytes()
        for name in tracked
        if name.endswith((".go", ".ps1", "/go.mod", "/go.sum"))
    }
    if (set(CLIENT.glob("*.go")) | set(CLIENT.glob("*.ps1"))) - {CLIENT / name for name in module}:
        raise ValueError("Add all reviewed Windows Go source files to version control before building")
    revision = command("git", "rev-parse", "HEAD", cwd=ROOT)
    if command("git", "status", "--porcelain", cwd=ROOT):
        raise ValueError("Build from a clean, reviewed checkout")
    ldflags = f"-s -w -X main.version={revision[:12]}"
    if server:
        ldflags += f" -X main.defaultServer={server}"

    env = {**os.environ, "GOTOOLCHAIN": "local", "CGO_ENABLED": "0", "GOWORK": "off", "GOFLAGS": ""}
    go_root = Path(command(compiler, "env", "GOROOT", env=env))
    private = None
    sequence = 0
    if signing_key is not None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_path = Path(signing_key).absolute()
        if key_path.resolve().is_relative_to(ROOT.resolve()) or not server:
            raise ValueError("Keep the signing key outside Git and supply the approved HTTPS origin")
        fd = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as file:
            info = os.fstat(file.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o077
                or info.st_uid != os.geteuid()
                or info.st_size > 128
            ):
                raise ValueError("Use a publisher-owned private regular signing key with mode 0600")
            seed = base64.b64decode(file.read().strip(), validate=True)
        if len(seed) != 32:
            raise ValueError("Invalid release signing key")
        private = Ed25519PrivateKey.from_private_bytes(seed)
        public = base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")
        sequence = int(time.time()) if release_sequence is None else release_sequence
        if previous_manifest is not None:
            if previous_manifest.stat().st_size > 65536:
                raise ValueError("Previous Windows manifest exceeds limit")
            envelope = json.loads(previous_manifest.read_bytes())
            payload = base64.b64decode(envelope["payload"], validate=True)
            private.public_key().verify(base64.b64decode(envelope["signature"], validate=True), payload)
            previous = json.loads(payload)
            if (
                envelope["schema"] != "bearings.windows-release-envelope.v1"
                or previous["schema"] != "bearings.windows-release.v1"
                or previous["origin"] != server
                or type(previous["sequence"]) is not int
                or previous["sequence"] < 1
            ):
                raise ValueError("Previous Windows release does not match the publisher")
            if release_sequence is None:
                sequence = max(sequence, previous["sequence"] + 1)
            elif sequence <= previous["sequence"]:
                raise ValueError("Release sequence must increase")
        if not 1 <= sequence <= 2**63 - 1:
            raise ValueError("Invalid release sequence")
        ldflags += f" -X main.releasePublicKey={public} -X main.releaseSequence={sequence} -X main.releaseCommit={revision}"
    metadata = {
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "README.md": (CLIENT / "README.md").read_bytes(),
        "SOURCE.txt": (
            f"Source: https://github.com/rommelfs/bearings/tree/{revision}/clients/windows\n"
            f"Commit: {revision}\nCompiler: {version}\nHTTPS origin: {server or 'unconfigured'}\n"
            "Corresponding source: bearings-windows-source.zip (distributed alongside this ZIP).\n"
            f"Build the extracted source for the target Windows GOARCH with CGO_ENABLED=0 "
            f"go build -mod=vendor -trimpath -buildvcs=false -ldflags '{ldflags}' .\n"
            "No Authenticode signature. Signed update metadata is provided for publisher-key builds. SHA256SUMS provides checksums.\n"
        ).encode(),
        "licenses/Go-LICENSE": (go_root / "LICENSE").read_bytes(),
    }

    output = output.resolve()
    if output.exists():
        raise ValueError("Choose a new output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bearings-windows-", dir=output.parent) as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        for name, data in module.items():
            (source / name).write_bytes(data)
        subprocess.run([compiler, "mod", "verify"], cwd=source, env=env, check=True)
        subprocess.run([compiler, "mod", "vendor"], cwd=source, env=env, check=True)
        vendor = {
            str(path.relative_to(source)): path.read_bytes()
            for path in (source / "vendor").rglob("*")
            if path.is_file()
        }
        licenses = {
            "licenses/" + name.removeprefix("vendor/"): data
            for name, data in vendor.items()
            if Path(name).name in {"LICENSE", "PATENTS"}
        }
        artifacts = root / "artifacts"
        artifacts.mkdir()
        archive(
            artifacts / "bearings-windows-source.zip",
            {
                **module,
                **metadata,
                **vendor,
                "scripts/build_windows_client.py": Path(__file__).read_bytes(),
            },
        )
        release_assets = {}
        for arch, label in ARCHITECTURES.items():
            binary = artifacts / f"bearings-windows-{label}.exe"
            subprocess.run(
                [
                    compiler,
                    "build",
                    "-mod=vendor",
                    "-trimpath",
                    "-buildvcs=false",
                    "-ldflags",
                    ldflags,
                    "-o",
                    str(binary),
                    ".",
                ],
                cwd=source,
                env={**env, "GOOS": "windows", "GOARCH": arch, "GO386": "sse2", "GOAMD64": "v1"},
                check=True,
            )
            archive(
                artifacts / f"bearings-windows-{label}.zip",
                {**metadata, **licenses, "bearings-windows.exe": binary.read_bytes()},
            )
            package = artifacts / f"bearings-windows-{label}.zip"
            release_assets[arch] = {
                "name": package.name,
                "size": package.stat().st_size,
                "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                "exe_size": binary.stat().st_size,
                "exe_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            }
        if private is not None:
            payload = json.dumps(
                {
                    "schema": "bearings.windows-release.v1",
                    "origin": server,
                    "version": revision,
                    "sequence": sequence,
                    "assets": release_assets,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            envelope = {
                "schema": "bearings.windows-release-envelope.v1",
                "payload": base64.b64encode(payload).decode("ascii"),
                "signature": base64.b64encode(private.sign(payload)).decode("ascii"),
            }
            (artifacts / "update.json").write_text(
                json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii"
            )
        checksums = [
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            for path in sorted(artifacts.iterdir())
        ]
        (artifacts / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="ascii")
        artifacts.rename(output)
    print(f"Built Windows x64, ARM64 and x86 packages in {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/windows-client")
    parser.add_argument("--server", default="", help="Approved Bearings HTTPS origin embedded in every EXE")
    parser.add_argument(
        "--signing-key", type=Path, help="Private publisher seed outside the repository (base64, mode 0600)"
    )
    parser.add_argument(
        "--release-sequence",
        type=int,
        help="Monotonic release sequence; defaults to build time in UTC seconds",
    )
    parser.add_argument(
        "--previous-manifest", type=Path, help="Verify the preceding release and advance its sequence"
    )
    args = parser.parse_args()
    compiler = shutil.which(args.go)
    if compiler is None:
        parser.error("Supply a Go compiler with --go")
    try:
        build(
            str(Path(compiler).resolve()),
            args.output,
            args.server,
            signing_key=args.signing_key,
            release_sequence=args.release_sequence,
            previous_manifest=args.previous_manifest,
        )
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
