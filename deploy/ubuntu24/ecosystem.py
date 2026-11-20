#!/usr/bin/env python3
"""Native, staged extension of an existing Bearings install. No lab provisioning.

Install is resumable for the recorded installation only. Activate requires operator
certificates and a healthy local IdP; it preserves existing Bearings environment.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(__file__).with_name("ecosystem")
CONFIG = Path("/etc/bearings/ecosystem")
APPS = Path("/opt/bearings-services")
ISSUER = "https://sso.bearings.circl.lu/realms/bearings"
HOSTS = {name: name + ".bearings.circl.lu" for name in ("netbox", "flowintel", "sso")}
USERS = {name: "bearings_" + name for name in ("netbox", "flowintel", "keycloak")}
NETBOX_REV = "3cd2c1d6469caed6c50e80eddd4cde863e0e2cf5"
FLOWINTEL_REV = "0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f"
KC_VERSION = "26.8.1"
KC_SHA256 = "4e2740b181faa2ea623a1c2ecf00855935311e546046e2f857615a47ed24cbe8"
UV = "/opt/bearings-tools/bin/uv"
SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "DEBIAN_FRONTEND": "noninteractive"}


def run(args, *, input=None, capture=False, cwd=None):
    return subprocess.run(
        [str(arg) for arg in args],
        input=input,
        text=True,
        check=True,
        capture_output=capture,
        cwd=cwd,
        env=SAFE_ENV,
    )


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
        "server { listen 80; "
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
        "server { listen 443 ssl;\n"
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


def service_run(name, args, *, input=None):
    directory = APPS / name / ("netbox" if name == "netbox" else "")
    return run(
        [
            "systemd-run",
            "--quiet",
            "--wait",
            "--collect",
            "--pty" if sys.stdin.isatty() and input is None else "--pipe",
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
    )


def django(name, args, *, input=None):
    return service_run(
        name, [APPS / name / ".venv/bin/python", APPS / name / "netbox/manage.py", *args], input=input
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
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(ISSUER + "/.well-known/openid-configuration", timeout=15) as response:
        data = json.loads(response.read(1000001))
    if data.get("issuer") != ISSUER:
        raise ValueError("Public issuer differs; Bearings SSO remains unchanged")
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
    if args.action == "install":
        state = initialize(args)
        if state.get("activated"):
            raise ValueError("Already activated; use documented reviewed upgrades, not first installation")
        install(state)
        return
    state = json.loads(protected_read(CONFIG / "state.json"))
    if args.action == "activate":
        activate(state)
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
