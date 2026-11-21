#!/usr/bin/env python3
"""Disposable root installer acceptance. No host accounts/systemd, operational services or external network."""

import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python38", action="store_true", help="Exercise real Python 3.8 in a disposable image"
    )
    args = parser.parse_args()
    image = "bearings-development"
    if args.python38:
        image = "bearings-installer-python38"
        subprocess.run(
            ["docker", "build", "-f", "docker/client-installer-python38.Dockerfile", "-t", image, "."],
            cwd=ROOT,
            check=True,
            timeout=180,
        )
    binary = ROOT / ".local/linux-client/bearings-linux-amd64"
    if not binary.is_file():
        raise SystemExit("Build the Linux client first")
    for automatic in ("0", "1"):
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0:0",
                "--hostname",
                "synthetic-bearings-installer",
                "--memory",
                "512m",
                "--cpus",
                "2",
                "--pids-limit",
                "128",
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--cap-add",
                "SETUID",
                "--cap-add",
                "SETGID",
                "--cap-add",
                "DAC_OVERRIDE",
                "--cap-add",
                "FOWNER",
                "--cap-add",
                "KILL",
                "-e",
                "BEARINGS_INSTALLER_TEST=1",
                "-e",
                "BEARINGS_INSTALLER_FLEET=" + automatic,
                "-e",
                "BEARINGS_INSTALLER_PYTHON="
                + ("/usr/local/bin/python3.8" if args.python38 else "/app/.venv/bin/python"),
                "-v",
                f"{ROOT / 'clients/linux'}:/test-source:ro",
                "-v",
                f"{binary}:/test-client:ro",
                "--entrypoint",
                "/app/.venv/bin/python",
                image,
                "/test-source/test_installer_container.py",
            ],
            check=True,
            timeout=180,
        )


if __name__ == "__main__":
    main()
