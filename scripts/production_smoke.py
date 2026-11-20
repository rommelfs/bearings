#!/usr/bin/env python3
"""Isolated production-profile check: PG16 peer socket, Gunicorn and verified loopback Nginx TLS.

No actual bearings.circl.lu connection, host account/service or production data.
"""

from datetime import datetime, timedelta, timezone
import json
import base64
import hashlib
from types import SimpleNamespace
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
from cryptography.x509.oid import NameOID
from http_message_signatures import HTTPMessageSigner, HTTPSignatureKeyResolver, algorithms

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, **kwargs)


def main():
    if os.getuid() == 0:
        raise SystemExit("Run this fixture as an unprivileged developer; it creates no host accounts")
    suffix = uuid.uuid4().hex[:10]
    pg, edge = "bearings-prod-pg-" + suffix, "bearings-prod-edge-" + suffix
    created = []
    gunicorn = None
    with tempfile.TemporaryDirectory(prefix="bearings-production-") as directory:
        root = Path(directory)
        root.chmod(0o750)
        socket_dir = root / "pgsocket"
        socket_dir.mkdir(mode=0o755)
        data, static = root / "data", root / "static"
        data.mkdir(mode=0o700)
        static.mkdir(mode=0o755)
        static.chmod(0o755)
        clients = root / "clients"
        clients.mkdir(mode=0o755)
        clients.chmod(0o755)
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.production",
            "DJANGO_DEBUG": "0",
            "DJANGO_SECRET_KEY": "synthetic-isolated-production-" + suffix + "x" * 60,
            "DATABASE_URL": "postgresql://bearings@/bearings",
            "PGHOST": str(socket_dir),
            "BEARINGS_DATA_DIR": str(data),
            "DJANGO_STATIC_ROOT": str(static),
            "BEARINGS_LINUX_CLIENT_DIR": str(clients),
            "DJANGO_ALLOWED_HOSTS": "bearings.circl.lu",
            "BEARINGS_PUBLIC_URL": "https://bearings.circl.lu",
            "BEARINGS_PUBLIC_REGISTRATION": "0",
            "BEARINGS_DEV_STACK": "0",
            "BEARINGS_SSO_LAB": "0",
            "BEARINGS_SSO_ENABLED": "0",
            "BEARINGS_SERVICE_MAIL_TRANSPORT": "file",
            "BEARINGS_NOTIFICATION_TRANSPORT": "file",
        }

        def manage(*args):
            return run([sys.executable, ROOT / "manage.py", *args], cwd=ROOT, env=env)

        try:
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
                    "POSTGRES_PASSWORD=synthetic-local-fixture-only",
                    "-e",
                    "POSTGRES_INITDB_ARGS=--auth-local=peer --auth-host=scram-sha-256",
                    "-v",
                    f"{socket_dir}:/var/run/postgresql",
                    "postgres:16-alpine",
                ]
            )
            created.append(pg)
            for _ in range(100):
                r = subprocess.run(
                    ["docker", "exec", "--user", "postgres", pg, "pg_isready", "-U", "postgres"],
                    capture_output=True,
                )
                logs = subprocess.run(["docker", "logs", pg], capture_output=True)
                if r.returncode == 0 and b"PostgreSQL init process complete;" in logs.stdout:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Fixture PostgreSQL readiness failed")
            # Match the real unprivileged UID through server-side peer authentication.
            run(
                [
                    "docker",
                    "exec",
                    "--user",
                    "0",
                    pg,
                    "sh",
                    "-c",
                    f"printf 'bearings:x:{os.getuid()}:{os.getgid()}:synthetic:/nonexistent:/bin/false\\n' >> /etc/passwd",
                ]
            )
            run(
                [
                    "docker",
                    "exec",
                    "--user",
                    "postgres",
                    pg,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    "CREATE ROLE bearings LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
                ]
            )
            run(["docker", "exec", "--user", "postgres", pg, "createdb", "-O", "bearings", "bearings"])
            manage("migrate", "--noinput")
            manage("collectstatic", "--noinput")
            manage("check", "--deploy", "--fail-level", "WARNING")
            manage("run_worker", "--once")
            manage("refresh_national", "--limit", "10")
            counts = manage(
                "shell",
                "--no-imports",
                "-v",
                "0",
                "-c",
                "from portal.models import Organization,DemoDataset; assert Organization.objects.count()==0 and DemoDataset.objects.count()==0; print('no-fixtures')",
            )
            assert b"no-fixtures" in counts.stdout
            log = (root / "gunicorn.log").open("wb")
            gunicorn = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "gunicorn",
                    "--bind",
                    f"unix:{root / 'web.sock'}",
                    "--umask",
                    "7",
                    "--workers",
                    "1",
                    "--threads",
                    "2",
                    "--access-logfile",
                    "/dev/null",
                    "config.wsgi:application",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
            )
            for _ in range(100):
                if (root / "web.sock").exists():
                    break
                if gunicorn.poll() is not None:
                    raise RuntimeError("Production Gunicorn failed to start")
                time.sleep(0.1)
            else:
                raise RuntimeError("Production socket readiness failed")
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC production fixture")])
            now = datetime.now(timezone.utc)
            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1))
                .not_valid_after(now + timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("bearings.circl.lu")]), False)
                .sign(key, hashes.SHA256())
            )
            (root / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            (root / "key.pem").write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            (root / "key.pem").chmod(0o600)
            config = (ROOT / "deploy/ubuntu24/nginx.conf").read_text()
            replacements = {
                "/run/bearings/web.sock": "/smoke/web.sock",
                "/var/www/bearings/static/": "/smoke/static/",
                "/etc/letsencrypt/live/bearings.circl.lu/fullchain.pem": "/smoke/cert.pem",
                "/etc/letsencrypt/live/bearings.circl.lu/privkey.pem": "/smoke/key.pem",
                "/var/log/nginx/bearings-access.log": "/tmp/access.log",
                "/var/log/nginx/bearings-error.log": "/tmp/error.log",
                "listen 80;": "listen 8080;",
                "listen [::]:80;": "listen [::]:8080;",
                "listen 443 ssl;": "listen 8443 ssl;",
                "listen [::]:443 ssl;": "listen [::]:8443 ssl;",
            }
            for old, new in replacements.items():
                config = config.replace(old, new)
            (root / "nginx.conf").write_text(config)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            # Nginx workers have a distinct UID and the shared socket group, as on the target.
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    edge,
                    "-p",
                    f"127.0.0.1:{port}:8443",
                    "-v",
                    f"{root}:/smoke:ro",
                    "--entrypoint",
                    "/bin/sh",
                    "nginx:1.28-alpine",
                    "-c",
                    f"printf 'bearing-socket:x:{os.getgid()}:\\n' >> /etc/group; printf 'user nginx bearing-socket;\\nevents {{}}\\nhttp {{ include /etc/nginx/mime.types; include /smoke/nginx.conf; }}\\n' > /etc/nginx/nginx.conf; exec nginx -g 'daemon off;'",
                ]
            )
            created.append(edge)

            def request(path):
                return subprocess.run(
                    [
                        "curl",
                        "--noproxy",
                        "*",
                        "--silent",
                        "--show-error",
                        "--cacert",
                        str(root / "cert.pem"),
                        "--resolve",
                        f"bearings.circl.lu:{port}:127.0.0.1",
                        "--max-time",
                        "5",
                        "-o",
                        str(root / "body"),
                        "-D",
                        str(root / "headers"),
                        "-w",
                        "%{http_code}",
                        f"https://bearings.circl.lu:{port}" + path,
                    ],
                    capture_output=True,
                    text=True,
                )

            for _ in range(80):
                response = request("/accounts/login/")
                if response.returncode == 0 and response.stdout == "200":
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Production HTTPS login did not become ready")
            header = (root / "headers").read_text().lower()
            assert "strict-transport-security: max-age=3600" in header
            assert "secure" in header and "csrf" in header
            assert request("/register/").stdout == "403"
            assert request("/static/portal/style.css").stdout == "200"
            assert request("/downloads/linux/").stdout == "200"
            # Explicit synthetic fixture after the no-bootstrap assertion, for signed ingress through the real edge.
            asset = manage(
                "shell",
                "--no-imports",
                "-v",
                "0",
                "-c",
                "from django.contrib.auth import get_user_model; from portal.models import Organization,Membership,InventorySource,Asset; "
                "u=get_user_model().objects.create_user('synthetic-prod-owner'); o=Organization.objects.create(name='SYNTHETIC production check',slug='synthetic-prod',operator_visibility=False); "
                "Membership.objects.create(user=u,organization=o,role='admin'); s=InventorySource.objects.create(organization=o,mode='manual'); "
                "a=Asset.objects.create(organization=o,source=s,name='SYNTHETIC host',kind='vm'); print(a.pk)",
            )
            device_key = ed25519.Ed25519PrivateKey.generate()
            public = base64.b64encode(device_key.public_key().public_bytes_raw()).decode()
            code = (
                manage(
                    "issue_agent_enrollment",
                    "--organization",
                    "synthetic-prod",
                    "--actor",
                    "synthetic-prod-owner",
                    "--asset",
                    asset.stdout.decode().strip(),
                    "--public-key",
                    public,
                )
                .stdout.decode()
                .strip()
                .split(".", 1)[1]
            )
            grant = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)))
            payload = json.dumps(
                {"schema": "bearings.agent.enroll.v1", "request_id": str(uuid.uuid4())}, separators=(",", ":")
            ).encode()
            identity = "enroll:" + grant["grant"].split(".", 1)[0]
            headers = {
                "Content-Type": "application/json",
                "Content-Digest": "sha-256=:"
                + base64.b64encode(hashlib.sha256(payload).digest()).decode()
                + ":",
                "X-Bearings-Key": identity,
                "Authorization": "Bearer " + grant["grant"],
            }
            message = SimpleNamespace(
                method="POST", url=f"https://bearings.circl.lu:{port}/api/v1/agent/enroll/", headers=headers
            )

            class Resolver(HTTPSignatureKeyResolver):
                def resolve_private_key(self, key_id):
                    return device_key

            HTTPMessageSigner(signature_algorithm=algorithms.ED25519, key_resolver=Resolver()).sign(
                message,
                key_id=identity,
                created=now,
                expires=now + timedelta(minutes=5),
                nonce=str(uuid.uuid4()),
                tag="bearings.agent.v1",
                label="bearings",
                covered_component_ids=(
                    "@method",
                    "@path",
                    "@authority",
                    "content-digest",
                    "content-type",
                    "x-bearings-key",
                ),
            )
            body = root / "enroll-body"
            body.write_bytes(payload)
            curl_config = root / "private-curl-config"
            curl_config.write_text(
                "".join("header = " + json.dumps(k + ": " + v) + "\n" for k, v in headers.items())
            )
            curl_config.chmod(0o600)
            result = run(
                [
                    "curl",
                    "--noproxy",
                    "*",
                    "--silent",
                    "--show-error",
                    "--cacert",
                    root / "cert.pem",
                    "--resolve",
                    f"bearings.circl.lu:{port}:127.0.0.1",
                    "--config",
                    curl_config,
                    "--data-binary",
                    "@" + str(body),
                    "--output",
                    root / "receipt",
                    "--write-out",
                    "%{http_code}",
                    f"https://bearings.circl.lu:{port}/api/v1/agent/enroll/",
                ]
            )
            assert result.stdout == b"200", "Signed production ingress failed"
            assert json.loads((root / "receipt").read_text())["asset_id"] == asset.stdout.decode().strip()
            print(
                json.dumps(
                    {
                        "signed_agent_enrollment_through_edge": 200,
                        "postgres": 16,
                        "peer_auth": True,
                        "database_role_superuser": False,
                        "gunicorn_https_login": 200,
                        "registration_closed": 403,
                        "static": 200,
                        "no_synthetic_seed": True,
                        "worker_once": True,
                        "deploy_check": True,
                        "tls_verified_loopback_only": True,
                        "no_host_service_installed": True,
                    }
                )
            )
        finally:
            if gunicorn is not None:
                gunicorn.terminate()
                try:
                    gunicorn.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    gunicorn.kill()
                    gunicorn.wait()
                log.close()
            for name in reversed(created):
                subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
            # PG removes sockets on graceful stop; root fixture cleanup handles any remaining socket entries.
            if socket_dir.exists():
                try:
                    socket_dir.rmdir()
                except OSError:
                    # Do not change another container/host directory; this exact owned bind is a fixture.
                    subprocess.run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "--network",
                            "none",
                            "-v",
                            f"{socket_dir}:/fixture",
                            "--entrypoint",
                            "/bin/sh",
                            "postgres:16-alpine",
                            "-c",
                            "rm -f /fixture/.s.PGSQL.*",
                        ],
                        capture_output=True,
                    )
            shutil.rmtree(static, ignore_errors=True)


if __name__ == "__main__":
    main()
