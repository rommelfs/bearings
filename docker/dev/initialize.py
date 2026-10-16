"""One-off root initializer for isolated development volumes; never prints secrets."""

import json
import os
import pwd
import re
import secrets
import subprocess
from pathlib import Path
import certifi

UID = pwd.getpwnam("bearings").pw_uid
ROOT = Path("/state")


def write(path, content, *, app=False, public=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o644 if public else 0o600)
    os.chown(path, UID if app else 0, 0)


def secret(path, *, app=False):
    if not path.exists():
        write(path, secrets.token_urlsafe(48) + "\n", app=app)
    if not app:
        path.chmod(0o640)  # official NetBox process is netbox:root
    return path.read_text().strip()


def openssl(*args):
    subprocess.run(["openssl", *args], check=True, capture_output=True)


def main():
    mode = os.environ.get("BEARINGS_NETBOX_MODE", "bundled")
    for name in ["secrets", "trust", "netbox-secrets", "tls", "ca-private"]:
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    for name in ["demo_password", "django_secret"]:
        secret(ROOT / "secrets" / name, app=True)
    write(ROOT / "secrets/app_uid", str(UID), public=True)
    ca = b""
    if mode == "bundled":
        for name in ["secret_key", "db_password", "api_token_pepper_1", "api_raw_rw", "api_raw_ro"]:
            secret(ROOT / "netbox-secrets" / name)
        key, cert = ROOT / "ca-private/ca.key", ROOT / "tls/ca.crt"
        if not key.exists():
            openssl(
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-sha256",
                "-days",
                "3650",
                "-subj",
                "/CN=Bearings isolated development CA",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            )
            key.chmod(0o600)
        openssl("x509", "-in", str(cert), "-noout", "-checkend", "86400")
        server_cert, server_key = ROOT / "tls/netbox.crt", ROOT / "tls/netbox.key"
        renew = not server_cert.exists()
        if not renew:
            renew = (
                subprocess.run(
                    ["openssl", "x509", "-in", str(server_cert), "-noout", "-checkend", "1209600"],
                    capture_output=True,
                ).returncode
                != 0
            )
        if renew:
            cfg = ROOT / "ca-private/server.cnf"
            cfg.write_text(
                "[req]\ndistinguished_name=dn\nprompt=no\nreq_extensions=ext\n[dn]\nCN=netbox.bearings.test\n[ext]\nsubjectAltName=DNS:netbox.bearings.test,DNS:localhost,DNS:host.docker.internal,IP:127.0.0.1,IP:::1\n[server]\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:netbox.bearings.test,DNS:localhost,DNS:host.docker.internal,IP:127.0.0.1,IP:::1\n"
            )
            csr = ROOT / "ca-private/server.csr"
            openssl(
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(server_key),
                "-out",
                str(csr),
                "-config",
                str(cfg),
            )
            openssl(
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(cert),
                "-CAkey",
                str(key),
                "-CAcreateserial",
                "-out",
                str(server_cert),
                "-days",
                "397",
                "-sha256",
                "-extfile",
                str(cfg),
                "-extensions",
                "server",
            )
            server_key.chmod(0o600)
        openssl("verify", "-CAfile", str(cert), str(server_cert))
        ca = cert.read_bytes()
    elif mode == "external":
        directory = Path("/external")
        config = json.loads((directory / "connection.json").read_text())
        name = config["token_env_var"]
        if not re.fullmatch(r"NETBOX_[A-Z0-9_]*TOKEN", name):
            raise ValueError("Invalid credential reference")
        write(ROOT / "secrets" / name, (directory / "token").read_text(), app=True)
        write(
            ROOT / "secrets/connections.json",
            json.dumps({"mode": "external", "connections": [config]}),
            public=True,
        )
        if (directory / "ca.crt").exists():
            openssl("x509", "-in", str(directory / "ca.crt"), "-noout")
            ca = (directory / "ca.crt").read_bytes()
    else:
        raise ValueError("Unknown development NetBox mode")
    write(ROOT / "trust/ca-bundle.pem", Path(certifi.where()).read_text() + "\n" + ca.decode(), public=True)
    if ca:
        write(ROOT / "trust/netbox-ca.crt", ca.decode(), public=True)
    elif (ROOT / "trust/netbox-ca.crt").exists():
        (ROOT / "trust/netbox-ca.crt").unlink()
    print("Development secrets and verified certificate trust prepared; values are not logged.")


if __name__ == "__main__":
    main()
