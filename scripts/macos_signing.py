#!/usr/bin/env python3
"""Transport notarized Bearings releases between Ubuntu and one approved Mac."""

import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile

ARTIFACTS = {
    "bearings-macos-arm64.zip": 32 << 20,
    "bearings-macos-amd64.zip": 32 << 20,
    "bearings-macos-source.zip": 32 << 20,
    "update.json": 65536,
}
MAX_TRANSFER = sum(ARTIFACTS.values()) + 16384
REVISION = re.compile(r"[0-9a-f]{40}")
DESTINATION = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*@[A-Za-z0-9][A-Za-z0-9.-]*")
REPOSITORY = "https://github.com/rommelfs/bearings.git"
REQUEST_LIMIT = 98304


def unpack(archive, output):
    with ZipFile(archive) as transfer:
        entries = transfer.infolist()
        if len(entries) != len(ARTIFACTS) or {e.filename for e in entries} != ARTIFACTS.keys():
            raise ValueError("Unexpected files in macOS release transfer")
        output.mkdir()
        for entry in entries:
            limit = ARTIFACTS[entry.filename]
            if not 0 < entry.file_size <= limit:
                raise ValueError("Invalid size in macOS release transfer")
            with transfer.open(entry) as source, (output / entry.filename).open("xb") as target:
                body = source.read(limit + 1)
                if len(body) != entry.file_size:
                    raise ValueError("Incorrect size in macOS release transfer")
                target.write(body)


def receive(destination, identity, known_hosts, request, output):
    if not DESTINATION.fullmatch(destination):
        raise ValueError("Configure an SSH signing destination in user@host form")
    args = [
        "/usr/bin/ssh",
        "-F",
        "/dev/null",
        "-T",
        "-i",
        identity,
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ClearAllForwardings=yes",
        "--",
        destination,
        "bearings-macos-release",
    ]
    with tempfile.TemporaryFile() as input_file, tempfile.TemporaryFile() as archive:
        input_file.write(json.dumps(request).encode())
        input_file.seek(0)
        with subprocess.Popen(args, stdin=input_file, stdout=subprocess.PIPE) as process:
            deadline = time.monotonic() + 1800
            total = 0
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.select(max(0, deadline - time.monotonic())):
                        chunk = os.read(process.stdout.fileno(), 1 << 20)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_TRANSFER or time.monotonic() >= deadline:
                            raise ValueError("Mac signing exceeded the response limit or deadline")
                        archive.write(chunk)
                    else:
                        raise TimeoutError("Mac signing did not finish within the deadline")
                if process.wait(timeout=max(0, deadline - time.monotonic())):
                    raise ValueError("The Mac signing station did not return a release")
            finally:
                if process.poll() is None:
                    process.kill()
        archive.seek(0)
        unpack(archive, output)


def serve(config, request, sink):
    revision = request.get("revision")
    origin = config["origin"]
    if (
        set(request) != {"revision", "origin", "previous"}
        or not isinstance(revision, str)
        or not REVISION.fullmatch(revision)
        or request["origin"] != origin
    ):
        raise ValueError("Invalid signing request")
    previous = base64.b64decode(request["previous"], validate=True)
    if len(previous) > ARTIFACTS["update.json"]:
        raise ValueError("Previous macOS release manifest is too large")
    checkout = Path(config["checkout"])
    ref = config["approved_ref"]
    if not ref.startswith(("refs/heads/", "refs/tags/")):
        raise ValueError("Configure one reviewed branch or tag")
    subprocess.run(["git", "check-ref-format", ref], check=True, stdout=sys.stderr)

    def git(*args, capture=False):
        return subprocess.run(
            ["git", "-C", checkout, *args],
            text=True,
            check=True,
            stdout=subprocess.PIPE if capture else sys.stderr,
        ).stdout

    # Lock the dedicated checkout, including its tool environment and keychain use.
    with Path(config["lock"]).open("a") as lock, tempfile.TemporaryDirectory() as temporary:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if git("status", "--porcelain", capture=True).strip():
            raise ValueError("The dedicated signing checkout must be clean")
        git("fetch", "--no-tags", REPOSITORY, ref)
        git("merge-base", "--is-ancestor", revision, "FETCH_HEAD")
        git("switch", "--detach", revision)
        work = Path(temporary)
        release = work / "release"
        args = [
            config["uv"],
            "run",
            "--frozen",
            "python",
            "scripts/build_macos_client.py",
            "--go",
            config["go"],
            "--server",
            origin,
            "--signing-key",
            config["release_key"],
            "--apple-identity",
            config["apple_identity"],
            "--apple-team",
            config["apple_team"],
            "--notary-profile",
            config["notary_profile"],
            "--output",
            release,
        ]
        if previous:
            manifest = work / "previous.json"
            manifest.write_bytes(previous)
            args += ["--previous-manifest", manifest]
        subprocess.run(args, cwd=checkout, stdin=subprocess.DEVNULL, stdout=sys.stderr, check=True)
        with ZipFile(sink, "w") as transfer:
            for name, limit in ARTIFACTS.items():
                artifact = release / name
                if not 0 < artifact.stat().st_size <= limit:
                    raise ValueError("Mac signing produced a release outside the transfer limits")
                transfer.write(artifact, name)


def read_signer_config(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as config:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_size > 16384
        ):
            raise ValueError("The Mac signer configuration must be a private, owned regular file")
        return json.loads(config.read(16385))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    client = commands.add_parser("fetch")
    client.add_argument("--destination", required=True)
    client.add_argument("--identity", required=True, type=Path)
    client.add_argument("--known-hosts", required=True, type=Path)
    client.add_argument("--revision", required=True)
    client.add_argument("--origin", required=True)
    client.add_argument("--previous", type=Path)
    client.add_argument("--output", required=True, type=Path)
    signer = commands.add_parser("serve")
    signer.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "serve":
        raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            raise ValueError("Signing request too large")
        serve(read_signer_config(args.config), json.loads(raw), sys.stdout.buffer)
    else:
        previous = b""
        if args.previous:
            with args.previous.open("rb") as stream:
                previous = stream.read(ARTIFACTS["update.json"] + 1)
            if len(previous) > ARTIFACTS["update.json"]:
                raise ValueError("Previous macOS release manifest is too large")
        receive(
            args.destination,
            args.identity,
            args.known_hosts,
            {
                "revision": args.revision,
                "origin": args.origin,
                "previous": base64.b64encode(previous).decode(),
            },
            args.output,
        )


if __name__ == "__main__":
    main()
