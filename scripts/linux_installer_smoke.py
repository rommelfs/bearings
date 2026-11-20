#!/usr/bin/env python3
"""Disposable root installer acceptance. No host accounts/systemd, operational services or external network."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    binary = ROOT / ".local/linux-client/bearings-linux-amd64"
    if not binary.is_file():
        raise SystemExit("Build the Linux client first")
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
            "-v",
            f"{ROOT / 'clients/linux'}:/test-source:ro",
            "-v",
            f"{binary}:/test-client:ro",
            "--entrypoint",
            "/app/.venv/bin/python",
            "bearings-development",
            "/test-source/test_installer_container.py",
        ],
        check=True,
        timeout=180,
    )


if __name__ == "__main__":
    main()
