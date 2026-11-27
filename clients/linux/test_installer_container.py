# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic privileged acceptance; run ONLY via scripts/linux_installer_smoke.py."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import pwd
import secrets
import socket
import signal
import time
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
    # The installer must work without weakening /run's noexec mount policy.
    probe = Path("/run/bearings-noexec-probe")
    probe.write_text("#!/bin/sh\nexit 0\n")
    probe.chmod(0o755)
    try:
        subprocess.run([str(probe)], check=True)
    except OSError as error:
        assert error.errno == errno.EACCES
    else:
        raise AssertionError("Fixture requires an actually noexec /run mount")
    finally:
        probe.unlink()
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
    Path("/run/installer-python").write_text(os.environ.get("BEARINGS_INSTALLER_PYTHON", sys.executable))
    systemctl = Path("/usr/bin/systemctl")
    systemctl.write_text("""#!/usr/local/bin/python3
import json,sys
from pathlib import Path
p=Path('/run/synthetic-systemd.json');s=json.loads(p.read_text());a=sys.argv[1:];code=0
unit=next((x for x in a if x.endswith(('.service','.timer'))),'bearings-linux.service')
u=s if unit=='bearings-linux.service' else s.setdefault('units',{}).setdefault(unit,{'active':False,'enabled':False})
s.setdefault('calls',[]).append(a)
if unit=='bearings-linux-update-recover-boot.service' and not u['active'] and (a[0] in ('start','restart') or (a[0]=='enable' and '--now' in a)):
 import subprocess
 p.write_text(json.dumps(s))
 result=subprocess.run([Path('/run/installer-python').read_text(),'-I','/usr/local/lib/bearings-linux/update.py','auto-update-recover-boot'],capture_output=True,timeout=20)
 s=json.loads(p.read_text());u=s.setdefault('units',{}).setdefault(unit,{'active':False,'enabled':False})
 s['nested_boot_recoveries']=s.get('nested_boot_recoveries',0)+1
 if result.returncode:
  sys.stderr.buffer.write(result.stderr);p.write_text(json.dumps(s));sys.exit(result.returncode)
if unit=='bearings-linux.service' and a[0] in ('start','restart') and Path('/etc/systemd/system/bearings-linux.service.d/auto-update-recovery.conf').exists():
 gate=s.setdefault('units',{}).setdefault('bearings-linux-update-recover-boot.service',{'active':False,'enabled':False})
 if not gate['active']:
  import subprocess
  p.write_text(json.dumps(s))
  result=subprocess.run(['/usr/bin/systemctl','start','bearings-linux-update-recover-boot.service'],capture_output=True,timeout=20)
  s=json.loads(p.read_text());u=s
  if result.returncode:
   sys.stderr.buffer.write(result.stderr);p.write_text(json.dumps(s));sys.exit(result.returncode)
if a[0]=='daemon-reload' and s.pop('pause_reload',False):
 import time
 p.write_text(json.dumps(s));Path('/run/updater-paused').touch();time.sleep(90)
if unit=='bearings-linux.service' and a[0]=='restart' and s.pop('fail_next_restart',False):
 u['active']=False;p.write_text(json.dumps(s));sys.exit(1)
if a[0]=='show':print('synthetic-test-only')
elif a[0]=='is-active':code=0 if u['active'] else 3
elif a[0]=='is-enabled':code=0 if u['enabled'] else 1
elif a[0]=='is-failed':code=0 if u.get('failed',False) else 1
elif a[0]=='status':print('synthetic systemd status');code=0 if u['active'] else 3
elif a[0]=='stop':u['active']=False;u['failed']=False
elif a[0] in ('start','restart'):u['active']=True;u['failed']=False
elif a[0]=='enable':u['enabled']=True;u['active']=u['active'] or '--now' in a
elif a[0]=='disable':u['enabled']=False;u['active']=False
elif a[0]!='daemon-reload':code=99
p.write_text(json.dumps(s));sys.exit(code)
""")
    systemctl.chmod(0o755)
    installer = source / "install.py"

    def call(*args, ok=True, stdin=None, error_contains=None):
        r = subprocess.run(
            [os.environ.get("BEARINGS_INSTALLER_PYTHON", sys.executable), installer, *args],
            input=stdin,
            capture_output=True,
            timeout=60,
        )
        assert (r.returncode == 0) == ok, (
            "Installer result differs: " + r.stderr.decode(errors="replace")[-1500:]
        )
        if error_contains:
            assert error_contains in r.stderr.decode(errors="replace")
            assert fleet_token.encode() not in r.stderr
            assert b"untrusted response body" not in r.stderr
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

    # Upgrade both exact prior reviewed units, preserving private state and stopped state.
    unit_path = Path("/etc/systemd/system/bearings-linux.service")
    current_unit = unit_path.read_bytes()
    previous_unit = current_unit.replace(b"--interval 15m", b"--interval 6h")
    older_unit = previous_unit.replace(
        b"# AF_NETLINK is required to read local interface/address metadata without probing.\n", b""
    ).replace(b"AF_INET6 AF_NETLINK", b"AF_INET6")
    for old_unit in (previous_unit, older_unit):
        unit_path.write_bytes(old_unit)
        call("--binary", "/test-client")
        assert unit_path.read_bytes() == current_unit
        assert (private / "key").read_bytes() == key_before
        assert not json.loads(state.read_text())["active"]

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
    fleet_id = str(uuid.uuid4())
    fleet_token = fleet_id + "." + secrets.token_urlsafe(32)
    bootstraps = []
    automatic = os.environ.get("BEARINGS_INSTALLER_FLEET") == "1"

    class Resolver(HTTPSignatureKeyResolver):
        def resolve_public_key(self, key_id):
            assert key_id in ("enroll:" + grant_id, "fleet:" + fleet_id)
            return ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(public["public_key"]))

    publication = {"suffix": b"", "corrupt": False, "response": 200, "bootstrap_denied": False}
    fetched_artifacts = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if publication["response"] != 200:
                self.send_response(publication["response"])
                if publication["response"] == 302:
                    self.send_header("Location", "https://example.invalid/unapproved")
                self.end_headers()
                return
            artifacts = {
                "bearings-linux-amd64": Path("/test-client").read_bytes() + publication["suffix"],
                "bearings-linux.service": (source / "systemd/bearings-linux.service").read_bytes(),
            }
            manifest = "".join(
                hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in artifacts.items()
            ).encode()
            name = self.path.rsplit("/", 1)[-1]
            fetched_artifacts.append(name)
            response = manifest if name == "SHA256SUMS" else artifacts[name]
            if publication["corrupt"] and name == "bearings-linux-amd64":
                response += b"corrupt"
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            is_bootstrap = self.path == "/api/v1/agent/bootstrap/"
            assert self.path in ("/api/v1/agent/enroll/", "/api/v1/agent/bootstrap/")
            assert self.headers["Authorization"] == "Bearer " + (fleet_token if is_bootstrap else token)
            digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
            assert self.headers["Content-Digest"] == "sha-256=:" + digest + ":"
            HTTPMessageVerifier(signature_algorithm=algorithms.ED25519, key_resolver=Resolver()).verify(
                SimpleNamespace(
                    method="POST", url="https://" + self.headers["Host"] + self.path, headers=self.headers
                ),
                expect_tag="bearings.agent.v1",
                expect_label="bearings",
            )
            if is_bootstrap and publication["bootstrap_denied"]:
                response = ("untrusted response body " + fleet_token).encode()
                self.send_response(403)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            if is_bootstrap:
                request = json.loads(body)
                assert request["public_key"] == public["public_key"]
                assert request["schema"] == "bearings.agent.bootstrap.v1"
                bootstraps.append(body)
                response = json.dumps(
                    {
                        "schema": "bearings.agent.grant.v1",
                        "url": origin,
                        "grant": token,
                        "public_key": public["public_key"],
                        "register_host": True,
                        "asset_id": "",
                        "expires_at": (now + timedelta(minutes=30)).isoformat(),
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            received.append(body)
            if automatic:
                assert json.loads(body)["host"]["hostname"] == "synthetic-bearings-installer"
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
        if not automatic:
            call("enroll", "--grant-file", str(grant), ok=False)
        else:
            call(
                "--server",
                f"https://localhost:{server.server_port}",
                "--bootstrap-stdin",
                stdin=fleet_token.encode(),
                ok=False,
            )
        assert (private / "key").read_bytes() == key_before
        assert not received and not json.loads(state.read_text())["enabled"]
        assert not list(Path("/run").glob("bearings-linux-enroll-*"))
        origin = f"https://localhost:{server.server_port}"
        call("--server", origin, "--ca-file", str(ca))
        assert (private / "key").read_bytes() == key_before
        code = b"bearings-enroll-v1." + base64.urlsafe_b64encode(original).rstrip(b"=")
        if automatic:
            publication["bootstrap_denied"] = True
            call(
                "--server",
                origin,
                "--ca-file",
                str(ca),
                "--bootstrap-stdin",
                stdin=fleet_token.encode(),
                ok=False,
                error_contains="Rollout key rejected (HTTP 403). Check whether the key is invalid or expired",
            )
            assert (private / "key").read_bytes() == key_before
            assert not bootstraps and not received
            publication["bootstrap_denied"] = False
            call(
                "--server",
                origin,
                "--ca-file",
                str(ca),
                "--bootstrap-stdin",
                stdin=fleet_token.encode() + b"\n",
            )
            assert len(bootstraps) == 1
            assert not (private / "bootstrap-grant.json").exists()
            assert fleet_token not in (private / "bootstrap.json").read_text()
            state.write_text(json.dumps({"active": False, "enabled": True}))
            call("--server", origin, "--ca-file", str(ca), "--bootstrap-stdin", stdin=b"")
            assert not json.loads(state.read_text())["active"]
            assert len(bootstraps) == 1 and len(received) == 1
            call("start")
        else:
            # A new HTTPS install configures the timer before manual registration.
            call("--server", origin, "--ca-file", str(ca))
            status = json.loads(call("auto-update-status"))
            assert status["timer_active"] and status["timer_enabled"]
            fetched_artifacts.clear()
            call("auto-update")
            assert not fetched_artifacts
            assert json.loads(call("auto-update-status"))["status"]["result"] == "awaiting_enrollment"
            call("--server", origin, "--ca-file", str(ca), "--no-auto-update")
            status = json.loads(call("auto-update-status"))
            assert not status["timer_enabled"] and not status["configuration"]["enabled"]
            call("enroll", "--code-stdin", "--ca-file", str(ca), stdin=code + b"\n")
        if automatic:
            status = json.loads(call("auto-update-status"))
            assert status["timer_active"] and status["timer_enabled"]

        # Root login shells may retain SUDO_UID while the executed installer is
        # readable only by root. Copying itself is distinct from untrusted inputs.
        root_installer = Path("/root/bearings-install.py")
        root_installer.write_bytes(installer.read_bytes())
        root_installer.chmod(0o600)
        original_installer = installer
        os.environ["SUDO_UID"] = str(account.pw_uid)
        try:
            installer = root_installer
            call("auto-update-enable", "--server", origin)
            assert Path("/usr/local/lib/bearings-linux/update.py").read_bytes() == root_installer.read_bytes()
        finally:
            installer = original_installer
            os.environ.pop("SUDO_UID", None)

        # Real updater files/downloads; only systemd control is doubled.
        call("auto-update-enable", "--server", origin, "--ca-file", str(ca))
        installed_updater = Path("/usr/local/lib/bearings-linux/update.py")
        assert installed_updater.read_bytes() == installer.read_bytes()
        assert installed_updater.stat().st_uid == 0 and not installed_updater.stat().st_mode & 0o022
        updater_state = Path("/var/lib/bearings-linux-updater")
        update_config = Path("/etc/bearings-linux/update.json")
        assert update_config.stat().st_mode & 0o777 == 0o600
        enabled_status = json.loads(call("auto-update-status"))
        assert enabled_status["timer_active"] and enabled_status["timer_enabled"]
        assert json.loads(state.read_text())["nested_boot_recoveries"] >= 1
        config_before_update = (private / "config.json").read_bytes()
        before_calls = len(json.loads(state.read_text())["calls"])
        fetched_artifacts.clear()
        call("auto-update")
        assert fetched_artifacts == ["SHA256SUMS"]
        assert json.loads((updater_state / "status.json").read_text())["result"] == "unchanged"
        assert not any("restart" in row for row in json.loads(state.read_text())["calls"][before_calls:])
        assert not (updater_state / "pending.json").exists()

        # Reproduce a failed/inactive boot dependency before the runtime updater.
        # Starting the client under the updater lock would make its child fail.
        service = json.loads(state.read_text())
        service["units"]["bearings-linux-update-recover-boot.service"]["active"] = False
        state.write_text(json.dumps(service))
        publication["suffix"] = b"synthetic-new-publication"
        call("auto-update")
        installed = Path("/usr/local/bin/bearings-linux")
        accepted_binary = installed.read_bytes()
        assert accepted_binary == Path("/test-client").read_bytes() + publication["suffix"]
        assert json.loads((updater_state / "status.json").read_text())["result"] == "updated"
        assert (private / "key").read_bytes() == key_before
        assert (private / "config.json").read_bytes() == config_before_update

        # Local administrative controls must work through sudo as well as direct root.
        # Private installed state is read as root; untrusted input reads still drop privileges.
        os.environ["SUDO_UID"] = str(account.pw_uid)
        try:
            assert json.loads(call("auto-update-status"))["timer_enabled"]
            call("auto-update")
        finally:
            os.environ.pop("SUDO_UID", None)

        # A late process failure during probation recovers the retained baseline too.
        service = json.loads(state.read_text())
        service["active"] = False
        service["failed"] = True
        state.write_text(json.dumps(service))
        call("auto-update-recover")
        assert installed.read_bytes() == Path("/test-client").read_bytes()
        assert json.loads(state.read_text())["active"]
        publication["suffix"] = b"synthetic-next-working-publication"
        call("auto-update")
        accepted_binary = installed.read_bytes()

        # Corrupt response never changes a live client or initiates recovery.
        publication["suffix"] = b"synthetic-corrupted-publication"
        publication["corrupt"] = True
        call("auto-update", ok=False)
        assert installed.read_bytes() == accepted_binary
        assert json.loads(state.read_text())["active"]
        assert not (updater_state / "pending.json").exists()
        publication["corrupt"] = False

        for response_status in (503, 302):
            publication["response"] = response_status
            call("auto-update", ok=False)
            assert installed.read_bytes() == accepted_binary and json.loads(state.read_text())["active"]
            assert not (updater_state / "pending.json").exists()
        publication["response"] = 200

        # Candidate bytes execute, but systemd restart fails: restore known-good bytes.
        publication["suffix"] = b"synthetic-broken-publication"
        service = json.loads(state.read_text())
        service["fail_next_restart"] = True
        state.write_text(json.dumps(service))
        call("auto-update", ok=False)
        assert installed.read_bytes() == accepted_binary and json.loads(state.read_text())["active"]
        assert json.loads((updater_state / "status.json").read_text())["result"] == "rolled_back"
        before_calls = len(json.loads(state.read_text())["calls"])
        call("auto-update", ok=False)
        assert not any("restart" in row for row in json.loads(state.read_text())["calls"][before_calls:])
        assert installed.read_bytes() == accepted_binary

        # Emulate power loss between durable checkpoint and successful commit.
        spec = importlib.util.spec_from_file_location("updater_fixture", installer)
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)
        updater.checkpoint_update("f" * 64, updater.UNIT_SHA256)
        updater.atomic(installed, b"interrupted binary", 0o755)
        service = json.loads(state.read_text())
        service["units"]["bearings-linux-update-recover-boot.service"]["active"] = False
        service["active"] = False
        state.write_text(json.dumps(service))
        call("auto-update-recover")
        assert installed.read_bytes() == accepted_binary and json.loads(state.read_text())["active"]
        assert not (updater_state / "pending.json").exists()

        # Boot recovery restores bytes before systemd starts the dependent client.
        updater.checkpoint_update("e" * 64, updater.UNIT_SHA256)
        updater.atomic(installed, b"interrupted boot candidate", 0o755)
        service = json.loads(state.read_text())
        service["active"] = False
        state.write_text(json.dumps(service))
        call("auto-update-recover-boot")
        assert installed.read_bytes() == accepted_binary and not json.loads(state.read_text())["active"]
        recovery_dependency = Path("/etc/systemd/system/bearings-linux.service.d/auto-update-recovery.conf")
        assert "Requires=bearings-linux-update-recover-boot.service" in recovery_dependency.read_text()
        call("start")

        # Missing/corrupted backups never authorize a guessed recovery.
        updater.checkpoint_update("d" * 64, updater.UNIT_SHA256)
        previous_binary = (updater_state / "previous-client").read_bytes()
        updater.atomic(updater_state / "previous-client", b"damaged backup", 0o700)
        call("auto-update-recover", ok=False)
        assert installed.read_bytes() == accepted_binary and (updater_state / "pending.json").exists()
        updater.atomic(updater_state / "previous-client", previous_binary, 0o700)
        call("auto-update-recover")

        # A disk write failure restores the prior client and resumes reporting.
        from unittest.mock import patch

        publication["suffix"] = b"synthetic-disk-failure-publication"
        original_atomic = updater.atomic
        failed_write = []

        def disk_full(path, *args, **kwargs):
            if path == installed and not failed_write:
                failed_write.append(True)
                raise OSError(errno.ENOSPC, "synthetic full filesystem")
            return original_atomic(path, *args, **kwargs)

        calls_before = len(json.loads(state.read_text())["calls"])
        with patch.object(updater, "atomic", side_effect=disk_full):
            try:
                updater.automatic_update()
            except updater.InstallError:
                pass
            else:
                raise AssertionError("Expected disk failure")
        assert failed_write and installed.read_bytes() == accepted_binary
        # Installer stops immediately before its atomic write; recovery restarts the prior client.
        assert json.loads(state.read_text())["active"]
        assert not (updater_state / "pending.json").exists()

        # Kill an actual updater process after replacement but before transaction commit.
        publication["suffix"] = b"synthetic-process-death-publication"
        service = json.loads(state.read_text())
        service["pause_reload"] = True
        state.write_text(json.dumps(service))
        paused = Path("/run/updater-paused")
        process = subprocess.Popen(
            [os.environ.get("BEARINGS_INSTALLER_PYTHON", sys.executable), installer, "auto-update"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 15
            while not paused.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert paused.exists() and (updater_state / "pending.json").exists()
            assert installed.read_bytes() != accepted_binary
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        call("auto-update-recover")
        assert installed.read_bytes() == accepted_binary and json.loads(state.read_text())["active"]
        assert not (updater_state / "pending.json").exists()

        # A customized main unit is refused before creating an unrecoverable marker.
        old_unit = unit_path.read_bytes()
        unit_path.write_bytes(old_unit + b"\n# deliberate local main-unit change\n")
        publication["suffix"] = b"synthetic-next-publication"
        call("auto-update", ok=False)
        assert not (updater_state / "pending.json").exists()
        assert installed.read_bytes() == accepted_binary
        unit_path.write_bytes(old_unit)

        # Manual and scheduled installers share an exclusive process lock.
        import fcntl

        with Path("/run/bearings-linux-installer.lock").open("r+") as locked:
            fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
            call("auto-update", ok=False)
        assert installed.read_bytes() == accepted_binary

        # A new publication clears the practical quarantine; paused reporting stays paused.
        publication["suffix"] = b"synthetic-corrected-publication"
        service = json.loads(state.read_text())
        service["active"] = False
        state.write_text(json.dumps(service))
        call("auto-update")
        assert not json.loads(state.read_text())["active"]
        call("auto-update-disable")
        assert not json.loads(update_config.read_text())["enabled"]
        disabled_status = json.loads(call("auto-update-status"))
        assert not disabled_status["timer_active"] and not disabled_status["timer_enabled"]
        calls_before = len(json.loads(state.read_text())["calls"])
        call("auto-update")
        assert not any("restart" in row for row in json.loads(state.read_text())["calls"][calls_before:])
        assert (private / "key").read_bytes() == key_before
        assert (private / "config.json").read_bytes() == config_before_update
        call("start")
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
    assert all(json.loads(state.read_text())[key] is True for key in ("active", "enabled"))
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
        assert json.loads(state.read_text())["active"] is active
        assert json.loads(state.read_text())["enabled"] is True
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
                "run_noexec_preserved": True,
                "real_account_and_file_permissions": True,
                "central_https_download": True,
                "stdin_registration": True,
                "automatic_rollout": automatic,
                "tls_and_signature_verified": True,
                "failed_enrollment_preserves_key": True,
                "update_preserves_state_and_dropins": True,
                "stopped_service_preserved": True,
                "source_privileges_enforced": True,
                "auto_update_unchanged_no_restart": True,
                "auto_update_rollback_quarantine_recovery": True,
                "auto_update_disable_and_paused_state": True,
                "systemd": "controlled test double",
            }
        )
    )


if __name__ == "__main__":
    main()
