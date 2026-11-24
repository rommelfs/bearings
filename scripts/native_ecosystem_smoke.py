"""Isolated native Python runtimes/configuration against disposable PostgreSQL/Redis.

No host accounts/services, operational DNS, mail or production data. Requires
reviewed local NetBox/FlowIntel git checkouts and Docker. The source paths and
native fixed runtime directories are redirected only inside this owned fixture.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "deploy/ubuntu24/ecosystem"


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True, **kwargs)


def cleanup_socket_directory(pg_socket):
    # Only the exact bind created by this fixture, never a database/state volume.
    try:
        pg_socket.rmdir()
    except OSError:
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                f"{pg_socket}:/fixture",
                "--entrypoint",
                "/bin/sh",
                "postgres:16-alpine",
                "-c",
                "rm -f /fixture/.s.PGSQL.*",
            ]
        )
        pg_socket.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netbox-source", type=Path, required=True)
    parser.add_argument("--flowintel-source", type=Path, required=True)
    args = parser.parse_args()
    if os.getuid() == 0:
        raise SystemExit("Use an unprivileged developer account; no host service installation")
    created, processes = [], []
    suffix = uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix="bearings-native-") as temporary:
        base = Path(temporary)
        base.chmod(0o755)
        pg_socket, redis_socket = base / "pg", base / "redis"
        pg_socket.mkdir(mode=0o777)
        pg_socket.chmod(0o777)
        redis_socket.mkdir(mode=0o755)
        fixture = base / "fixture"
        fixture.mkdir()
        try:
            pg = "bearings-native-pg-" + suffix
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    pg,
                    "--network",
                    "none",
                    "-e",
                    "POSTGRES_PASSWORD=synthetic-isolated-only",
                    "-e",
                    "POSTGRES_INITDB_ARGS=--auth-local=trust",
                    "-v",
                    f"{pg_socket}:/var/run/postgresql",
                    "postgres:16-alpine",
                ]
            )
            created.append(pg)
            for _ in range(120):
                ready = subprocess.run(
                    [
                        "docker",
                        "exec",
                        pg,
                        "sh",
                        "-c",
                        'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres',
                    ],
                    capture_output=True,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Fixture PostgreSQL not ready")
            for name in ("netbox", "flowintel"):
                run(["docker", "exec", "-u", "postgres", pg, "createuser", "bearings_" + name])
                run(
                    [
                        "docker",
                        "exec",
                        "-u",
                        "postgres",
                        pg,
                        "createdb",
                        "--owner=bearings_" + name,
                        "bearings_" + name,
                    ]
                )
            redis = "bearings-native-redis-" + suffix
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    redis,
                    "--network",
                    "none",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "-v",
                    f"{redis_socket}:/socket",
                    "valkey/valkey:9.1-alpine",
                    "valkey-server",
                    "--port",
                    "0",
                    "--unixsocket",
                    "/socket/redis.sock",
                    "--unixsocketperm",
                    "700",
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                ]
            )
            created.append(redis)
            for _ in range(60):
                if (redis_socket / "redis.sock").exists():
                    break
                time.sleep(0.5)
            for name, source, expected in (
                ("netbox", args.netbox_source, "3cd2c1d6469caed6c50e80eddd4cde863e0e2cf5"),
                ("flowintel", args.flowintel_source, "0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f"),
            ):
                revision = run(["git", "-C", source, "rev-parse", "HEAD"], text=True).stdout.strip()
                if revision != expected:
                    raise RuntimeError("Unexpected fixture source revision")
                target = base / name
                target.mkdir()
                archive = base / (name + ".tar")
                with archive.open("wb") as output:
                    subprocess.run(["git", "-C", str(source), "archive", "HEAD"], stdout=output, check=True)
                with tarfile.open(archive) as tar:
                    tar.extractall(target, filter="data")
                venv = base / (name + "-venv")
                run(["uv", "venv", "--python", "3.12", venv])
                lock = (
                    TEMPLATES / "netbox-requirements.txt"
                    if name == "netbox"
                    else ROOT / "docker/flowintel/requirements.txt"
                )
                run(["uv", "pip", "sync", "--python", venv / "bin/python", "--require-hashes", lock])
            common = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "OIDC_ISSUER": "https://sso.bearings.circl.lu/realms/bearings",
                "OIDC_CLIENT_SECRET": "synthetic-native-client-secret",
                "PYTHONUNBUFFERED": "1",
            }
            config = "from netbox_configuration import *\n"
            config += f"DATABASES['default']['HOST']={str(pg_socket)!r}\n"
            config += f"STORAGES['staticfiles']['OPTIONS']['location']={str(base / 'static')!r}\n"
            config += f"MEDIA_ROOT={str(base / 'media')!r}\n"
            config += f"SCRIPTS_ROOT={str(base / 'scripts')!r}\nREPORTS_ROOT={str(base / 'reports')!r}\n"
            config += f"REDIS={{name:{{'URL':{('unix://' + str(redis_socket / 'redis.sock'))!r}+'?db='+str(i)}} for i,name in enumerate(('tasks','caching'))}}\n"
            (fixture / "fixture_netbox.py").write_text(config)
            netbox_env = {
                **common,
                "NETBOX_HOST": "netbox.bearings.circl.lu",
                "NETBOX_SECRET_KEY": "synthetic-native-secret-" + "x" * 64,
                "NETBOX_TOKEN_PEPPER": "synthetic-native-pepper-" + "x" * 64,
                "NETBOX_CONFIGURATION": "fixture_netbox",
                "PYTHONPATH": f"{fixture}:{TEMPLATES}:{ROOT / 'config'}",
            }
            netbox = [base / "netbox-venv/bin/python", base / "netbox/netbox/manage.py"]
            run([*netbox, "migrate", "--noinput"], env=netbox_env)
            run([*netbox, "collectstatic", "--noinput"], env=netbox_env)
            if not any((base / "static").rglob("*.css")) or (base / "netbox/netbox/static").exists():
                raise RuntimeError("Static collection did not use the separate native destination")
            inventory_checks = (ROOT / "scripts/native_inventory_checks.py").read_text()
            inventory_source = (TEMPLATES / "netbox_inventory.py").read_text()
            run(
                [*netbox, "shell", "--no-imports", "-c", "import sys;exec(sys.stdin.read())"],
                input=(
                    "NATIVE_INVENTORY_SOURCE=" + repr(inventory_source) + "\n" + inventory_checks
                ).encode(),
                env=netbox_env,
            )
            checks = (ROOT / "scripts/netbox_native_link_checks.py").read_text()
            link_source = (TEMPLATES / "netbox_link.py").read_text()
            run(
                [*netbox, "shell", "--no-imports", "-c", "import sys;exec(sys.stdin.read())"],
                input=("NATIVE_LINK_SOURCE=" + repr(link_source) + "\n" + checks).encode(),
                env=netbox_env,
            )
            # Actual ORM fixtures: own-tenant visibility and denial of another tenant.
            fixture_code = """
from users.models import User, Token, ObjectPermission
from tenancy.models import Tenant
from virtualization.models import VirtualMachine
from django.contrib.contenttypes.models import ContentType
first=Tenant.objects.create(name='Native synthetic one',slug='native-one')
other=Tenant.objects.create(name='Native synthetic other',slug='native-other')
VirtualMachine.objects.create(name='native-visible',tenant=first)
VirtualMachine.objects.create(name='native-hidden',tenant=other)
user=User.objects.create(username='native-scoped');user.set_unusable_password();user.save()
permission=ObjectPermission.objects.create(name='Native constrained view',actions=['view'],constraints={'tenant_id':first.pk})
permission.object_types.add(ContentType.objects.get_for_model(VirtualMachine));permission.users.add(user)
token=Token(user=user,token='a'*40,description='Synthetic native test',write_enabled=False);token.save()
from pathlib import Path
Path(NATIVE_TOKEN).write_text(token.get_auth_header_prefix()+'a'*40)
"""
            token_file = base / "native-token"
            run(
                [
                    *netbox,
                    "shell",
                    "--no-imports",
                    "-c",
                    f"NATIVE_TOKEN={str(token_file)!r}\n" + fixture_code,
                ],
                env=netbox_env,
            )
            netbox_socket = base / "netbox.sock"
            log = (base / "netbox.log").open("wb")
            processes.append(
                subprocess.Popen(
                    [
                        str(base / "netbox-venv/bin/gunicorn"),
                        "--bind",
                        "unix:" + str(netbox_socket),
                        "--workers",
                        "1",
                        "netbox.wsgi",
                    ],
                    cwd=base / "netbox/netbox",
                    env=netbox_env,
                    stdout=log,
                    stderr=log,
                )
            )
            flow = base / "flowintel"
            shutil.copyfile(TEMPLATES / "flowintel_config.py", flow / "conf/config.py")
            text = (flow / "conf/config.py").read_text().replace("/var/run/postgresql", str(pg_socket))
            (flow / "conf/config.py").write_text(text)
            shutil.copyfile(ROOT / "docker/flowintel/config_module.py", flow / "conf/config_module.py")
            shutil.copyfile(ROOT / "docker/flowintel/sso.py", fixture / "flowintel_sso.py")
            text = (
                (TEMPLATES / "flowintel_wsgi.py")
                .read_text()
                .replace("/run/bearings-flowintel-redis/redis.sock", str(redis_socket / "redis.sock"))
            )
            (fixture / "flowintel_wsgi.py").write_text(text)
            flow_env = {
                **common,
                "FLOWINTEL_HOST": "flowintel.bearings.circl.lu",
                "FLOWINTEL_ORIGIN": "https://flowintel.bearings.circl.lu",
                "FLOWINTEL_APP_ENV": "production",
                "DB_DIALECT": "postgresql",
                "DB_DRIVER": "psycopg2",
                "SECRET_KEY": "synthetic-native-flow-secret-" + "x" * 50,
                "ADMIN_FIRST_NAME": "Synthetic",
                "ADMIN_LAST_NAME": "Operator",
                "ADMIN_MAIL": "native-fixture@example.invalid",
                "ADMIN_PASSWORD": "synthetic-not-operational",
                "BOT_MAIL": "native-disabled-bot@example.invalid",
                "BEARINGS_FLOWINTEL_NATIVE": "1",
                "BEARINGS_FLOWINTEL_SSO": "1",
                "PYTHONPATH": f"{fixture}:{TEMPLATES}:{flow}:{ROOT / 'docker/sso'}",
            }
            run(
                [base / "flowintel-venv/bin/python", TEMPLATES / "flowintel_manage.py", "init"],
                cwd=flow,
                env=flow_env,
            )
            # Repeat initialization must retain credentials and not duplicate users.
            verify = "from flowintel_wsgi import create_app;from app.db_class.db import User;app=create_app();c=app.app_context();c.push();print([(u.email,u.password_hash,u.role_id,u.org_id) for u in User.query.order_by(User.id)])"
            before = run([base / "flowintel-venv/bin/python", "-c", verify], cwd=flow, env=flow_env).stdout
            run(
                [base / "flowintel-venv/bin/python", TEMPLATES / "flowintel_manage.py", "init"],
                cwd=flow,
                env=flow_env,
            )
            after = run([base / "flowintel-venv/bin/python", "-c", verify], cwd=flow, env=flow_env).stdout
            if before != after:
                raise RuntimeError("FlowIntel repeat changed retained identities")
            bridge_check = """
import runpy,uuid
from app.extensions import db
from app.db_class.db import Role
from flowintel_wsgi import create_app
app=create_app()
with app.app_context():
    module=runpy.run_path(BRIDGE_SOURCE)
    provision=module['provision']
    data={'key':str(uuid.uuid4()),'actor':'native-fixture@example.invalid'}
    saved=provision(data)
    assert provision({**data,'saved':saved}) == saved
    role=db.session.get(Role,saved['role'])
    assert not any(getattr(role,f) for f in module['FLAGS'])
    role.admin=True
    db.session.commit()
    try:
        provision({**data,'saved':saved})
        raise AssertionError('Changed privilege policy accepted')
    except ValueError:
        pass
print('Native non-admin FlowIntel bridge and changed-policy rejection passed')
"""
            run(
                [
                    base / "flowintel-venv/bin/python",
                    "-c",
                    "BRIDGE_SOURCE=" + repr(str(TEMPLATES / "flowintel_bridge.py")) + "\n" + bridge_check,
                ],
                cwd=flow,
                env=flow_env,
            )
            flow_socket = base / "flowintel.sock"
            log_flow = (base / "flowintel.log").open("wb")
            processes.append(
                subprocess.Popen(
                    [
                        str(base / "flowintel-venv/bin/gunicorn"),
                        "--bind",
                        "unix:" + str(flow_socket),
                        "--workers",
                        "1",
                        "flowintel_wsgi:create_app()",
                    ],
                    cwd=flow,
                    env=flow_env,
                    stdout=log_flow,
                    stderr=log_flow,
                )
            )
            for name, unix, path in (
                ("netbox", netbox_socket, "/login/"),
                ("flowintel", flow_socket, "/account/login"),
            ):
                for _ in range(60):
                    result = subprocess.run(
                        [
                            "curl",
                            "--fail",
                            "--silent",
                            "--max-time",
                            "2",
                            "--unix-socket",
                            str(unix),
                            "-H",
                            f"Host: {name}.bearings.circl.lu",
                            "-H",
                            "X-Forwarded-Proto: https",
                            "http://localhost" + path,
                        ],
                        capture_output=True,
                    )
                    if result.returncode == 0:
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Native fixture application failed readiness: " + name)
                if name == "flowintel" and (
                    b"Sign in with SSO" not in result.stdout or b"Lab account:" in result.stdout
                ):
                    raise RuntimeError("Native FlowIntel login contains incorrect SSO UI")
            response = run(
                [
                    "curl",
                    "--fail",
                    "--silent",
                    "--unix-socket",
                    netbox_socket,
                    "-H",
                    "Host: netbox.bearings.circl.lu",
                    "-H",
                    "Authorization: " + token_file.read_text(),
                    "http://localhost/api/virtualization/virtual-machines/",
                ]
            )
            inventory = json.loads(response.stdout)
            if [item["name"] for item in inventory["results"]] != ["native-visible"]:
                raise RuntimeError("Native NetBox tenant scope failed")
            print(
                json.dumps(
                    {
                        "native_netbox_login": 200,
                        "native_flowintel_login": 200,
                        "netbox_tenant_isolation": True,
                        "flowintel_repeated_init_preserves_identity": True,
                        "private_redis_unix_socket": True,
                        "postgres": 16,
                        "host_services_installed": False,
                    }
                )
            )
        except subprocess.CalledProcessError as error:
            # Fixtures contain no operational secrets; still keep output to the failing phase only.
            sys.stderr.buffer.write((error.stderr or b"")[-6000:])
            raise
        finally:
            for process in processes:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for container in reversed(created):
                subprocess.run(["docker", "rm", "-fv", container], capture_output=True)
            # PostgreSQL changes the mountpoint owner. Remove this exact owned
            # empty fixture directory before TemporaryDirectory resets modes.
            cleanup_socket_directory(pg_socket)


if __name__ == "__main__":
    main()
