# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic privileged acceptance; run ONLY via scripts/linux_installer_smoke.py."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import pwd
import secrets
import socket
import ssl
import subprocess
import sys
import threading
from types import SimpleNamespace
import uuid


def main():
    if (
        os.geteuid() != 0
        or socket.gethostname() != "synthetic-bearings-installer"
        or os.environ.get("BEARINGS_INSTALLER_TEST") != "1"
        or not Path("/.dockerenv").exists()
    ):
        raise SystemExit("Refusing privileged fixture outside the explicitly isolated installer container")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
    from cryptography.x509.oid import NameOID
    from http_message_signatures import HTTPMessageVerifier, HTTPSignatureKeyResolver, algorithms

    source = Path("/test-source")
    fixture = Path("/test-fixture")
    fixture.mkdir(mode=0o700)
    state = Path("/run/synthetic-systemd.json")
    state.write_text(json.dumps({"active": False, "enabled": False}))
    systemctl = Path("/usr/bin/systemctl")
    systemctl.write_text("""#!/usr/local/bin/python3
import json,sys
from pathlib import Path
p=Path('/run/synthetic-systemd.json');s=json.loads(p.read_text());a=sys.argv[1:];code=0
if a[0]=='show':print('synthetic-test-only')
elif a[0]=='is-active':code=0 if s['active'] else 3
elif a[0]=='status':print('synthetic systemd status');code=0 if s['active'] else 3
elif a[0]=='stop':s['active']=False
elif a[0] in ('start','restart'):s['active']=True
elif a[0]=='enable':s['enabled']=True;s['active']=s['active'] or '--now' in a
elif a[0]!='daemon-reload':code=99
p.write_text(json.dumps(s));sys.exit(code)
""")
    systemctl.chmod(0o755)
    installer = source / "install.py"

    def call(*args, ok=True, stdin=None):
        r = subprocess.run([sys.executable, installer, *args], input=stdin, capture_output=True, timeout=60)
        assert (r.returncode == 0) == ok, (
            "Installer result differs: " + r.stderr.decode(errors="replace")[-1500:]
        )
        return r.stdout

    first = call("--binary", "/test-client")
    public = next(json.loads(line) for line in first.decode().splitlines() if line.startswith("{"))
    account = pwd.getpwnam("bearings-linux")
    private = Path("/var/lib/bearings-linux")
    key_before = (private / "key").read_bytes()
    assert private.stat().st_uid == account.pw_uid and private.stat().st_mode & 0o777 == 0o700
    assert (private / "key").stat().st_mode & 0o777 == 0o600
    assert not json.loads(state.read_text())["active"]
    call("--binary", "/test-client")
    assert (private / "key").read_bytes() == key_before
    assert not json.loads(state.read_text())["enabled"]

    # Explicit LXC compatibility does not rewrite the hardened unit or device key.
    unit_before = Path("/etc/systemd/system/bearings-linux.service").read_bytes()
    lxc = Path("/etc/systemd/system/bearings-linux.service.d/bearings-lxc.conf")
    assert not lxc.exists()
    call("--binary", "/test-client", "--lxc-compatible")
    lxc_before = lxc.read_bytes()
    assert b"PrivateTmp=no" in lxc_before and b"ProtectHostname=no" in lxc_before
    assert lxc.stat().st_uid == 0 and lxc.stat().st_mode & 0o777 == 0o644
    assert (private / "key").read_bytes() == key_before
    assert Path("/etc/systemd/system/bearings-linux.service").read_bytes() == unit_before
    call("--binary", "/test-client")
    assert lxc.read_bytes() == lxc_before
    lxc.write_bytes(lxc_before + b"# operator change\n")
    call("--binary", "/test-client", "--lxc-compatible", ok=False)
    assert lxc.read_bytes().endswith(b"# operator change\n")
    assert (private / "key").read_bytes() == key_before
    lxc.write_bytes(lxc_before)

    # Real verified TLS and RFC 9421 proof; systemd remains a controlled test double.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SYNTHETIC installer loopback")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        .sign(key, hashes.SHA256())
    )
    ca = fixture / "ca.pem"
    ca.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_tls = fixture / "tls.pem"
    private_tls.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    grant_id = str(uuid.uuid4())
    token = grant_id + "." + secrets.token_urlsafe(32)
    device_id, asset_id = str(uuid.uuid4()), str(uuid.uuid4())
    received = []

    class Resolver(HTTPSignatureKeyResolver):
        def resolve_public_key(self, key_id):
            assert key_id == "enroll:" + grant_id
            return ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(public["public_key"]))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            artifacts = {
                "bearings-linux-amd64": Path("/test-client").read_bytes(),
                "bearings-linux.service": (source / "systemd/bearings-linux.service").read_bytes(),
            }
            manifest = "".join(
                hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in artifacts.items()
            ).encode()
            name = self.path.rsplit("/", 1)[-1]
            response = manifest if name == "SHA256SUMS" else artifacts[name]
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            assert self.path == "/api/v1/agent/enroll/"
            assert self.headers["Authorization"] == "Bearer " + token
            digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
            assert self.headers["Content-Digest"] == "sha-256=:" + digest + ":"
            HTTPMessageVerifier(signature_algorithm=algorithms.ED25519, key_resolver=Resolver()).verify(
                SimpleNamespace(
                    method="POST", url="https://" + self.headers["Host"] + self.path, headers=self.headers
                ),
                expect_tag="bearings.agent.v1",
                expect_label="bearings",
            )
            received.append(body)
            response = json.dumps(
                {
                    "schema": "bearings.agent.enrolled.v1",
                    "device_id": device_id,
                    "asset_id": asset_id,
                    "expires_at": (now + timedelta(days=90)).isoformat(),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, private_tls)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    grant = fixture / "grant.json"
    original = json.dumps(
        {
            "schema": "bearings.agent.grant.v1",
            "url": f"https://localhost:{server.server_port}",
            "grant": token,
            "public_key": public["public_key"],
            "asset_id": asset_id,
            "register_host": False,
            "expires_at": (now + timedelta(minutes=30)).isoformat(),
        }
    ).encode()
    grant.write_bytes(original)
    try:
        call("enroll", "--grant-file", str(grant), ok=False)
        assert (private / "key").read_bytes() == key_before
        assert not received and not json.loads(state.read_text())["enabled"]
        assert not list(Path("/run").glob("bearings-linux-enroll-*"))
        origin = f"https://localhost:{server.server_port}"
        call("--server", origin, "--ca-file", str(ca))
        assert (private / "key").read_bytes() == key_before
        code = b"bearings-enroll-v1." + base64.urlsafe_b64encode(original).rstrip(b"=")
        call("enroll", "--code-stdin", "--ca-file", str(ca), stdin=code + b"\n")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    identity = json.loads(call("identity"))
    assert identity["enrolled"] and identity["public_key"] == public["public_key"]
    config = json.loads((private / "config.json").read_text())
    assert config["device_id"] == device_id and config["ca_file"] == "/etc/bearings-linux/ca.pem"
    assert grant.read_bytes() == original
    assert len(received) == 1 and not list(Path("/run").glob("bearings-linux-enroll-*"))
    assert json.loads(state.read_text()) == {"active": True, "enabled": True}
    assert Path(config["ca_file"]).read_bytes() == ca.read_bytes()

    # A pending queue and operator drop-in survive upgrades and deliberate stops.
    queue = private / "outbox/synthetic.json"
    queue.write_bytes(b"synthetic queued observation")
    os.chown(queue, account.pw_uid, account.pw_gid)
    queue.chmod(0o600)
    dropin = Path("/etc/systemd/system/bearings-linux.service.d/override.conf")
    dropin.parent.mkdir(exist_ok=True)
    dropin.write_text("[Service]\n# synthetic operator customization\n")
    for active in (True, False):
        state.write_text(json.dumps({"active": active, "enabled": True}))
        call("--binary", "/test-client")
        assert json.loads(state.read_text()) == {"active": active, "enabled": True}
        assert (private / "key").read_bytes() == key_before
        assert json.loads((private / "config.json").read_text()) == config
        assert queue.read_bytes() == b"synthetic queued observation" and dropin.exists()
    call("start")
    assert json.loads(state.read_text())["active"]

    unit = Path("/etc/systemd/system/bearings-linux.service")
    unit.write_text(unit.read_text() + "\n# local edit\n")
    call("--binary", "/test-client", ok=False)
    assert unit.read_text().endswith("# local edit\n")
    assert (private / "key").read_bytes() == key_before
    assert json.loads(state.read_text())["active"]

    # Privileged source reads cannot bypass the invoking user's file permissions.
    spec = importlib.util.spec_from_file_location("installer", installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    protected = fixture / "root-only"
    protected.write_bytes(b"synthetic root-only marker")
    protected.chmod(0o600)
    os.environ["SUDO_UID"] = str(account.pw_uid)
    try:
        module.source(protected, 100)
    except module.InstallError:
        pass
    else:
        raise AssertionError("Invoking-user read restriction bypassed")
    print(
        json.dumps(
            {
                "synthetic_only": True,
                "real_account_and_file_permissions": True,
                "central_https_download": True,
                "stdin_registration": True,
                "tls_and_signature_verified": True,
                "failed_enrollment_preserves_key": True,
                "update_preserves_state_and_dropins": True,
                "stopped_service_preserved": True,
                "source_privileges_enforced": True,
                "systemd": "controlled test double",
            }
        )
    )


if __name__ == "__main__":
    main()
