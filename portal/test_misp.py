"""Restricted cache lifecycle, upstream read-only contract and current-recipient authorization."""

import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase, SimpleTestCase, override_settings
from django.utils import timezone
from .tests import Fixture
from .models import MISPInstance, MISPEvent, InfrastructureClaim
from . import misp
from .connectors.http import ConnectorError
from .connectors.misp import snapshot, validate_event


def event_payload(identity=None, timestamp=1700000000, info="Synthetic restricted event"):
    return {
        "Event": {
            "uuid": identity or str(uuid.uuid4()),
            "id": "51",
            "timestamp": str(timestamp),
            "info": info,
            "distribution": "4",
            "sharing_group_id": "17",
            "Tag": [{"name": "tlp:red"}],
            "Attribute": [{"type": "domain", "value": "host.example.invalid", "distribution": "0"}],
            "Object": [
                {"name": "domain-ip", "Attribute": [{"type": "hostname", "value": "nested.example.invalid"}]}
            ],
        }
    }


class MISPCacheTests(Fixture):
    def setUp(self):
        self.source = MISPInstance.objects.create(
            name="Personal MISP", owner=self.analyst, misp_user_id=71, enabled=True
        )
        self.payload = event_payload()
        self.fetch = patch("portal.misp.snapshot", return_value=[self.payload["Event"]]).start()
        self.addCleanup(patch.stopall)

    def refresh(self):
        misp.sync_source(self.source.pk)
        return MISPEvent.objects.get(source=self.source, event_uuid=self.payload["Event"]["uuid"])

    def test_only_personal_owner_can_read_even_if_legacy_grants_or_platform_privileges_exist(self):
        event = self.refresh()
        event.readers.add(self.platform, self.reader)
        event.review_digest = event.digest
        event.reviewed_by = self.platform
        event.save()
        self.assertTrue(misp.visible_events(self.analyst).exists())
        for user in [self.platform, self.admin, self.reader]:
            self.assertFalse(misp.visible_events(user).exists())
            self.login(user)
            self.assertIn(self.client.get(f"/circl/misp/{event.pk}/").status_code, [403, 404])
        with self.assertRaises(PermissionDenied):
            misp.grant_readers(
                self.platform, event.pk, [self.reader], "No key delegation", expected_digest=event.digest
            )
        self.analyst.groups.clear()
        self.assertFalse(misp.visible_events(self.analyst).exists())

    def test_same_event_uuid_is_isolated_per_credential_and_owner(self):
        self.refresh()
        other = MISPInstance.objects.create(
            name="Other identity",
            token_env_var="MISP_OTHER_TOKEN",
            owner=self.platform,
            misp_user_id=72,
            enabled=True,
        )
        misp.sync_source(other.pk)
        self.assertEqual(MISPEvent.objects.count(), 2)
        self.assertEqual(
            list(misp.visible_events(self.analyst).values_list("source_id", flat=True)), [self.source.pk]
        )
        self.assertEqual(
            list(misp.visible_events(self.platform).values_list("source_id", flat=True)), [other.pk]
        )

    def test_failed_missing_stale_and_inflight_caches_are_retained_but_hidden(self):
        event = self.refresh()
        self.fetch.side_effect = ConnectorError("Synthetic failure")
        with self.assertRaises(ConnectorError):
            misp.sync_source(self.source.pk)
        event.refresh_from_db()
        self.assertEqual(event.payload, self.payload["Event"])
        self.assertFalse(misp.visible_events(self.analyst).exists())
        self.fetch.side_effect = None
        self.fetch.return_value = []
        misp.sync_source(self.source.pk)
        event.refresh_from_db()
        self.assertFalse(event.available)
        self.fetch.return_value = [self.payload["Event"]]
        self.refresh()
        self.assertTrue(misp.visible_events(self.analyst).exists())
        MISPInstance.objects.filter(pk=self.source.pk).update(
            last_success=timezone.now() - timedelta(hours=3)
        )
        self.assertFalse(misp.visible_events(self.analyst).exists())

    def test_owner_and_native_identity_cannot_be_reassigned_after_cache(self):
        self.refresh()
        self.source.owner = self.platform
        with self.assertRaises(ValidationError):
            self.source.full_clean()
        self.source.owner = self.analyst
        self.source.misp_user_id = 999
        with self.assertRaises(ValidationError):
            self.source.full_clean()
        self.source.misp_user_id = 71
        self.source.base_url = "https://other.example.invalid"
        with self.assertRaises(ValidationError):
            self.source.full_clean()

    def test_local_research_only_uses_current_verified_visible_claims_and_never_delegates(self):
        event = self.refresh()
        claim = InfrastructureClaim.objects.create(
            organization=self.a,
            kind="domain",
            value="example.invalid",
            status="verified",
            valid_from=timezone.now() - timedelta(days=1),
        )
        InfrastructureClaim.objects.create(
            organization=self.b,
            kind="domain",
            value="example.invalid",
            status="verified",
            valid_from=timezone.now() - timedelta(days=1),
        )
        rows, _ = misp.research(self.analyst, event)
        self.assertEqual({r["organization"].pk for r in rows}, {self.a.pk})
        claim.status = "declared"
        claim.save()
        self.assertEqual(misp.research(self.analyst, event)[0], [])
        with self.assertRaises(PermissionDenied):
            misp.research(self.platform, event)

    def test_no_network_on_reads_and_legacy_grant_endpoint_denied(self):
        event = self.refresh()
        self.fetch.reset_mock()
        self.login(self.analyst)
        response = self.client.get(f"/circl/misp/{event.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotContains(response, "Record authorized readers")
        self.assertEqual(self.client.post(f"/circl/misp/{event.pk}/", {"action": "grant"}).status_code, 403)
        self.fetch.assert_not_called()


def personal_source(**kwargs):
    from django.contrib.auth import get_user_model

    user, _ = get_user_model().objects.get_or_create(username="misp-owner", defaults={"is_superuser": True})
    return MISPInstance(owner=user, misp_user_id=71, **kwargs)


class MISPConnectorTests(TestCase):
    def test_bounded_read_search_uses_only_operator_endpoint_and_stops_at_final_page(self):
        source = personal_source(name="MISP", enabled=True)
        row = event_payload()
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic-test-key"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch(
                "portal.connectors.misp.request_json",
                side_effect=[{"User": {"id": "71", "authkey": "must-not-log"}}, {"response": [row]}],
            ) as http,
        ):
            result = snapshot(source)
        self.assertEqual(result, [row["Event"]])
        args, kwargs = http.call_args_list[-1]
        self.assertEqual(args, ("POST", "https://misppriv.circl.lu/events/restSearch"))
        self.assertFalse(kwargs["json"]["withAttachments"])
        self.assertEqual(kwargs["headers"]["Authorization"], "synthetic-test-key")
        self.assertNotIn("url", kwargs["json"])

    def test_wrong_native_key_identity_is_refused_before_any_event_search(self):
        source = personal_source(name="MISP", enabled=True)
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch(
                "portal.connectors.misp.request_json",
                return_value={"User": {"id": "999", "authkey": "must-not-persist"}},
            ) as http,
        ):
            with self.assertRaises(ConnectorError):
                snapshot(source)
            self.assertEqual(http.call_count, 1)
            self.assertEqual(http.call_args.args[0], "GET")

    def test_missing_secret_disabled_source_and_unsupported_responses_fail_closed(self):
        source = personal_source(name="MISP", enabled=True)
        with patch.dict("os.environ", {}, clear=True), patch("portal.connectors.misp.request_json") as http:
            with self.assertRaises(ConnectorError):
                snapshot(source)
            http.assert_not_called()
        for data in [
            {},
            {"response": {}},
            {"response": [], "next": "https://evil.invalid"},
            {"response": [{}]},
        ]:
            with (
                self.subTest(data=data),
                patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
                patch("portal.connectors.misp.approved_base", return_value=source.base_url),
                patch("portal.connectors.misp.request_json", side_effect=[{"User": {"id": "71"}}, data]),
            ):
                with self.assertRaises(ConnectorError):
                    snapshot(source)

    def test_snapshot_size_and_time_budget_do_not_publish_partial_events(self):
        source = personal_source(name="MISP", enabled=True)
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch(
                "portal.connectors.misp.request_json",
                side_effect=[{"User": {"id": "71"}}, {"response": [event_payload()]}],
            ),
            patch("portal.connectors.misp.MAX_BYTES", 1),
        ):
            with self.assertRaises(ConnectorError):
                snapshot(source)
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch("portal.connectors.misp.time.monotonic", side_effect=[0, 31]),
            patch("portal.connectors.misp.request_json") as http,
        ):
            with self.assertRaises(ConnectorError):
                snapshot(source)
            self.assertEqual(http.call_count, 1)

    def test_duplicate_pages_bounds_and_invalid_event_metadata_never_yield_partial_success(self):
        source = personal_source(name="MISP", enabled=True)
        rows = []
        for i in range(10):
            row = event_payload()
            row["Event"]["id"] = str(i + 1)
            rows.append(row)
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch(
                "portal.connectors.misp.request_json",
                side_effect=[{"User": {"id": "71"}}, {"response": rows}, {"response": rows}],
            ),
        ):
            with self.assertRaises(ConnectorError):
                snapshot(source)
        for change in [
            {"uuid": "invalid"},
            {"timestamp": True},
            {"id": "0"},
            {"distribution": "99"},
            {"Attribute": {}},
            {"deleted": True},
        ]:
            row = event_payload()
            row["Event"].update(change)
            with self.assertRaises(ConnectorError):
                validate_event(row)


class MISPLeaseTests(TransactionTestCase):
    def test_concurrent_worker_cannot_publish_after_operator_disables_source(self):
        from django.db import connection, close_old_connections
        from django.test import skipUnlessDBFeature
        import threading

        @skipUnlessDBFeature("has_select_for_update")
        def run_case():
            source = MISPInstance.objects.create(
                name="Lease fixture", enabled=True, owner=personal_source().owner, misp_user_id=71
            )
            entered, release = threading.Event(), threading.Event()
            errors = []

            def fetch(_source):
                entered.set()
                if not release.wait(5):
                    raise ConnectorError("Synthetic test timeout")
                return [event_payload()["Event"]]

            def worker():
                close_old_connections()
                try:
                    misp.sync_source(source.pk)
                except ConnectorError:
                    errors.append("refused")
                finally:
                    connection.close()

            with patch("portal.misp.snapshot", side_effect=fetch) as http:
                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    self.assertTrue(entered.wait(5))
                    self.assertIsNone(misp.sync_source(source.pk))
                    self.assertEqual(http.call_count, 1)
                    MISPInstance.objects.filter(pk=source.pk).update(enabled=False)
                finally:
                    release.set()
                    thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(errors, ["refused"])
            self.assertFalse(MISPEvent.objects.exists())

        run_case()


@override_settings(CONNECTOR_PROXY_DNS=False)
class MISPTransportTests(TestCase):
    def test_real_https_read_search_pagination_and_redirect_refusal(self):
        import ipaddress
        import ssl
        import tempfile
        import threading
        from pathlib import Path
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic MISP TLS test")])
        now = timezone.now()
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        calls, mode = [], ["ok"]
        rows = []
        for i in range(10):
            row = event_payload()
            row["Event"]["id"] = str(i + 1)
            rows.append(row)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                data = json.dumps({"User": {"id": "71"}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, self.headers.get("Authorization"), body))
                if mode[0] == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "https://127.0.0.1:1/must-not-follow")
                    self.end_headers()
                    return
                data = json.dumps({"response": rows if body["page"] == 1 else []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        with tempfile.TemporaryDirectory() as directory:
            ca, private = Path(directory) / "ca.pem", Path(directory) / "key.pem"
            ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            private.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            private.chmod(0o600)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(ca, private)
            server.socket = tls.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            source = personal_source(
                name="TLS fixture",
                base_url=f"https://127.0.0.1:{server.server_port}",
                enabled=True,
                allow_private=True,
            )
            try:
                with patch.dict(
                    "os.environ",
                    {
                        "SSL_CERT_FILE": str(ca),
                        "NO_PROXY": "127.0.0.1",
                        "MISP_CIRCL_TOKEN": "synthetic-transport-key",
                    },
                ):
                    self.assertEqual(len(snapshot(source)), 10)
                    self.assertEqual([call[2]["page"] for call in calls], [1, 2])
                    self.assertTrue(
                        all(c[0] == "/events/restSearch" and c[1] == "synthetic-transport-key" for c in calls)
                    )
                    mode[0] = "redirect"
                    with self.assertRaises(ConnectorError):
                        snapshot(source)
                    self.assertEqual(len(calls), 3)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)


class MISPInstallerTests(SimpleTestCase):
    def test_key_is_stdin_only_and_configuration_is_disabled_until_operator_enables_it(self):
        import io
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        from scripts.configure_misp import execute

        args = SimpleNamespace(
            owner="misp-owner",
            misp_user_id=71,
            url="https://misp.example.invalid",
            credential_ref="MISP_TEST_TOKEN",
            token_file=None,
            name="Synthetic MISP",
            actor="operator",
            allow_private=False,
        )
        with (
            patch("scripts.dev.active", return_value={"mode": "bundled", "project": "bearings-test"}),
            patch("scripts.configure_misp.getpass.getpass", return_value="synthetic-private-test-token"),
            patch(
                "scripts.dev.run",
                side_effect=[
                    SimpleNamespace(stdout='{"source":1}'),
                    SimpleNamespace(stdout=""),
                    SimpleNamespace(stdout=""),
                ],
            ) as run,
            redirect_stdout(io.StringIO()) as output,
        ):
            execute(args)
        self.assertNotIn("synthetic-private-test-token", output.getvalue())
        self.assertIn("configured and disabled", output.getvalue())
        self.assertEqual(len(run.call_args_list), 3)
        for call in run.call_args_list:
            self.assertNotIn("synthetic-private-test-token", str(call.args))
        self.assertEqual(
            json.loads(run.call_args_list[1].kwargs["input"])["token"], "synthetic-private-test-token"
        )
        config = json.loads(run.call_args_list[0].kwargs["input"])
        self.assertNotIn("token", config)
        self.assertNotIn("enabled", config)

    def test_external_mode_refuses_secret_read_or_container_mutation(self):
        from types import SimpleNamespace
        from scripts.configure_misp import execute

        with (
            patch("scripts.dev.active", return_value={"mode": "external"}),
            patch("scripts.configure_misp.getpass.getpass") as prompt,
            patch("scripts.dev.run") as run,
        ):
            with self.assertRaises(SystemExit):
                execute(SimpleNamespace())
            prompt.assert_not_called()
            run.assert_not_called()
