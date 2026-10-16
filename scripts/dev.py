#!/usr/bin/env python3
"""Docker + Python standard-library starter. No uv/local Python packages required."""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/dev-stack"
STATE = LOCAL / "active.json"
DOCKER_NOT_FOUND = (
    "Docker command not found. Install and open Docker Desktop on macOS/Windows "
    "(https://www.docker.com/products/docker-desktop/), then reopen your terminal. "
    "On Linux install Docker Engine and the Compose plugin. "
    "If Docker is installed, ensure its CLI is on PATH."
)


def environment():
    result = dict(os.environ)
    if ROOT.is_relative_to(Path("/workspace")) and not result.get("DOCKER_CONFIG"):
        directory = Path("/workspace/.cache/docker")
        directory.mkdir(parents=True, exist_ok=True)
        result["DOCKER_CONFIG"] = str(directory)
    return result


def compose(mode, project):
    result = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.dev.yaml")]
    if mode == "bundled":
        result += ["-f", str(ROOT / "compose.netbox.yaml")]
    return result


def run(args, **kwargs):
    try:
        return subprocess.run(args, cwd=ROOT, env=environment(), check=True, **kwargs)
    except FileNotFoundError:
        raise SystemExit(DOCKER_NOT_FOUND) from None


def check_docker():
    if shutil.which("docker") is None:
        raise SystemExit(DOCKER_NOT_FOUND)
    for command, message in [
        (
            ["docker", "compose", "version"],
            "Docker Compose is unavailable. Install Compose v2.24+ (included in Docker Desktop).",
        ),
        (
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            "Docker Engine is unreachable. Open Docker Desktop and wait until it is running, or start your Linux Docker service. Check your Docker context and socket permissions.",
        ),
    ]:
        try:
            run(command, capture_output=True, text=True, timeout=15)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise SystemExit(message) from None


def private_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(value)


def configure(args):
    try:
        parsed = urlsplit(args.url)
        port = parsed.port
    except ValueError:
        raise SystemExit("Enter a valid HTTPS NetBox base URL") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise SystemExit("Use an approved HTTPS URL without credentials, query or fragment")
    if args.tenant_id is not None and args.tenant_id < 1:
        raise SystemExit("Tenant ID must be positive")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    authority = host + (":" + str(port) if port and port != 443 else "")
    url = parsed._replace(scheme="https", netloc=authority).geturl().rstrip("/")
    identity = hashlib.sha256(
        json.dumps([url, args.tenant_id, args.dedicated, args.access_mode]).encode()
    ).hexdigest()[:12]
    token = (
        Path(args.token_file).read_text().strip()
        if args.token_file
        else getpass.getpass("NetBox API token (hidden, without Authorization prefix): ").strip()
    )
    if not token or "\n" in token or "\r" in token:
        raise SystemExit("A nonempty single-line token is required")
    if args.ca_file and not Path(args.ca_file).is_file():
        raise SystemExit("CA certificate file does not exist")
    directory = LOCAL / "external"
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    config = {
        "name": "external-" + identity,
        "organization_slug": "external-" + identity,
        "organization_name": "External NetBox development workspace",
        "base_url": url,
        "token_env_var": "NETBOX_EXTERNAL_" + identity.upper() + "_TOKEN",
        "auth_scheme": args.auth_scheme,
        "tenant_id": args.tenant_id,
        "dedicated": args.dedicated,
        "access_mode": args.access_mode,
        "allow_private": args.allow_private,
        "site_id": args.site_id,
        "role_id": args.role_id,
        "device_type_id": args.device_type_id,
    }
    private_file(directory / "connection.json", json.dumps(config, indent=2) + "\n")
    private_file(directory / "token", token + "\n")
    ca = directory / "ca.crt"
    if args.ca_file:
        shutil.copyfile(args.ca_file, ca)
        ca.chmod(0o600)
    elif ca.exists():
        ca.unlink()
    print(
        "External configuration saved locally (read-only by default). Run: python3 scripts/dev.py up --external"
    )


def active():
    return (
        json.loads(STATE.read_text())
        if STATE.exists()
        else {"mode": "bundled", "project": os.getenv("BEARINGS_DEV_PROJECT", "bearings-dev")}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    up = commands.add_parser("up", help="Start the bundled lab, or use --external for an existing NetBox")
    up.add_argument("--external", action="store_true")
    up.add_argument("--no-build", action="store_true")
    up.add_argument("--timeout", type=int, default=600)
    connect = commands.add_parser("configure", help="Configure an external NetBox without logging its token")
    connect.add_argument("--url", required=True)
    scope = connect.add_mutually_exclusive_group(required=True)
    scope.add_argument("--tenant-id", type=int)
    scope.add_argument(
        "--dedicated",
        action="store_true",
        help="Explicitly approve this organization to read the whole instance",
    )
    connect.add_argument("--access-mode", choices=["read_only", "read_write"], default="read_only")
    connect.add_argument("--auth-scheme", choices=["Bearer", "Token"], default="Bearer")
    connect.add_argument("--allow-private", action="store_true")
    connect.add_argument("--token-file", help="Read token from a secure file instead of prompting")
    connect.add_argument("--ca-file", help="Additional approved CA certificate for the external instance")
    for name in ["site-id", "role-id", "device-type-id"]:
        connect.add_argument("--" + name, type=int)
    for name in ["down", "status", "logs", "credentials", "trust", "query", "smoke"]:
        commands.add_parser(name)
    manage = commands.add_parser(
        "manage", help="Run a Bearings management command with stack credentials/trust loaded"
    )
    manage.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action != "configure":
        check_docker()
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / "external").mkdir(exist_ok=True)
    if args.action == "configure":
        configure(args)
        return
    if args.action == "up":
        mode = "external" if args.external else "bundled"
        project = os.getenv("BEARINGS_DEV_PROJECT", "bearings-dev")
        if mode == "external":
            path = LOCAL / "external/connection.json"
            if not path.exists():
                raise SystemExit("Run scripts/dev.py configure first; no external token or scope is guessed")
            config = json.loads(path.read_text())
            project += "-external-" + config["name"].removeprefix("external-")
        target = {"mode": mode, "project": project}
        if STATE.exists() and active() != target:
            old = active()
            run(compose(old["mode"], old["project"]) + ["down"])
            print("Previous lab stopped; its volumes and data were retained.")
        private_file(STATE, json.dumps(target))
        options = ["up", "-d", "--wait", "--wait-timeout", str(args.timeout)]
        if not args.no_build:
            options.append("--build")
        run(compose(mode, project) + options)
        if mode == "bundled":
            run(compose(mode, project) + ["exec", "-T", "netbox-tls", "nginx", "-s", "reload"])
        print(
            "Bearings development stack started. Check connection health in the workspace; external availability is independent."
        )
        print("Use 'python3 scripts/dev.py credentials' to display the generated local login password.")
        return
    state = active()
    base = compose(state["mode"], state["project"])
    if args.action == "down":
        run(base + ["down"])
        print("Containers stopped; persistent volumes and data retained.")
    elif args.action == "status":
        run(base + ["ps", "-a"])
    elif args.action == "logs":
        run(base + ["logs", "--tail", "100", "--follow"])
    elif args.action in {"query", "smoke", "manage"}:
        if args.action == "manage":
            import sys

            option = [] if sys.stdin.isatty() else ["-T"]
            run(
                base
                + [
                    "exec",
                    *option,
                    "web",
                    "/app/.venv/bin/python",
                    "docker/dev/entrypoint.py",
                    "manage",
                    *args.arguments,
                ]
            )
        elif args.action == "query":
            run(
                base
                + [
                    "exec",
                    "-T",
                    "web",
                    "/app/.venv/bin/python",
                    "docker/dev/entrypoint.py",
                    "manage",
                    "query_netbox",
                    "--all",
                    "--object-type",
                    "devices",
                    "--object-type",
                    "virtual-machines",
                    "--object-type",
                    "ip-addresses",
                    "--object-type",
                    "prefixes",
                ]
            )
        else:
            run(base + ["exec", "-T", "web", "/app/.venv/bin/python", "docker/dev/entrypoint.py", "smoke"])
    elif args.action == "credentials":
        print("LOCAL DEVELOPMENT ONLY: Bearings users platform-admin, company-admin, circl-analyst.")
        if state["mode"] == "bundled":
            print(
                "Bundled NetBox user: netbox-admin. All new demo users share this generated local password:"
            )
        else:
            print(
                "External NetBox accounts are unchanged. New Bearings demo users share this generated local password:"
            )
        run(base + ["exec", "-T", "web", "cat", "/run/bearings/secrets/demo_password"])
    elif args.action == "trust":
        container = run(base + ["ps", "-a", "-q", "dev-init"], capture_output=True, text=True).stdout.strip()
        if not container:
            raise SystemExit("Start the lab first")
        destination = LOCAL / "netbox-ca.crt"
        run(["docker", "cp", container + ":/state/trust/netbox-ca.crt", str(destination)])
        print("Public development CA exported to " + str(destination) + ". No private key was exported.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
