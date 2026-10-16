"""Build in a proxy-only cloud sandbox without embedding proxy settings or CA material."""

import os
import socket
import subprocess
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
    config_path = "/workspace/.cache/docker"
    Path(config_path).mkdir(parents=True, exist_ok=True)
    runenv = dict(os.environ, DOCKER_CONFIG=config_path)
    return subprocess.call(args, cwd=Path(__file__).resolve().parents[1], env=runenv)


if __name__ == "__main__":
    raise SystemExit(main())
