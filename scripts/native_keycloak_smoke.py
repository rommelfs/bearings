"""Exercise the production realm on disposable Keycloak/PostgreSQL, loopback only.

Uses the pinned upstream Keycloak image to validate the native build's version,
realm and runtime options. Does not test Ubuntu apt/systemd or issue certificates.
"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native", ROOT / "deploy/ubuntu24/ecosystem.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


def main():
    suffix = uuid.uuid4().hex[:10]
    network, pg, keycloak = (
        "bearings-native-" + kind + "-" + suffix for kind in ("network", "idp-db", "idp")
    )
    containers = []
    network_created = False
    with tempfile.TemporaryDirectory(prefix="bearings-keycloak-") as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        state = {
            "secrets": {
                name + "_oidc": "synthetic-" + name + "-" + suffix
                for name in ("bearings", "netbox", "flowintel")
            }
        }
        path = root / "bearings-realm.json"
        path.write_text(json.dumps(native.realm(state)))
        path.chmod(0o644)
        try:
            run(["docker", "network", "create", network])
            network_created = True
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    pg,
                    "--network",
                    network,
                    "-e",
                    "POSTGRES_PASSWORD=synthetic-isolated-only",
                    "postgres:16-alpine",
                ]
            )
            containers.append(pg)
            for _ in range(120):
                r = subprocess.run(
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
                if r.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Fixture IdP database not ready")
            run(
                ["docker", "exec", "-i", "-u", "postgres", pg, "psql", "-v", "ON_ERROR_STOP=1"],
                input=b"CREATE ROLE bearings_keycloak LOGIN PASSWORD 'synthetic-idp-database' NOSUPERUSER NOCREATEDB NOCREATEROLE;\nCREATE DATABASE bearings_keycloak OWNER bearings_keycloak;\n",
            )
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    keycloak,
                    "--network",
                    network,
                    "--memory",
                    "1536m",
                    "-p",
                    "127.0.0.1::8080",
                    "-p",
                    "127.0.0.1::9000",
                    "-v",
                    f"{path}:/opt/keycloak/data/import/bearings-realm.json:ro",
                    "-e",
                    "KC_DB=postgres",
                    "-e",
                    f"KC_DB_URL=jdbc:postgresql://{pg}:5432/bearings_keycloak",
                    "-e",
                    "KC_DB_USERNAME=bearings_keycloak",
                    "-e",
                    "KC_DB_PASSWORD=synthetic-idp-database",
                    "-e",
                    "KC_HOSTNAME=https://sso.bearings.circl.lu",
                    "-e",
                    "KC_HTTP_ENABLED=true",
                    "-e",
                    "KC_PROXY_HEADERS=xforwarded",
                    "-e",
                    "KC_PROXY_TRUSTED_ADDRESSES=127.0.0.1,172.16.0.0/12",
                    "-e",
                    "KC_BOOTSTRAP_ADMIN_USERNAME=sso-admin",
                    "-e",
                    "KC_BOOTSTRAP_ADMIN_PASSWORD=synthetic-idp-recovery",
                    "-e",
                    "KC_HEALTH_ENABLED=true",
                    "-e",
                    "JAVA_OPTS_KC_HEAP=-Xms256m -Xmx1024m",
                    "quay.io/keycloak/keycloak:" + native.KC_VERSION,
                    "start",
                    "--cache=local",
                    "--import-realm",
                ]
            )
            containers.append(keycloak)

            def port(container_port):
                return (
                    run(["docker", "port", keycloak, container_port], text=True)
                    .stdout.strip()
                    .rsplit(":", 1)[1]
                )

            origin = "http://127.0.0.1:" + port("8080/tcp")
            health = "http://127.0.0.1:" + port("9000/tcp")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), native.NoRedirect())

            def request(path, *, token=None, body=None):
                headers = {"Host": "sso.bearings.circl.lu", "X-Forwarded-Proto": "https"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                if body is not None:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                req = urllib.request.Request(origin + path, headers=headers, data=body)
                with opener.open(req, timeout=5) as response:
                    return json.load(response)

            for _ in range(180):
                try:
                    with opener.open(health + "/health/ready", timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Fixture Keycloak failed readiness")
            discovery = request("/realms/bearings/.well-known/openid-configuration")
            assert discovery["issuer"] == native.ISSUER
            data = urllib.parse.urlencode(
                {
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": "sso-admin",
                    "password": "synthetic-idp-recovery",
                }
            ).encode()
            token = request("/realms/master/protocol/openid-connect/token", body=data)["access_token"]
            assert request("/admin/realms/bearings/users", token=token) == []
            clients = request("/admin/realms/bearings/clients", token=token)
            for expected in native.realm(state)["clients"]:
                found = next(client for client in clients if client["clientId"] == expected["clientId"])
                for key in (
                    "redirectUris",
                    "directAccessGrantsEnabled",
                    "serviceAccountsEnabled",
                    "publicClient",
                ):
                    assert found[key] == expected[key]
                assert found["attributes"]["pkce.code.challenge.method"] == "S256"
            print(
                json.dumps(
                    {
                        "keycloak": native.KC_VERSION,
                        "postgres_non_superuser": True,
                        "production_realm_imported": True,
                        "three_exact_clients_pkce": True,
                        "no_fixture_users_in_bearings_realm": True,
                        "public_domain_contacted": False,
                    }
                )
            )
        except Exception:
            for container in containers:
                log = subprocess.run(["docker", "logs", "--tail", "35", container], capture_output=True)
                sys.stderr.buffer.write(log.stdout + log.stderr)
            raise
        finally:
            for container in reversed(containers):
                subprocess.run(["docker", "rm", "-fv", container], capture_output=True)
            if network_created:
                subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
