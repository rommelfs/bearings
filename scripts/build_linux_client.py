#!/usr/bin/env python3
"""Build the dependency-free Linux reference client from reviewed local source; no install or release signing."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/linux-client")
    args = parser.parse_args()
    compiler = shutil.which(args.go)
    if not compiler:
        parser.error("Install a supported Go compiler (1.24+) or supply --go /path/to/go")
    check = subprocess.run([compiler, "version"], capture_output=True, text=True)
    if check.returncode or not check.stdout.startswith("go version go"):
        parser.error("The selected program is not the Go language compiler; supply --go /path/to/go")
    revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True
    ).strip():
        revision += "-dirty"
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for arch in ("amd64", "arm64"):
        output = args.output / f"bearings-linux-{arch}"
        env = {
            **os.environ,
            "GOOS": "linux",
            "GOARCH": arch,
            "CGO_ENABLED": "0",
            "GOTOOLCHAIN": "local",
            "GOPROXY": "off",
            "GOSUMDB": "off",
        }
        subprocess.run(
            [
                compiler,
                "build",
                "-trimpath",
                "-buildvcs=false",
                "-ldflags",
                f"-s -w -X main.version={revision}",
                "-o",
                str(output.resolve()),
                ".",
            ],
            cwd=ROOT / "clients/linux",
            env=env,
            check=True,
        )
        records.append(f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}")
    (args.output / "SHA256SUMS").write_text("\n".join(records) + "\n")
    print(
        f"Built reviewed-source reference artifacts in {args.output}; checksums are not release signatures."
    )


if __name__ == "__main__":
    main()
