"""Build in a proxy-only cloud sandbox without embedding proxy settings or CA material."""

import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main():
    proxy = urlsplit(os.environ["HTTPS_PROXY"])
    addresses = socket.getaddrinfo(proxy.hostname, proxy.port or 80, type=socket.SOCK_STREAM)
    ip = next(a[4][0] for a in addresses if a[0] == socket.AF_INET)
    # Docker's namespace may not have the host's proxy DNS/hosts entry.
    # Built-in proxy args are transient and not part of image history.
    args = [
        "docker",
        "build",
        "--add-host",
        f"{proxy.hostname}:{ip}",
        "--build-arg",
        "HTTPS_PROXY",
        "--build-arg",
        "HTTP_PROXY",
        "--secret",
        "id=cloud-ca,src=" + os.environ["SSL_CERT_FILE"],
        "-t",
        "bearings-development",
        ".",
    ]
    if "--flowintel" in sys.argv:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from scripts.flowintel_source import prepare_source

        source = prepare_source()
        args = args[:-3] + [
            "--build-context",
            "flowintel=" + str(source),
            "--build-context",
            "flowintel-conf=" + str(source / "conf"),
            "-f",
            "docker/flowintel/Dockerfile",
            "-t",
            "bearings-flowintel",
            ".",
        ]
    elif "--rt" in sys.argv:
        args = args[:-3] + ["-f", "docker/rt/Dockerfile", "-t", "bearings-rt", "."]
    config_path = "/workspace/.cache/docker"
    Path(config_path).mkdir(parents=True, exist_ok=True)
    runenv = dict(os.environ, DOCKER_CONFIG=config_path)
    return subprocess.call(args, cwd=Path(__file__).resolve().parents[1], env=runenv)


if __name__ == "__main__":
    raise SystemExit(main())
