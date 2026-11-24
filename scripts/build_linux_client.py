#!/usr/bin/env python3
"""Build the dependency-free Linux reference client from reviewed local source; no install or release signing."""

import argparse
import hashlib
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

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
    # Private/ignored local configuration (for example .env) is never a source
    # artifact. Compile only Go files whose corresponding source can be bundled.
    tracked = [
        ROOT / os.fsdecode(name)
        for name in subprocess.check_output(["git", "ls-files", "-z", "--", "clients/linux"], cwd=ROOT).split(
            b"\0"
        )
        if name
    ]
    if set((ROOT / "clients/linux").glob("*.go")) - set(tracked):
        parser.error("Review and add every Go source file to version control before building")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.output.resolve() == (ROOT / ".local/linux-client").resolve():
        args.output.chmod(0o755)
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
        output.chmod(0o755)
        records.append(f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}")
    for source, name in [
        (ROOT / "clients/linux/install.py", "install.py"),
        (ROOT / "clients/linux/systemd/bearings-linux.service", "bearings-linux.service"),
        (ROOT / "clients/linux/README.md", "README.md"),
        (ROOT / "LICENSE", "LICENSE"),
    ]:
        target = args.output / name
        shutil.copyfile(source, target)
        target.chmod(0o644)
        records.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {name}")
    archive = args.output / "bearings-linux-source.tar.gz"
    with (
        archive.open("wb") as output,
        gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as zipped,
    ):
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            client_source = ROOT / "clients/linux"
            for path in sorted(tracked):
                if path.is_symlink():
                    raise SystemExit("Refusing symlink in client source bundle")
                if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                info = tar.gettarinfo(path, arcname="source/" + str(path.relative_to(client_source)))
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
            tar.add(ROOT / "LICENSE", arcname="LICENSE", recursive=False)
    archive.chmod(0o644)
    records.append(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}")
    source_note = args.output / "SOURCE.txt"
    source_note.write_text(
        "Source: https://github.com/rommelfs/bearings\n"
        f"Revision: {revision}\n"
        "Corresponding client/installer source: bearings-linux-source.tar.gz\n"
        "Build client: unpack, cd source, then CGO_ENABLED=0 go build -o bearings-linux .\n"
        "Review the local source/artifacts before sudo installation; checksums are not release signatures.\n"
    )
    source_note.chmod(0o644)
    records.append(f"{hashlib.sha256(source_note.read_bytes()).hexdigest()}  SOURCE.txt")
    (args.output / "SHA256SUMS").write_text("\n".join(records) + "\n")
    (args.output / "SHA256SUMS").chmod(0o644)
    print(
        f"Built reviewed-source reference artifacts in {args.output}; checksums are not release signatures."
    )


if __name__ == "__main__":
    main()
