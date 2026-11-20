#!/usr/bin/env python3
"""Run management as the service user via systemd's own protected EnvironmentFile parser."""

import os
from pathlib import Path
import stat
import sys


def main():
    if os.geteuid() != 0 or len(sys.argv) < 2:
        raise SystemExit("Use sudo /opt/bearings/deploy/ubuntu24/manage.py COMMAND [ARGS]")
    path = Path("/etc/bearings/bearings.env")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as file:
        info = os.fstat(file.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o077
            or info.st_size > 262144
        ):
            raise SystemExit("Environment file must be root-owned, bounded and mode 0600")
        lines = [line.strip() for line in file if line.startswith("DJANGO_SETTINGS_MODULE=")]
        if lines != ["DJANGO_SETTINGS_MODULE=config.production"]:
            raise SystemExit("Use the production settings profile")
    root = Path(__file__).resolve().parents[2]
    command = [
        "/usr/bin/systemd-run",
        "--quiet",
        "--wait",
        "--collect",
        "--pty" if sys.stdin.isatty() else "--pipe",
        "--property=User=bearings",
        "--property=Group=www-data",
        f"--property=WorkingDirectory={root}",
        f"--property=EnvironmentFile={path}",
        "--property=NoNewPrivileges=yes",
        "--",
        str(root / ".venv/bin/python"),
        str(root / "manage.py"),
        *sys.argv[1:],
    ]
    os.execve(
        command[0],
        command,
        {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "TERM": os.getenv("TERM", "dumb")},
    )


if __name__ == "__main__":
    main()
