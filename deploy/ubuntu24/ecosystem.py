#!/usr/bin/env python3
"""Native, staged extension of an existing Bearings install. No lab provisioning.

Install is resumable for the recorded installation only. Activate requires operator
certificates and a healthy local IdP; it preserves existing Bearings environment.
"""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path
import pwd
import re
import secrets
import shlex
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
import uuid

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(__file__).with_name("ecosystem")
CONFIG = Path("/etc/bearings/ecosystem")
APPS = Path("/opt/bearings-services")
CLIENT_RELEASES = Path("/var/www/bearings/client-builds")
BEARINGS_ENV = Path("/etc/bearings/bearings.env")
ISSUER = "https://sso.bearings.circl.lu/realms/bearings"
HOSTS = {name: name + ".bearings.circl.lu" for name in ("netbox", "flowintel", "sso")}
USERS = {name: "bearings_" + name for name in ("netbox", "flowintel", "keycloak")}
NETBOX_REV = "3cd2c1d6469caed6c50e80eddd4cde863e0e2cf5"
FLOWINTEL_REV = "0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f"
KC_VERSION = "26.8.1"
KC_SHA256 = "4e2740b181faa2ea623a1c2ecf00855935311e546046e2f857615a47ed24cbe8"
UV = "/opt/bearings-tools/bin/uv"
SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "DEBIAN_FRONTEND": "noninteractive"}
GO_VERSION = "1.27.4"
GO_SHA256 = {
    "amd64": "7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840",
    "arm64": "3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92",
}


def run(args, *, input=None, capture=False, cwd=None, env=None):
    return subprocess.run(
        [str(arg) for arg in args],
        input=input,
        text=True,
        check=True,
        capture_output=capture,
        cwd=cwd,
        env={**SAFE_ENV, **(env or {})},
    )


def client_compiler():
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if not arch:
        raise ValueError("Native client builder supports amd64/arm64 Linux hosts")
    target = APPS / ("go-" + GO_VERSION + "-" + arch)
    marker = target / "bearings-archive.sha256"
    if target.is_symlink():
        raise ValueError("Refusing a symlink compiler directory")
    if target.exists():
        if protected_read(marker).strip() != GO_SHA256[arch]:
            raise ValueError("Retained compiler receipt differs; no adoption or overwrite")
    else:
        with tempfile.TemporaryDirectory(dir=APPS) as temporary:
            archive = Path(temporary) / "go.tar.gz"
            with (
                urllib.request.urlopen(
                    f"https://go.dev/dl/go{GO_VERSION}.linux-{arch}.tar.gz", timeout=30
                ) as response,
                archive.open("wb") as output,
            ):
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 256 * 1024 * 1024:
                        raise ValueError("Go archive exceeds download limit")
                    output.write(chunk)
            with archive.open("rb") as contents:
                if hashlib.file_digest(contents, "sha256").hexdigest() != GO_SHA256[arch]:
                    raise ValueError("Go compiler archive checksum mismatch")
            with tarfile.open(archive) as tar:
                tar.extractall(temporary, filter="data")
            extracted = Path(temporary) / "go"
            write(extracted / marker.name, GO_SHA256[arch] + "\n")
            extracted.rename(target)
    compiler = target / "bin/go"
    if run([compiler, "version"], capture=True).stdout.strip() != f"go version go{GO_VERSION} linux/{arch}":
        raise ValueError("Compiler version/architecture mismatch")
    return compiler


def client_server(current):
    origins = re.findall(r"(?m)^[ \t]*BEARINGS_PUBLIC_URL[ \t]*=(.*)$", current)
    values = shlex.split(origins[0]) if len(origins) == 1 else []
    if len(values) != 1 or not values[0]:
        raise ValueError("Set one BEARINGS_PUBLIC_URL in the protected Bearings environment")
    return values[0]


def windows_release_key(current):
    """One stable operator trust anchor; losing it requires recovery, never rotation."""
    directory(CONFIG)
    key = CONFIG / "windows-release.key"
    previous = re.findall(r"(?m)^BEARINGS_WINDOWS_CLIENT_DIR=(.*)$", current)
    values = shlex.split(previous[0]) if len(previous) == 1 else []
    manifest = Path(values[0]) / "update.json" if len(values) == 1 else None
    if key.exists() or key.is_symlink():
        seed = base64.b64decode(protected_read(key).strip(), validate=True)
        if len(seed) != 32:
            raise ValueError("Invalid Windows release key; restore the protected backup")
    else:
        if manifest is not None and manifest.exists():
            raise ValueError("Windows release key missing; restore its protected backup before publishing")
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(base64.b64encode(secrets.token_bytes(32)).decode("ascii") + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return key, manifest if manifest is not None and manifest.exists() else None


def prepare_clients(*, restart=True):
    """Build both release sets before switching their environment pointers together."""
    if run(["git", "status", "--porcelain"], cwd=ROOT, capture=True).stdout.strip():
        raise ValueError(
            "Publish only a clean reviewed checkout; keep downloaded installers outside the repository"
        )
    directory(APPS, mode=0o755)
    compiler = client_compiler()
    directory(CLIENT_RELEASES, mode=0o755)
    release = Path(tempfile.mkdtemp(prefix="clients-", dir=CLIENT_RELEASES))
    try:
        with tempfile.TemporaryDirectory(dir=APPS) as cache:
            build_env = {
                **{
                    name: os.environ[name]
                    for name in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "SSL_CERT_FILE")
                    if name in os.environ
                },
                "GOCACHE": str(Path(cache) / "cache"),
                "GOPATH": str(Path(cache) / "path"),
                "GOENV": "off",
                "GOTELEMETRY": "off",
                "GOPROXY": "https://proxy.golang.org",
                "GOSUMDB": "sum.golang.org",
            }
            for target in ("linux", "windows"):
                server_args = []
                if target == "windows":
                    server = client_server(protected_read(BEARINGS_ENV))
                    key, previous = windows_release_key(protected_read(BEARINGS_ENV))
                    server_args = ["--server", server, "--signing-key", key]
                    if previous is not None:
                        server_args += ["--previous-manifest", previous]
                run(
                    [
                        ROOT / ".venv/bin/python" if target == "windows" else sys.executable,
                        ROOT / f"scripts/build_{target}_client.py",
                        "--go",
                        compiler,
                        *server_args,
                        "--output",
                        release / target,
                    ],
                    cwd=ROOT,
                    env=build_env,
                )
        for path in (release / "linux", release / "windows"):
            path.chmod(0o755)
        for path in (release / "windows").iterdir():
            path.chmod(0o644)
        release.chmod(0o755)
        current = protected_read(BEARINGS_ENV)
        if client_server(current) != server:
            raise ValueError("BEARINGS_PUBLIC_URL changed during the client build. Retry publication.")
        updated = merge_environment(
            current,
            {
                "BEARINGS_LINUX_CLIENT_DIR": str(release / "linux"),
                "BEARINGS_WINDOWS_CLIENT_DIR": str(release / "windows"),
            },
        )
        directory(CONFIG)
        backup = CONFIG / "bearings-before-client-builds.env"
        if not backup.exists():
            write(backup, current)
        write(BEARINGS_ENV, updated)
    except Exception:
        shutil.rmtree(release)
        raise
    if restart:
        try:
            run(["systemctl", "restart", "bearings-web"])
        except subprocess.CalledProcessError:
            write(BEARINGS_ENV, current)
            run(["systemctl", "restart", "bearings-web"])
            raise
    print("Linux and Windows downloads prepared for /downloads/linux/ and /downloads/windows/.")


def prepare_linux_client():
    """Compatibility entry point for existing operator automation."""
    prepare_clients()


def protected_read(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o077
            or info.st_size > 262144
        ):
            raise ValueError("Expected a bounded, root-owned private regular file: " + str(path))
        return stream.read()


def write(path, text, mode=0o600):
    """Atomic writes into operator-owned directories; never follow a destination symlink."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing symlink destination: " + str(path))
    fd, temporary = tempfile.mkstemp(prefix=".bearings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def environment(values):
    # Generated values only. No shell is used; systemd reads these files.
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or not re.fullmatch(r"[a-zA-Z0-9_./:@?=+,-]+", value):
            raise ValueError("Unsafe generated environment value")
    return "".join(f"{key}={value}\n" for key, value in values.items())


def merge_environment(current, additions):
    """Preserve unrelated secrets byte-for-byte; encode controlled systemd values only."""
    for line in current.splitlines():
        if line.lstrip().startswith(("#", ";")) or not line.strip():
            continue
        if line.endswith("\\") or line.count('"') % 2 or line.count("'") % 2:
            raise ValueError("Review multiline/escaped environment syntax before automated updates")
    for key, value in additions.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or not re.fullmatch(
            r"[a-zA-Z0-9_./:@?=+,\[\] -]*", value
        ):
            raise ValueError("Unsafe environment update")
    kept = [
        line for line in current.splitlines(keepends=True) if line.split("=", 1)[0].strip() not in additions
    ]
    retained = "".join(kept)
    return (
        retained
        + ("\n" if retained and not retained.endswith("\n") else "")
        + "".join(f'{key}="{value}"\n' for key, value in additions.items())
    )


def bearings_manage(args, *, input=None):
    # Input forces the wrapper's pipe mode, including when capturing private metadata.
    return run([ROOT / "deploy/ubuntu24/manage.py", *args], input=input or "", capture=True)


def captured_json(result):
    # Upstream FlowIntel prints a production-mode notice before the JSON result.
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ValueError(
            "Native operation returned no valid receipt; inspect locally without publishing secrets"
        ) from None


def connect_circl(state, args):
    plan = captured_json(bearings_manage(["native_circl", "--actor", args.actor]))
    if not args.apply:
        print(
            json.dumps(
                {
                    "company": "CIRCL",
                    **plan,
                    "netbox": "tenant-scoped read only",
                    "flowintel": "separate non-admin service",
                    "delivery": "unchanged",
                }
            )
        )
        return
    if not state.get("activated"):
        raise ValueError("Activate and verify native HTTPS/SSO before connecting CIRCL")
    path = CONFIG / "circl-connection.json"
    if not path.exists() and (plan["assets"] or plan.get("mode") not in {None, "manual"}):
        raise ValueError("Existing populated or authoritative source requires a reviewed migration")
    saved = json.loads(protected_read(path)) if path.exists() else {"key": str(uuid.uuid4())}
    if saved.get("netbox", {}).get("managed"):
        raise ValueError(
            "Retained CIRCL inventory is managed; use manage-circl-inventory --verify. First-connect never downgrades it."
        )
    # Persist marker before upstream mutations. A crash before credential receipt is
    # deliberately fail-closed: never adopt or reset an unrecorded upstream identity.
    write(path, json.dumps(saved))
    for name in ["netbox", "flowintel"]:
        data = {
            "key": saved["key"],
            "saved": saved.get(name),
            "actor": args.netbox_actor
            if name == "netbox"
            else (args.flowintel_actor or state["admin_email"]),
        }
        if name == "netbox":
            result = django(
                name,
                [
                    "shell",
                    "--no-imports",
                    "-c",
                    f"exec(open({str(TEMPLATES / 'netbox_inventory.py')!r}).read(), {{'__name__': '__main__'}})",
                ],
                input=json.dumps(data),
                capture=True,
            )
        else:
            result = service_run(
                name,
                [APPS / name / ".venv/bin/python", TEMPLATES / "flowintel_bridge.py"],
                input=json.dumps(data),
                capture=True,
            )
        saved[name] = captured_json(result)
        write(path, json.dumps(saved))
    env_path = Path("/etc/bearings/bearings.env")
    current = protected_read(env_path)
    additions = {
        "NETBOX_NATIVE_CIRCL_TOKEN": saved["netbox"]["value"],
        "FLOWINTEL_NATIVE_CIRCL_TOKEN": saved["flowintel"]["value"],
    }
    # Refuse overwriting a deliberately replaced credential, including an empty one.
    for key, value in additions.items():
        existing = [line for line in current.splitlines() if line.split("=", 1)[0].strip() == key]
        if existing and existing != [f'{key}="{value}"']:
            raise ValueError("Retained credential reference changed; no restoration")
    write(env_path, merge_environment(current, additions))
    data = {"key": saved["key"], "tenant": saved["netbox"]["tenant"], "flow_org": saved["flowintel"]["org"]}
    result = captured_json(
        bearings_manage(["native_circl", "--actor", args.actor, "--apply"], input=json.dumps(data))
    )
    run(["systemctl", "restart", "bearings-web", "bearings-worker", "bearings-national"])
    print(json.dumps(result))
    imported = bearings_manage(["sync_netbox", "--source", result["source"]])
    print(imported.stdout.strip())
    print(
        "CIRCL bindings ready; initial GET-only inventory import passed. Empty inventory means coverage is unknown. No cases or email sent."
    )


def managed_circl_inventory(state, args):
    path = CONFIG / "circl-connection.json"
    if not state.get("activated") or not path.is_file():
        raise ValueError("Activate HTTPS/SSO and the retained native CIRCL connection first")
    saved = json.loads(protected_read(path))
    if not saved.get("netbox"):
        raise ValueError("No retained native NetBox receipt; refusing identity adoption")
    metadata = {"key": saved["key"], "tenant": saved["netbox"]["tenant"]}
    command = [
        "native_managed_netbox",
        "--actor",
        args.actor,
        "--host",
        args.host,
        "--kind",
        args.kind,
        "--virtualization",
        args.virtualization,
    ]
    plan = captured_json(bearings_manage(command, input=json.dumps(metadata)))
    if not args.apply and not args.verify:
        print(
            json.dumps(
                {
                    **plan,
                    "planned_mode": "tenant-scoped managed NetBox",
                    "planned_inventory_export": bool(getattr(args, "export_inventory", False)),
                    "existing_rollout_codes": "retain original mode",
                    "physical_host_cluster": "not inferred",
                }
            )
        )
        return
    if args.verify and not saved["netbox"].get("managed"):
        raise ValueError("Managed native policy has not been applied")
    result = django(
        "netbox",
        [
            "shell",
            "--no-imports",
            "-c",
            f"exec(open({str(TEMPLATES / 'netbox_managed.py')!r}).read(), {{'__name__': '__main__'}})",
        ],
        input=json.dumps(
            {
                "key": saved["key"],
                "saved": saved["netbox"],
                "actor": args.netbox_actor,
                "verify_only": args.verify,
                "export_inventory": getattr(args, "export_inventory", False),
            }
        ),
        capture=True,
    )
    saved["netbox"] = captured_json(result)
    write(path, json.dumps(saved))
    metadata["defaults"] = saved["netbox"]["defaults"]
    if getattr(args, "export_inventory", False):
        if not saved["netbox"].get("export"):
            raise ValueError("Native inventory export has not been provisioned")
        export_args = [
            "configure_netbox_export",
            "--actor",
            args.actor,
            "--source",
            plan["source"],
            "--vrf",
            str(saved["netbox"]["export"]["vrf"]),
        ]
        if not args.verify:
            bearings_manage([*export_args, "--apply"])
        else:
            export_plan = captured_json(bearings_manage(export_args))
            if export_plan["current_policy"] != saved["netbox"]["export"]:
                raise ValueError("Retained export policy differs")
    verified = captured_json(
        bearings_manage([*command, "--verify" if args.verify else "--apply"], input=json.dumps(metadata))
    )
    if not verified.get("managed") or not all(
        verified.get(k)
        for k in ["uuid_match", "tenant_match", "import_match", "agent_software_reviews_preserved"]
    ):
        raise ValueError(
            "Managed inventory remains unconfirmed; inspect locally without replacing identities"
        )
    if not args.verify:
        run(["systemctl", "restart", "bearings-web", "bearings-worker", "bearings-national"])
    print(json.dumps(verified))
    print(
        "Managed NetBox host and Bearings import verified. Existing device keys, software and reviews preserved. Existing rollout codes retain their original mode; new codes use managed registration."
    )


def configure_mail(*, allow_self_signed=False):
    path = Path("/etc/bearings/bearings.env")
    current = protected_read(path)
    backup = CONFIG / "bearings-before-mail.env"
    if not backup.exists():
        write(backup, current)
    # A staged connection change must not accidentally release queued service mail.
    additions = {
        "SMTP_HOST": "[cped.circl.lu]",
        "SMTP_PORT": "25",
        "SMTP_STARTTLS": "1",
        "SMTP_TLS": "0",
        "SMTP_TLS_VERIFY": "0" if allow_self_signed else "1",
        "SMTP_TLS_UNVERIFIED_HOST": "cped.circl.lu" if allow_self_signed else "",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "DJANGO_DEFAULT_FROM_EMAIL": "info@circl.lu",
        "BEARINGS_MAIL_SUBJECT_PREFIX": "[CIRCL BEARINGS]",
        "BEARINGS_SERVICE_MAIL_TRANSPORT": "file",
        "BEARINGS_PUBLIC_REGISTRATION": "0",
    }
    write(path, merge_environment(current, additions))
    run(["systemctl", "restart", "bearings-web", "bearings-worker", "bearings-national"])
    print(
        "Relay configured with mandatory STARTTLS on port 25; certificate verification "
        + ("disabled only for cped.circl.lu" if allow_self_signed else "enabled")
        + ". Service delivery remains file-based; public signup remains disabled. Run service_mail_check before enabling delivery."
    )


def realm(state):
    clients = []
    for name, callback in (
        ("bearings", "https://bearings.circl.lu/oauth/complete/oidc/"),
        ("netbox", "https://netbox.bearings.circl.lu/oauth/complete/oidc/"),
        ("flowintel", "https://flowintel.bearings.circl.lu/bearings-sso/callback"),
    ):
        clients.append(
            {
                "clientId": name,
                "protocol": "openid-connect",
                "enabled": True,
                "publicClient": False,
                "secret": state["secrets"][name + "_oidc"],
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "fullScopeAllowed": False,
                "redirectUris": [callback],
                "defaultClientScopes": ["profile", "email"],
                "attributes": {"pkce.code.challenge.method": "S256"},
            }
        )
    return {
        "realm": "bearings",
        "enabled": True,
        "displayName": "CIRCL Bearings",
        "sslRequired": "all",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "bruteForceProtected": True,
        "accessTokenLifespan": 300,
        "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 28800,
        "clients": clients,
        "users": [],
    }


def unit(name, command, directory, state, *, paths="", redis_dependency=True):
    user = USERS[name]
    dependency = f"bearings-{name}-redis.service" if redis_dependency and name != "keycloak" else ""
    mounts = ""
    if not state["lxc_compatible"]:
        mounts = (
            "PrivateTmp=yes\nProtectSystem=strict\nProtectHome=yes\n"
            "ProtectKernelTunables=yes\nProtectKernelModules=yes\nProtectControlGroups=yes\n"
            f"ReadWritePaths=/var/lib/bearings-{name} /run/bearings-{name} {paths}\n"
        )
    return (
        "[Unit]\nDescription=Bearings " + name + " native service\n"
        f"After=network-online.target postgresql.service {dependency}\nWants=network-online.target postgresql.service\n"
        + (f"Requires={dependency}\n" if dependency else "")
        + f"[Service]\nUser={user}\nGroup=www-data\nWorkingDirectory={directory}\n"
        f"EnvironmentFile={CONFIG}/{name}.env\nRuntimeDirectory=bearings-{name}\n"
        f"RuntimeDirectoryMode=0750\nStateDirectory=bearings-{name}\nStateDirectoryMode=0700\n"
        f"ExecStart={command}\nRestart=on-failure\nRestartSec=5\nTimeoutStopSec=120\n"
        "NoNewPrivileges=yes\nCapabilityBoundingSet=\nRestrictSUIDSGID=yes\nUMask=0077\n"
        + mounts
        + "[Install]\nWantedBy=multi-user.target\n"
    )


def nginx(name, *, tls):
    host = HOSTS[name]
    common = (
        f"server_name {host};\nif ($host != {host}) {{ return 444; }}\n"
        "location ^~ /.well-known/acme-challenge/ { root /var/lib/letsencrypt; }\n"
    )
    http = (
        "server { listen 80; listen [::]:80; "
        + common
        + "location / { "
        + ("return 301 https://$host$request_uri;" if tls else "return 404;")
        + " } }\n"
    )
    if not tls:
        return http
    upstream = "http://127.0.0.1:18083" if name == "sso" else f"http://unix:/run/bearings-{name}/web.sock:"
    locations = ""
    if name == "netbox":
        locations = (
            "location /static/ { alias /var/www/bearings-netbox/static/; }\n"
            # Keep private media inaccessible until authorization-aware delivery is configured.
            "location /media/ { internal; alias /var/lib/bearings-netbox/media/; }\n"
        )
    # Do not log callback/auth-code queries at either edge. Runtime logs omit queries too.
    proxy = (
        f"proxy_pass {upstream};\nproxy_set_header Host $http_host;\n"
        "proxy_set_header X-Forwarded-Host $http_host;\nproxy_set_header X-Forwarded-Proto https;\n"
        "proxy_set_header X-Forwarded-For $remote_addr;\nproxy_set_header X-Real-IP $remote_addr;\n"
        "proxy_read_timeout 65s;\n"
    )
    return http + (
        "server { listen 443 ssl; listen [::]:443 ssl;\n"
        + common
        + "ssl_certificate /etc/letsencrypt/live/bearings-ecosystem/fullchain.pem;\n"
        "ssl_certificate_key /etc/letsencrypt/live/bearings-ecosystem/privkey.pem;\n"
        "ssl_protocols TLSv1.2 TLSv1.3;\nclient_max_body_size 10m;\n"
        "access_log off;\nerror_log /var/log/nginx/bearings-ecosystem-error.log crit;\n"
        "add_header Strict-Transport-Security 'max-age=3600' always;\n"
        + locations
        + "location / {\nerror_log /dev/null;\n"
        + proxy
        + "}\n}\n"
    )


def service_run(name, args, *, input=None, capture=False, interactive=False):
    directory = APPS / name / ("netbox" if name == "netbox" else "")
    return run(
        [
            "systemd-run",
            "--quiet",
            "--wait",
            "--collect",
            "--pty" if interactive and sys.stdin.isatty() and input is None and not capture else "--pipe",
            "--property=User=" + USERS[name],
            "--property=Group=www-data",
            "--property=WorkingDirectory=" + str(directory),
            "--property=EnvironmentFile=" + str(CONFIG / (name + ".env")),
            "--property=NoNewPrivileges=yes",
            "--property=CapabilityBoundingSet=",
            "--",
            *args,
        ],
        input=input,
        capture=capture,
    )


def django(name, args, *, input=None, capture=False):
    return service_run(
        name,
        [APPS / name / ".venv/bin/python", APPS / name / "netbox/manage.py", *args],
        input=input,
        capture=capture,
        interactive=bool(
            args
            and args[0] in {"createsuperuser", "changepassword", "shell", "dbshell"}
            and not any(
                a in {"--noinput", "--no-input", "-c", "--command"} or a.startswith("--command=")
                for a in args[1:]
            )
        ),
    )


def directory(path, user="root", mode=0o700):
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Refusing a symlink in a managed directory path: " + str(path))
    run(
        ["install", "-d", "-o", user, "-g", "www-data" if user != "root" else "root", "-m", f"{mode:o}", path]
    )


def checkout(name, url, revision):
    path = APPS / name
    if not path.exists():
        directory(path, mode=0o755)
        run(["git", "init", "-q", path])
        run(["git", "-C", path, "fetch", "--depth", "1", url, revision])
        run(["git", "-C", path, "checkout", "--detach", "FETCH_HEAD"])
    current = run(["git", "-C", path, "rev-parse", "HEAD"], capture=True).stdout.strip()
    if current != revision:
        raise ValueError("Existing native source revision differs; review an upgrade without replacing it")


def generate(state):
    sec = state["secrets"]
    shared = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "OIDC_ISSUER": ISSUER}
    adapter_path = str(TEMPLATES) + ":" + str(ROOT / "config")
    write(
        CONFIG / "netbox.env",
        environment(
            {
                **shared,
                "NETBOX_HOST": HOSTS["netbox"],
                "NETBOX_SECRET_KEY": sec["netbox_key"],
                "NETBOX_TOKEN_PEPPER": sec["netbox_pepper"],
                "NETBOX_CONFIGURATION": "netbox_configuration",
                "PYTHONPATH": adapter_path,
                "OIDC_CLIENT_SECRET": sec["netbox_oidc"],
            }
        ),
    )
    write(
        CONFIG / "flowintel.env",
        environment(
            {
                **shared,
                "SECRET_KEY": sec["flowintel_key"],
                "FLOWINTEL_HOST": HOSTS["flowintel"],
                "FLOWINTEL_ORIGIN": "https://" + HOSTS["flowintel"],
                "FLOWINTEL_APP_ENV": "production",
                "DB_DIALECT": "postgresql",
                "DB_DRIVER": "psycopg2",
                "DB_USER": "bearings_flowintel",
                "DB_HOST": "localhost",
                "DB_NAME": "bearings_flowintel",
                "DB_PASSWORD": sec["unused_db"],
                "ADMIN_FIRST_NAME": "CIRCL",
                "ADMIN_LAST_NAME": "Administrator",
                "ADMIN_MAIL": state["admin_email"],
                "ADMIN_PASSWORD": sec["flowintel_admin"],
                "BOT_MAIL": "disabled-bot@bearings.circl.lu",
                "BEARINGS_FLOWINTEL_NATIVE": "1",
                "BEARINGS_FLOWINTEL_SSO": "1",
                "OIDC_CLIENT_SECRET": sec["flowintel_oidc"],
                "PYTHONPATH": adapter_path + ":" + str(APPS / "flowintel") + ":" + str(ROOT / "docker/sso"),
            }
        ),
    )
    write(
        CONFIG / "keycloak.env",
        environment(
            {
                "KC_DB": "postgres",
                "KC_DB_URL": "jdbc:postgresql://127.0.0.1:5432/bearings_keycloak",
                "KC_DB_USERNAME": "bearings_keycloak",
                "KC_DB_PASSWORD": sec["keycloak_db"],
                "KC_HOSTNAME": "https://" + HOSTS["sso"],
                "KC_HTTP_ENABLED": "true",
                "KC_HTTP_HOST": "127.0.0.1",
                "KC_HTTP_PORT": "18083",
                "KC_HTTP_MANAGEMENT_PORT": "19000",
                "KC_HTTP_MANAGEMENT_HOST": "127.0.0.1",
                "KC_PROXY_HEADERS": "xforwarded",
                "KC_PROXY_TRUSTED_ADDRESSES": "127.0.0.1",
                "KC_CACHE": "local",
                "KC_BOOTSTRAP_ADMIN_USERNAME": "sso-admin",
                "KC_BOOTSTRAP_ADMIN_PASSWORD": sec["keycloak_admin"],
                "JAVA_OPTS_KC_HEAP": "-Xms256m,-Xmx1024m",
            }
        ).replace("JAVA_OPTS_KC_HEAP=-Xms256m,-Xmx1024m", 'JAVA_OPTS_KC_HEAP="-Xms256m -Xmx1024m"'),
    )
    # Immutable client secrets; importing a retained realm never overwrites live users/clients.
    target = APPS / "keycloak/data/import"
    if target.is_dir():
        write(target / "bearings-realm.json", json.dumps(realm(state)))
        shutil.chown(target / "bearings-realm.json", user=USERS["keycloak"], group="www-data")


def install(state):
    # Resume only our staged installation, never mutate a running application's
    # writable paths. An activated installation is refused by main().
    pending = [
        "bearings-" + name
        for name in ("netbox", "netbox-worker", "flowintel", "keycloak", "netbox-redis", "flowintel-redis")
        if Path("/etc/systemd/system", "bearings-" + name + ".service").is_file()
    ]
    if pending:
        run(["systemctl", "stop", *pending])
    if not state["lxc_compatible"]:
        run(["bash", ROOT / "deploy/ubuntu24/check-sandbox.sh"])
    if "redis_preexisting" not in state:
        state["redis_preexisting"] = shutil.which("redis-server") is not None
        save(state)
    run(["apt-get", "update"])
    run(
        [
            "apt-get",
            "install",
            "-y",
            "python3.12-venv",
            "python3-dev",
            "build-essential",
            "libpq-dev",
            "libxml2-dev",
            "libxmlsec1-dev",
            "libxmlsec1-openssl",
            "pkg-config",
            "redis-server",
            "openjdk-21-jre-headless",
            "git",
            "ca-certificates",
            "nginx",
            "certbot",
        ]
    )
    # Preserve an existing Redis installation; stop only the unused service newly
    # installed by this receipt. Our instances use private Unix sockets, no TCP.
    if not state["redis_preexisting"]:
        run(["systemctl", "disable", "--now", "redis-server"])
    directory(APPS, mode=0o755)
    for name, user in USERS.items():
        try:
            account = pwd.getpwnam(user)
        except KeyError:
            run(
                [
                    "useradd",
                    "--system",
                    "--user-group",
                    "--home-dir",
                    "/var/lib/bearings-" + name,
                    "--shell",
                    "/usr/sbin/nologin",
                    user,
                ]
            )
            account = pwd.getpwnam(user)
        if account.pw_dir != "/var/lib/bearings-" + name or account.pw_shell != "/usr/sbin/nologin":
            raise ValueError("Unexpected existing service account; preserved")
        directory("/var/lib/bearings-" + name, user)
        exists = run(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "psql",
                "-Atc",
                f"SELECT 1 FROM pg_roles WHERE rolname='{user}'",
            ],
            capture=True,
        ).stdout.strip()
        if not exists:
            password = f" PASSWORD '{state['secrets']['keycloak_db']}'" if name == "keycloak" else ""
            run(
                ["runuser", "-u", "postgres", "--", "psql", "-v", "ON_ERROR_STOP=1"],
                input=f"CREATE ROLE {user} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE{password};\n",
            )
        unsafe = run(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "psql",
                "-Atc",
                f"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname='{user}'",
            ],
            capture=True,
        ).stdout.strip()
        if unsafe != "f":
            raise ValueError("Unexpected privileged database role; preserved")
        owner = run(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "psql",
                "-Atc",
                f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{user}'",
            ],
            capture=True,
        ).stdout.strip()
        if not owner:
            run(["runuser", "-u", "postgres", "--", "createdb", "--owner=" + user, user])
        elif owner != user:
            raise ValueError("Unexpected database owner; preserved")
    checkout("netbox", "https://github.com/netbox-community/netbox.git", NETBOX_REV)
    checkout("flowintel", "https://github.com/flowintel/flowintel.git", FLOWINTEL_REV)
    for name, requirements in (
        ("netbox", TEMPLATES / "netbox-requirements.txt"),
        ("flowintel", ROOT / "docker/flowintel/requirements.txt"),
    ):
        venv = APPS / name / ".venv"
        if not venv.exists():
            run(["/usr/bin/python3.12", "-m", "venv", venv])
        run([UV, "pip", "sync", "--python", venv / "bin/python", "--require-hashes", requirements])
    keycloak(state)
    for name in ("netbox", "flowintel"):
        for folder in ("media", "scripts", "reports") if name == "netbox" else ("logs", "history", "uploads"):
            target = Path("/var/lib/bearings-" + name) / folder
            directory(target, USERS[name])
            source = APPS / name / ("netbox" if name == "netbox" else "") / folder
            if source.is_symlink():
                if source.resolve() != target:
                    raise ValueError("Unexpected runtime link; preserved")
            elif source.exists():
                # Never overwrite application runtime data. Upstream checkout contains placeholders.
                backup = source.with_name(folder + ".upstream")
                if backup.exists():
                    raise ValueError("Unexpected runtime backup; preserved")
                source.rename(backup)
                source.symlink_to(target)
            else:
                source.symlink_to(target)
    # Keep default source files next to the reviewed native overlays.
    shutil.copyfile(TEMPLATES / "flowintel_config.py", APPS / "flowintel/conf/config.py")
    shutil.copyfile(ROOT / "docker/flowintel/config_module.py", APPS / "flowintel/conf/config_module.py")
    shutil.copyfile(ROOT / "docker/flowintel/sso.py", APPS / "flowintel/flowintel_sso.py")
    directory("/var/www/bearings-netbox/static", USERS["netbox"], 0o755)
    generate(state)
    for name in ("netbox", "flowintel"):
        redis = (
            "port 0\ndaemonize no\nsupervised no\nprotected-mode yes\n"
            f"unixsocket /run/bearings-{name}-redis/redis.sock\nunixsocketperm 700\n"
            f'dir /var/lib/bearings-{name}-redis\nlogfile ""\n'
            + ("appendonly yes\n" if name == "netbox" else 'save ""\nappendonly no\n')
        )
        redis_path = APPS / name / "bearings-redis.conf"
        write(redis_path, redis, 0o644)  # No secrets or credential mount namespaces.
        redis_unit = unit(name, f"/usr/bin/redis-server {redis_path}", "/", state, redis_dependency=False)
        redis_unit = redis_unit.replace(f"EnvironmentFile={CONFIG}/{name}.env\n", "")
        redis_unit = redis_unit.replace("bearings-" + name + "\n", "bearings-" + name + "-redis\n")
        redis_unit = redis_unit.replace(
            f"/var/lib/bearings-{name} /run/bearings-{name}",
            f"/var/lib/bearings-{name}-redis /run/bearings-{name}-redis",
        )
        write(Path("/etc/systemd/system") / f"bearings-{name}-redis.service", redis_unit, 0o644)
    services = {
        "netbox": unit(
            "netbox",
            f"{APPS}/netbox/.venv/bin/gunicorn --bind unix:/run/bearings-netbox/web.sock --umask 7 --workers 2 --threads 2 --timeout 60 --max-requests 2000 --max-requests-jitter 200 --error-logfile - netbox.wsgi",
            APPS / "netbox/netbox",
            state,
            paths="/var/www/bearings-netbox/static",
        ),
        "netbox-worker": unit(
            "netbox",
            f"{APPS}/netbox/.venv/bin/python {APPS}/netbox/netbox/manage.py rqworker",
            APPS / "netbox/netbox",
            state,
        ),
        "flowintel": unit(
            "flowintel",
            f"{APPS}/flowintel/.venv/bin/gunicorn --bind unix:/run/bearings-flowintel/web.sock --umask 7 --workers 2 --timeout 60 --max-requests 2000 --max-requests-jitter 200 --error-logfile - flowintel_wsgi:create_app()",
            APPS / "flowintel",
            state,
        ),
        "keycloak": unit(
            "keycloak",
            f"{APPS}/keycloak/bin/kc.sh start --optimized --import-realm",
            APPS / "keycloak",
            state,
        ),
    }
    for name, text in services.items():
        if name == "netbox-worker":
            text = text.replace("RuntimeDirectory=bearings-netbox\n", "").replace(
                "RuntimeDirectoryMode=0750\n", ""
            )
        write(Path("/etc/systemd/system") / ("bearings-" + name + ".service"), text, 0o644)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "--now", "bearings-netbox-redis", "bearings-flowintel-redis"])
    django("netbox", ["migrate", "--noinput"])
    django("netbox", ["collectstatic", "--noinput"])
    # Readable static assets despite private service umask; no private media is published.
    for folder, directories, files in os.walk("/var/www/bearings-netbox/static"):
        Path(folder).chmod(0o755)
        for file in files:
            (Path(folder) / file).chmod(0o644)
    service_run("flowintel", [APPS / "flowintel/.venv/bin/python", TEMPLATES / "flowintel_manage.py", "init"])
    run(["systemctl", "enable", "--now", *["bearings-" + name for name in services]])
    wait_ready()
    sites(tls=False)
    state["installed"] = True
    save(state)
    print(
        "Native services ready internally. HTTP exposes ACME challenges only. Next: issue certificate, activate."
    )


def keycloak(state):
    target = APPS / "keycloak"
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=APPS) as temporary:
            archive = Path(temporary) / "keycloak.tar.gz"
            request = urllib.request.Request(
                f"https://github.com/keycloak/keycloak/releases/download/{KC_VERSION}/keycloak-{KC_VERSION}.tar.gz"
            )
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        raise ValueError("Keycloak archive exceeds download limit")
                    output.write(chunk)
            with archive.open("rb") as contents:
                if hashlib.file_digest(contents, "sha256").hexdigest() != KC_SHA256:
                    raise ValueError("Keycloak archive checksum mismatch")
            with tarfile.open(archive) as tar:
                tar.extractall(temporary, filter="data")
            (Path(temporary) / ("keycloak-" + KC_VERSION)).rename(target)
    data = Path("/var/lib/bearings-keycloak/data")
    directory(data, USERS["keycloak"])
    if not (target / "data").is_symlink():
        if (target / "data").exists():
            (target / "data").rename(target / "data.upstream")
        (target / "data").symlink_to(data)
    elif (target / "data").resolve() != data:
        raise ValueError("Unexpected Keycloak state link")
    directory(data / "import", USERS["keycloak"])
    run([target / "bin/kc.sh", "build", "--db=postgres", "--health-enabled=true", "--cache=local"])


def wait_ready():
    # A successful systemctl start is insufficient; wait for application responses.
    for name in ("netbox", "flowintel", "keycloak"):
        for attempt in range(90):
            if name == "keycloak":
                args = [
                    "curl",
                    "--fail",
                    "--silent",
                    "--max-time",
                    "2",
                    "http://127.0.0.1:19000/health/ready",
                ]
            else:
                path = "/login/" if name == "netbox" else "/account/login"
                args = [
                    "curl",
                    "--fail",
                    "--silent",
                    "--max-time",
                    "2",
                    "--unix-socket",
                    "/run/bearings-" + name + "/web.sock",
                    "-H",
                    "Host: " + HOSTS[name],
                    "-H",
                    "X-Forwarded-Proto: https",
                    "http://localhost" + path,
                ]
            result = subprocess.run(args, capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise ValueError(
                "Service readiness failed: " + name + "; inspect its journal, retain state and rerun install"
            )


def sites(*, tls):
    paths = [Path("/etc/nginx/sites-available") / ("bearings-" + name) for name in HOSTS]
    previous = {path: path.read_text() if path.exists() else None for path in paths}
    created = []
    try:
        for name, path in zip(HOSTS, paths):
            write(path, nginx(name, tls=tls), 0o644)
            enabled = Path("/etc/nginx/sites-enabled") / path.name
            if not enabled.exists() and not enabled.is_symlink():
                enabled.symlink_to(path)
                created.append(enabled)
            elif not enabled.is_symlink() or enabled.resolve() != path:
                raise ValueError("Unexpected enabled proxy site; preserved")
        run(["nginx", "-t"])
        run(["systemctl", "reload", "nginx"])
    except Exception:
        for link in created:
            link.unlink()
        for path, contents in previous.items():
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                write(path, contents, 0o644)
        raise


def bearings_env(state, current):
    additions = {
        "BEARINGS_SSO_ENABLED": "1",
        "OIDC_ISSUER": ISSUER,
        "OIDC_CLIENT_ID": "bearings",
        "OIDC_CLIENT_SECRET": state["secrets"]["bearings_oidc"],
        **{
            name: ISSUER + "/protocol/openid-connect/" + suffix
            for name, suffix in (
                ("OIDC_AUTHORIZATION_URL", "auth"),
                ("OIDC_TOKEN_URL", "token"),
                ("OIDC_USERINFO_URL", "userinfo"),
                ("OIDC_JWKS_URL", "certs"),
            )
        },
    }
    lines = [
        line
        for line in current.splitlines()
        if line != "# Native ecosystem SSO; local recovery remains enabled."
    ]
    for name, value in additions.items():
        existing = [line for line in lines if re.match(r"\s*" + name + r"\s*=", line)]
        allowed = {f"{name}={value}"}
        if name == "BEARINGS_SSO_ENABLED":
            allowed.add("BEARINGS_SSO_ENABLED=0")
        if any(line not in allowed for line in existing) or len(existing) > 1:
            raise ValueError("Existing SSO configuration differs; refusing identity repointing: " + name)
        lines = [line for line in lines if line not in existing]
    return (
        "\n".join(lines).rstrip()
        + "\n\n# Native ecosystem SSO; local recovery remains enabled.\n"
        + environment(additions)
    )


def activate(state):
    if not state.get("installed"):
        raise ValueError("Complete install first")
    for filename in ("fullchain.pem", "privkey.pem"):
        if not Path("/etc/letsencrypt/live/bearings-ecosystem", filename).is_file():
            raise ValueError("Issue the operator-approved ecosystem certificate first")
    wait_ready()
    target = Path("/etc/bearings/bearings.env")
    old = protected_read(target)
    new = bearings_env(state, old)
    sites(tls=True)
    # Validate the actual public issuer with ordinary CA verification and no redirects.
    # This runs on the operator's server, only after the explicit activate command.
    wait_for_issuer()
    backup = CONFIG / "bearings-before-sso.env"
    if not backup.exists():
        write(backup, old)
    write(target, new)
    try:
        run([ROOT / "deploy/ubuntu24/manage.py", "check", "--deploy", "--fail-level", "WARNING"])
    except Exception:
        write(target, old)
        raise
    run(["systemctl", "restart", "bearings-web", "bearings-worker", "bearings-national"])
    state["activated"] = True
    save(state)
    print("HTTPS and Bearings SSO enabled. Link explicit identities; no application roles were granted.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class IssuerNotReady(ValueError):
    """A verified request failed while new Nginx workers may still be starting."""


def wait_for_issuer():
    # systemctl reload signals Nginx; it does not wait for replacement workers.
    # Every attempt retains normal CA/hostname/issuer checks. Never change the
    # environment until a fully verified request succeeds.
    for attempt in range(8):
        try:
            verify_issuer(timeout=2)
            return
        except IssuerNotReady:
            if attempt == 7:
                raise
            time.sleep(0.25)


def verify_issuer(*, timeout=15):
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(ISSUER + "/.well-known/openid-configuration", timeout=timeout) as response:
            payload = response.read(1000001)
    except urllib.error.HTTPError as error:
        failure = IssuerNotReady if 500 <= error.code < 600 else ValueError
        raise failure(
            f"SSO HTTPS issuer returned HTTP {error.code}; Bearings SSO remains unchanged"
        ) from None
    except urllib.error.URLError as error:
        reason = error.reason
        failure = ValueError
        if isinstance(reason, ssl.SSLCertVerificationError):
            failure = IssuerNotReady
            detail = "certificate verification failed; check hostname/SAN, IPv4/IPv6 vhosts and CA trust"
        elif isinstance(reason, socket.gaierror):
            detail = "DNS resolution failed"
        elif isinstance(reason, TimeoutError):
            failure = IssuerNotReady
            detail = "connection timed out"
        elif isinstance(reason, ConnectionRefusedError):
            failure = IssuerNotReady
            detail = "connection refused"
        else:
            detail = "connection failed; check DNS, IPv4/IPv6 routing and proxy configuration"
        # Do not expose raw exceptions, proxy credentials or response bodies.
        raise failure(f"SSO HTTPS issuer {detail}; Bearings SSO remains unchanged") from None
    if len(payload) > 1000000:
        raise ValueError("SSO issuer metadata exceeds limit; Bearings SSO remains unchanged")
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get("issuer") != ISSUER:
        raise ValueError("Public issuer differs; Bearings SSO remains unchanged")


def save(state):
    write(CONFIG / "state.json", json.dumps(state, indent=2) + "\n")


def initialize(args):
    path = CONFIG / "state.json"
    if path.exists():
        state = json.loads(protected_read(path))
        if args.admin_email and args.admin_email != state["admin_email"]:
            raise ValueError("Retained administrator identity differs; preserved")
        if args.lxc_compatible != state["lxc_compatible"]:
            raise ValueError("Retained sandbox policy differs; use the same install flags")
        return state
    if not args.admin_email and sys.stdin.isatty():
        args.admin_email = input(
            "Email for the first local FlowIntel administrator (no email is sent): "
        ).strip()
    if not args.admin_email or not re.fullmatch(
        r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", args.admin_email
    ):
        raise ValueError("Supply --admin-email with the first FlowIntel administrator address")
    if APPS.exists() or APPS.is_symlink() or (CONFIG.exists() and any(CONFIG.iterdir())):
        raise ValueError("Existing native service directories found without installer receipt; preserved")
    for name in ("netbox", "netbox-worker", "flowintel", "keycloak", "netbox-redis", "flowintel-redis"):
        for target in (
            Path("/var/lib") / ("bearings-" + name),
            Path("/etc/systemd/system") / ("bearings-" + name + ".service"),
        ):
            if target.exists() or target.is_symlink():
                raise ValueError("Existing service/state found without installer receipt; preserved")
    for user in USERS.values():
        if subprocess.run(["getent", "passwd", user], capture_output=True).returncode == 0:
            raise ValueError("Service account already exists without installer receipt; preserved")
        existing = run(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "psql",
                "-Atc",
                f"SELECT 1 FROM pg_roles WHERE rolname='{user}' UNION SELECT 1 FROM pg_database WHERE datname='{user}'",
            ],
            capture=True,
        ).stdout.strip()
        if existing:
            raise ValueError("Database/role already exists without installer receipt; preserved")
    for name in HOSTS:
        if (
            Path("/etc/nginx/sites-available/bearings-" + name).exists()
            or Path("/etc/nginx/sites-enabled/bearings-" + name).is_symlink()
        ):
            raise ValueError("Existing ecosystem proxy configuration found; preserved")
    directory(CONFIG)
    state = {
        "version": 1,
        "admin_email": args.admin_email,
        "lxc_compatible": args.lxc_compatible,
        "secrets": {
            name: secrets.token_hex(32)
            for name in (
                "bearings_oidc",
                "netbox_oidc",
                "flowintel_oidc",
                "netbox_key",
                "netbox_pepper",
                "flowintel_key",
                "flowintel_admin",
                "keycloak_admin",
                "keycloak_db",
                "unused_db",
            )
        },
    }
    save(state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("plan")
    setup = sub.add_parser("install")
    setup.add_argument("--admin-email")
    setup.add_argument(
        "--lxc-compatible",
        action="store_true",
        help="Explicitly omit inner mount sandbox for constrained LXC",
    )
    sub.add_parser("activate")
    sub.add_parser("credentials")
    client_build = sub.add_parser(
        "prepare-clients",
        aliases=["prepare-linux-client"],
        help="Build and publish reviewed Linux and Windows client artifacts",
    )
    client_build.add_argument("--no-restart", action="store_true", help="Leave web restart to the upgrade")
    mail = sub.add_parser("configure-mail", help="Stage the approved CIRCL relay without enabling delivery")
    mail.add_argument(
        "--allow-self-signed",
        action="store_true",
        help="Require STARTTLS but skip relay authentication only for cped.circl.lu",
    )
    connect = sub.add_parser(
        "connect-circl", help="Plan or apply the first isolated native CIRCL connections"
    )
    connect.add_argument("--actor", default="platform-admin")
    connect.add_argument("--netbox-actor", default="platform-admin")
    connect.add_argument(
        "--flowintel-actor",
        help="Existing FlowIntel administrator email; defaults to recorded bootstrap email",
    )
    connect.add_argument("--apply", action="store_true")
    managed = sub.add_parser(
        "manage-circl-inventory", help="Plan, enable or verify the retained CIRCL managed NetBox host"
    )
    managed.add_argument(
        "--export-inventory",
        action="store_true",
        help="Explicitly provision a unique tenant VRF, interface/IP writes and reported software inventory",
    )
    managed.add_argument("--actor", default="platform-admin")
    managed.add_argument("--netbox-actor", default="platform-admin")
    managed.add_argument("--host", default="bearings.circl.lu")
    managed.add_argument("--kind", choices=["vm", "server", "desktop", "laptop"], default="vm")
    managed.add_argument(
        "--virtualization", choices=["", "lxc", "incus", "proxmox", "vmware", "kvm", "hyperv"], default="lxc"
    )
    managed_mode = managed.add_mutually_exclusive_group()
    managed_mode.add_argument("--apply", action="store_true")
    managed_mode.add_argument("--verify", action="store_true")
    link = sub.add_parser("link-netbox-sso")
    link.add_argument("--actor", required=True, help="Existing active NetBox superuser")
    link.add_argument("--username", required=True, help="Existing active NetBox account")
    link.add_argument("--subject", required=True, help="Verified immutable Keycloak User ID, not email")
    manage = sub.add_parser("manage")
    manage.add_argument("service", choices=["netbox", "flowintel"])
    manage.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "plan":
        print(
            json.dumps(
                {
                    "urls": {name: "https://" + host for name, host in HOSTS.items()},
                    "netbox_commit": NETBOX_REV,
                    "flowintel_commit": FLOWINTEL_REV,
                    "keycloak": KC_VERSION,
                    "new_database_roles": list(USERS.values()),
                    "preserves": ["Bearings database/key/state", "existing source bindings"],
                    "stages": [
                        "install internally and ACME-only sites",
                        "operator certificate",
                        "activate HTTPS/SSO",
                        "explicit identity/tenant bindings",
                    ],
                },
                indent=2,
            )
        )
        return
    if (
        os.geteuid() != 0
        or ROOT != Path("/opt/bearings")
        or Path("/proc/1/comm").read_text().strip() != "systemd"
    ):
        raise ValueError("Run as root from /opt/bearings on the existing Ubuntu 24.04 systemd server")
    if (
        'VERSION_ID="24.04"' not in Path("/etc/os-release").read_text()
        or "ID=ubuntu" not in Path("/etc/os-release").read_text()
    ):
        raise ValueError("Ubuntu 24.04 required")
    current = protected_read(Path("/etc/bearings/bearings.env"))
    if [line for line in current.splitlines() if line.startswith("DJANGO_SETTINGS_MODULE=")] != [
        "DJANGO_SETTINGS_MODULE=config.production"
    ]:
        raise ValueError("Existing native production Bearings settings required")
    os.umask(0o022)  # Public code/dependencies stay readable even from a root shell with umask 077.
    # A single operator operation at a time, including management and activation.
    descriptor = os.open("/etc/bearings/ecosystem.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.action in {"prepare-clients", "prepare-linux-client"}:
        prepare_clients(restart=not args.no_restart)
        return
    if args.action == "install":
        state = initialize(args)
        if state.get("activated"):
            raise ValueError("Already activated; use documented reviewed upgrades, not first installation")
        install(state)
        return
    state = json.loads(protected_read(CONFIG / "state.json"))
    if args.action == "activate":
        activate(state)
    elif args.action == "configure-mail":
        configure_mail(allow_self_signed=args.allow_self_signed)
    elif args.action == "manage-circl-inventory":
        managed_circl_inventory(state, args)
    elif args.action == "connect-circl":
        connect_circl(state, args)
    elif args.action == "credentials":
        if not sys.stdout.isatty():
            raise ValueError("Display initial recovery passwords only in an interactive terminal")
        print("Initial recovery credentials (changed passwords are not recoverable):")
        print(
            "Bearings: https://bearings.circl.lu/accounts/login/ (existing local account/password retained)"
        )
        print("NetBox: https://" + HOSTS["netbox"] + "/login/ (operator-created local administrator)")
        print("https://" + HOSTS["sso"] + "/admin/  sso-admin  " + state["secrets"]["keycloak_admin"])
        print(
            "https://"
            + HOSTS["flowintel"]
            + "/account/login  "
            + state["admin_email"]
            + "  "
            + state["secrets"]["flowintel_admin"]
        )
        print("NetBox: create your local administrator with ecosystem.py manage netbox createsuperuser")
    elif args.action == "link-netbox-sso":
        django(
            "netbox",
            ["shell", "--no-imports", "-c", f"exec(open({str(TEMPLATES / 'netbox_link.py')!r}).read())"],
            input=json.dumps({"actor": args.actor, "username": args.username, "subject": args.subject}),
        )
    elif args.service == "netbox":
        django("netbox", args.arguments)
    else:
        service_run(
            "flowintel",
            [APPS / "flowintel/.venv/bin/python", TEMPLATES / "flowintel_manage.py", *args.arguments],
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # Never print command arguments, environment, HTTP bodies or secret-bearing SQL.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        raise SystemExit("Ecosystem operation stopped: " + message) from None
