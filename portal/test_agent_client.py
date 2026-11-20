"""Real Go client -> verified loopback HTTPS -> PostgreSQL; no native inventory changes or external delivery."""

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
import ipaddress
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase, override_settings, Client
from django.utils import timezone
from . import agents
from .models import (
    Organization,
    Membership,
    InventorySource,
    Asset,
    Installation,
    AgentDevice,
    AgentReport,
    AgentComponent,
)

CLIENT = Path(
    os.getenv(
        "BEARINGS_LINUX_CLIENT",
        Path(__file__).resolve().parents[1] / ".local/linux-client/bearings-linux-amd64",
    )
)


class Handler(WSGIRequestHandler):
    def get_environ(self):
        env = super().get_environ()
        env["HTTPS"] = "on"
        return env

    def log_message(self, *args):
        pass


class Server(ThreadingMixIn, WSGIServer):
    daemon_threads = True

    def process_request_thread(self, *args, **kwargs):
        try:
            super().process_request_thread(*args, **kwargs)
        finally:
            connections.close_all()


@unittest.skipUnless(
    CLIENT.is_file(), "Build the Linux reference client to run actual HTTPS interoperability"
)
@override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"], DEBUG=False)
class AgentClientTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Live concurrent HTTPS uses a separate PostgreSQL test database")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.admin = get_user_model().objects.create_user("agent-reference-owner")
        self.org = Organization.objects.create(
            name="SYNTHETIC Linux reference", slug="agent-reference", operator_visibility=False
        )
        Membership.objects.create(user=self.admin, organization=self.org, role="admin")
        self.source = InventorySource.objects.create(organization=self.org, mode="manual")
        self.asset = Asset.objects.create(
            organization=self.org, source=self.source, name="SYNTHETIC Linux reference host", kind="server"
        )
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic loopback reference CA")])
        now = datetime.now(dt_timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        self.ca = self.root / "ca.pem"
        self.ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        private = self.root / "key.pem"
        private.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        private.chmod(0o600)
        self.server = Server(("127.0.0.1", 0), Handler)
        self.server.set_app(get_wsgi_application())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.ca, private)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.origin = "https://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.state = self.root / "state"

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def cli(self, command, *args, ok=True, stdin=None):
        result = subprocess.run(
            [str(CLIENT), command, "--state-dir", str(self.state), *args],
            capture_output=True,
            input=stdin,
            text=True,
            timeout=30,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def enroll(self, new_host=False):
        init = json.loads(self.cli("init").stdout)
        session = Client(enforce_csrf_checks=True)
        session.force_login(self.admin)
        with override_settings(PUBLIC_BASE_URL=self.origin):
            page = session.get("/organizations/agent-reference/agents/", secure=True)
            self.assertEqual(page.status_code, 200)
            response = session.post(
                "/organizations/agent-reference/agents/",
                {
                    "action": "enroll",
                    "asset": "" if new_host else self.asset.pk,
                    "new_asset_kind": "vm" if new_host else "",
                    "public_key": init["public_key"],
                    "acknowledged": "on",
                },
                secure=True,
                HTTP_X_CSRFTOKEN=session.cookies["csrftoken"].value,
                HTTP_ORIGIN="https://testserver",
            )
        self.assertEqual(response.status_code, 200, response.content)
        grant = self.root / "grant.json"
        grant.write_bytes(response.content)
        grant.chmod(0o600)
        enrolled = json.loads(
            self.cli(
                "enroll",
                "--grant-file",
                str(grant),
                "--ca-file",
                str(self.ca),
                *(["--register-host"] if new_host else []),
            ).stdout
        )
        self.assertEqual(enrolled["state"], "enrolled")
        self.device = AgentDevice.objects.get(pk=enrolled["device_id"])
        return init

    def test_fleet_bootstrap_recovers_lost_responses_without_duplicate_identity(self):
        from . import agent_fleets
        from .models import AgentFleetRegistration, InventoryWrite

        with override_settings(PUBLIC_BASE_URL=self.origin):
            fleet, token = agent_fleets.create(self.admin, self.org, "SYNTHETIC rollout", "server", 2, 24)
            self.cli("init")
            args = ("--server", self.origin, "--ca-file", str(self.ca))
            original_issue = agent_fleets.issue

            def lose_bootstrap(*a, **kw):
                original_issue(*a, **kw)
                raise RuntimeError("SYNTHETIC lost bootstrap receipt")

            with patch("portal.agent_fleets.issue", side_effect=lose_bootstrap):
                self.assertNotEqual(self.cli("bootstrap", *args, stdin=token, ok=False).returncode, 0)
            self.assertEqual(AgentFleetRegistration.objects.count(), 1)
            self.assertFalse((self.state / "bootstrap-grant.json").exists())
            original_redeem = agents.redeem

            def lose_enrollment(*a, **kw):
                original_redeem(*a, **kw)
                raise RuntimeError("SYNTHETIC lost device receipt")

            with patch("portal.agent_views.agents.redeem", side_effect=lose_enrollment):
                self.assertNotEqual(self.cli("bootstrap", *args, stdin=token, ok=False).returncode, 0)
            self.assertEqual(AgentDevice.objects.count(), 1)
            self.assertTrue((self.state / "bootstrap-grant.json").exists())
            private_key = (self.state / "key").read_bytes()
            self.cli("bootstrap", *args, stdin=token)
            self.assertFalse((self.state / "bootstrap-grant.json").exists())
            agent_fleets.revoke(self.admin, self.org, fleet.pk)
            self.cli("bootstrap", *args, stdin="")  # already enrolled, no rollout bearer needed
            self.assertEqual((self.state / "key").read_bytes(), private_key)
            self.assertEqual(AgentFleetRegistration.objects.count(), 1)
            self.assertEqual(AgentDevice.objects.count(), 1)
            self.assertFalse(InventoryWrite.objects.exists())
            self.cli("report", "--package", "bash")
            agents.process_pending()
            self.assertEqual(AgentComponent.objects.get().name, "bash")
            self.assertNotIn(token, "".join(p.read_text() for p in self.state.glob("*.json")))

    def test_parallel_native_fleet_hosts_cannot_exceed_quota(self):
        from . import agent_fleets
        from .models import AgentFleetRegistration, InventoryWrite

        with override_settings(PUBLIC_BASE_URL=self.origin):
            fleet, token = agent_fleets.create(
                self.admin, self.org, "SYNTHETIC parallel rollout", "server", 3, 24
            )

            def host(n):
                state = self.root / ("parallel-" + str(n))
                subprocess.run(
                    [str(CLIENT), "init", "--state-dir", str(state)], capture_output=True, check=True
                )
                return subprocess.run(
                    [
                        str(CLIENT),
                        "bootstrap",
                        "--state-dir",
                        str(state),
                        "--server",
                        self.origin,
                        "--ca-file",
                        str(self.ca),
                    ],
                    input=token,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).returncode

            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(host, range(12)))
            self.assertEqual(results.count(0), 3)
            fleet.refresh_from_db()
            self.assertEqual(fleet.issued_devices, 3)
            self.assertEqual(AgentDevice.objects.count(), 3)
            self.assertEqual(AgentFleetRegistration.objects.count(), 3)
            self.assertFalse(InventoryWrite.objects.exists())

    def test_actual_client_enrollment_report_receipt_and_explicit_projection(self):
        self.enroll()
        raw = self.cli("report", "--package", "bash").stdout
        ack = json.loads(raw.strip())
        self.assertEqual(ack["status"], "pending")
        row = AgentReport.objects.get()
        self.assertEqual(row.device_id, self.device.pk)
        self.assertTrue(bytes(row.body))
        self.assertEqual(row.request_url, self.origin + "/api/v1/agent/reports/")
        agents.process_pending()
        component = AgentComponent.objects.get()
        self.assertEqual(component.name, "bash")
        self.assertFalse(Installation.objects.exists())
        agents.bind(self.admin, self.org, component.pk, create=True)
        self.assertEqual(Installation.objects.get().version, component.version)
        result = json.loads(self.cli("status").stdout)
        self.assertEqual(result["status"], "applied")
        self.assertFalse(list((self.state / "outbox").glob("*.json")))
        agents.revoke(self.admin, self.org, self.device.pk)
        failed = self.cli("report", "--package", "bash", ok=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(len(list((self.state / "outbox").glob("*.json"))), 1)
        self.org.refresh_from_db()
        self.assertFalse(self.org.operator_visibility)

    def test_lost_ack_keeps_outbox_and_retry_does_not_duplicate(self):
        self.enroll()
        with patch(
            "portal.agent_views.agents.receipt", side_effect=RuntimeError("SYNTHETIC lost acknowledgment")
        ):
            result = self.cli("report", "--package", "bash", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(AgentReport.objects.count(), 1)
        self.assertEqual(len(list((self.state / "outbox").glob("*.json"))), 1)
        self.cli("flush")
        self.assertEqual(AgentReport.objects.count(), 1)
        self.assertFalse(list((self.state / "outbox").glob("*.json")))

    def test_concurrent_signed_duplicate_receives_one_durable_record(self):
        self.enroll()
        self.cli("enqueue", "--package", "bash")
        raw = next((self.state / "outbox").glob("*.json")).read_bytes()
        key = ed25519.Ed25519PrivateKey.from_private_bytes((self.state / "key").read_bytes())
        import httpx

        def send(_):
            close_old_connections()
            msg = SimpleNamespace(method="POST", url=self.origin + "/api/v1/agent/reports/", headers={})
            from http_message_signatures import HTTPMessageSigner, algorithms
            from .test_agents import Keys
            from .agent_protocol import COVERED, TAG
            import hashlib

            msg.headers = {
                "Content-Type": "application/json",
                "Content-Digest": "sha-256=:" + base64.b64encode(hashlib.sha256(raw).digest()).decode() + ":",
                "X-Bearings-Key": "device:" + str(self.device.pk),
            }
            HTTPMessageSigner(signature_algorithm=algorithms.ED25519, key_resolver=Keys(key)).sign(
                msg,
                key_id="device:" + str(self.device.pk),
                tag=TAG,
                label="bearings",
                covered_component_ids=COVERED,
                created=timezone.now(),
                expires=timezone.now() + timedelta(minutes=5),
                nonce=str(__import__("uuid").uuid4()),
            )
            import ssl

            ctx = ssl.create_default_context(cafile=str(self.ca))
            with httpx.Client(verify=ctx, trust_env=False) as client:
                return client.post(msg.url, content=raw, headers=msg.headers).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(send, range(2)))
        self.assertEqual(results, [202, 202])
        self.assertEqual(AgentReport.objects.count(), 1)

    def test_actual_client_can_register_a_new_private_host_without_preexisting_asset(self):
        self.enroll(new_host=True)
        self.assertNotEqual(self.device.asset_id, self.asset.pk)
        self.assertEqual(self.device.asset.kind, "vm")
        self.assertTrue(self.device.reported_network.get("hostname"))
        self.assertEqual(self.device.asset.state, "recorded")
        self.cli("report", "--package", "bash")
        agents.process_pending()
        self.assertEqual(self.device.components.count(), 1)
        self.org.refresh_from_db()
        self.assertFalse(self.org.operator_visibility)

    def test_native_configured_binary_report_over_verified_https(self):
        self.enroll()
        executable = Path("/usr/bin/printf").resolve()
        if not executable.is_file() or os.geteuid() == 0:
            self.skipTest("Requires an unprivileged collector and native printf")
        config = self.root / "binaries.json"
        config.write_text(
            json.dumps(
                {
                    "schema": "bearings.binary-probes.v1",
                    "binaries": [
                        {
                            "id": "custom-tool",
                            "name": "synthetic-tool",
                            "executable": str(executable),
                            "args": ["SYNTHETIC version %s\\n", "1.2.3"],
                            "version_pattern": r"(?m)^SYNTHETIC version ([0-9.]+)$",
                        }
                    ],
                }
            )
        )
        config.chmod(0o600)
        response = json.loads(self.cli("report", "--binaries-file", str(config)).stdout)
        self.assertEqual(response["status"], "pending")
        row = AgentReport.objects.get(pk=response["report_id"])
        agents.process_one(row.device_id, row.pk)
        c = AgentComponent.objects.get(device=row.device)
        self.assertEqual(c.manager, "binary")
        self.assertEqual(c.version, "1.2.3")
        import hashlib

        self.assertEqual(c.binary["sha256"], hashlib.sha256(executable.read_bytes()).hexdigest())
        self.assertEqual(c.binary["path"], str(executable))
        installation = agents.bind(self.admin, self.org, c.pk, create=True)
        self.assertEqual(installation.version, "1.2.3")
        self.assertTrue(installation.product.identifier.startswith("pkg:generic/"))
