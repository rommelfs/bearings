"""Restricted cache lifecycle, upstream read-only contract and current-recipient authorization."""

import copy
import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase, SimpleTestCase, override_settings
from django.utils import timezone
from .tests import Fixture
from .models import MISPInstance, MISPEvent, InfrastructureClaim, AuditEvent
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
            name="Synthetic MISP", base_url="https://misp.example.invalid"
        )
        self.source.enabled = True
        self.source.save()
        self.payload = event_payload()
        self.fetch = patch("portal.misp.snapshot", return_value=[self.payload["Event"]]).start()
        self.addCleanup(patch.stopall)

    def refresh(self):
        misp.sync_source(self.source.pk)
        return MISPEvent.objects.get(source=self.source, event_uuid=self.payload["Event"]["uuid"])

    def test_default_no_readers_and_no_participant_raw_or_derived_access(self):
        event = self.refresh()
        self.assertEqual(misp.visible_events(self.platform).count(), 1)
        for user in [self.admin, self.editor, self.reader, self.analyst]:
            self.assertFalse(misp.visible_events(user).exists())
            self.login(user)
            self.assertEqual(
                self.client.get(f"/circl/misp/{event.pk}/").status_code, 404 if user == self.analyst else 403
            )
            if user != self.analyst:
                self.assertEqual(self.client.get("/circl/misp/").status_code, 403)
        self.assertEqual(AuditEvent.objects.filter(action="misp.cache_refreshed").count(), 1)
        self.assertFalse(AuditEvent.objects.filter(details__icontains="host.example.invalid").exists())

    def test_attestation_bound_to_exact_payload_revision_and_current_analyst_role(self):
        event = self.refresh()
        with self.assertRaises(PermissionDenied):
            misp.grant_readers(
                self.analyst, event.pk, [self.analyst], "Not an operator", expected_digest=event.digest
            )
        with self.assertRaises(ValidationError):
            misp.grant_readers(
                self.platform,
                event.pk,
                [self.admin],
                "Company owner must not read this",
                expected_digest=event.digest,
            )
        with self.assertRaises(ValidationError):
            misp.grant_readers(self.platform, event.pk, [self.analyst], " ", expected_digest=event.digest)
        misp.grant_readers(
            self.platform,
            event.pk,
            [self.analyst],
            "Synthetic explicit recipient for RED and nested restrictions",
            expected_digest=event.digest,
        )
        self.assertTrue(misp.visible_events(self.analyst).exists())
        self.refresh()  # Unchanged data preserves the explicitly reviewed revision.
        self.assertTrue(misp.visible_events(self.analyst).exists())
        self.payload["Event"]["Attribute"][0]["distribution"] = "4"  # Policy-only change, same timestamp.
        self.refresh()
        self.assertFalse(misp.visible_events(self.analyst).exists())
        event.refresh_from_db()
        misp.grant_readers(
            self.platform, event.pk, [self.analyst], "Reviewed changed policy", expected_digest=event.digest
        )
        self.analyst.groups.clear()
        self.assertFalse(misp.visible_events(self.analyst).exists())

    def test_review_form_opened_before_policy_change_cannot_approve_new_revision(self):
        event = self.refresh()
        previous = event.digest
        self.payload["Event"]["Attribute"][0]["distribution"] = "4"
        self.refresh()
        self.login(self.platform)
        response = self.client.post(
            f"/circl/misp/{event.pk}/",
            {
                "action": "grant",
                "readers": [self.analyst.pk],
                "note": "Opened before the policy update",
                "acknowledged": "on",
                "expected_digest": previous,
            },
        )
        self.assertContains(response, "Event changed since this review form was opened")
        self.assertFalse(misp.visible_events(self.analyst).exists())

    def test_failed_refresh_preserves_payload_but_suspends_access_for_every_reader(self):
        event = self.refresh()
        misp.grant_readers(
            self.platform, event.pk, [self.analyst], "Synthetic recipients", expected_digest=event.digest
        )
        self.fetch.side_effect = ConnectorError("No body or secret should be propagated")
        with self.assertRaises(ConnectorError):
            misp.sync_source(self.source.pk)
        event.refresh_from_db()
        self.assertEqual(event.payload, self.payload["Event"])
        self.assertFalse(misp.visible_events(self.platform).exists())
        self.assertFalse(misp.visible_events(self.analyst).exists())
        self.source.refresh_from_db()
        self.assertNotIn("secret", self.source.error)
        self.fetch.side_effect = None
        self.refresh()
        self.assertTrue(misp.visible_events(self.analyst).exists())

    def test_missing_event_is_retained_hidden_and_reappearance_requires_fresh_review(self):
        event = self.refresh()
        misp.grant_readers(
            self.platform, event.pk, [self.analyst], "Synthetic recipients", expected_digest=event.digest
        )
        self.fetch.return_value = []
        misp.sync_source(self.source.pk)
        event.refresh_from_db()
        self.assertFalse(event.available)
        self.assertEqual(event.payload, self.payload["Event"])
        self.assertFalse(misp.visible_events(self.platform).exists())
        self.fetch.return_value = [self.payload["Event"]]
        self.refresh()
        self.assertTrue(misp.visible_events(self.platform).exists())
        self.assertFalse(misp.visible_events(self.analyst).exists())

    def test_disabled_stale_and_inflight_sources_never_expose_cache(self):
        self.refresh()
        for fields in [
            {"enabled": False},
            {"last_success": timezone.now() - timedelta(hours=3)},
            {"syncing_until": timezone.now() - timedelta(minutes=5)},
        ]:
            self.source.refresh_from_db()
            previous = {k: getattr(self.source, k) for k in fields}
            MISPInstance.objects.filter(pk=self.source.pk).update(**fields)
            self.assertFalse(misp.visible_events(self.platform).exists())
            MISPInstance.objects.filter(pk=self.source.pk).update(**previous)
        self.assertTrue(misp.visible_events(self.platform).exists())

    def test_endpoint_and_credential_reference_are_immutable_after_cache_and_validated(self):
        self.refresh()
        self.source.base_url = "https://different.example.invalid"
        with self.assertRaises(ValidationError):
            self.source.full_clean()
        for url in [
            "http://misp.example.invalid",
            "https://user:password@misp.example.invalid",
            "https://misp.example.invalid/?key=x",
        ]:
            source = MISPInstance(name="new", base_url=url)
            with self.assertRaises(ValidationError):
                source.full_clean()
        for refresh, max_age in [(0, 120), (60, 5), (1441, 2880)]:
            source = MISPInstance(name="new", refresh_minutes=refresh, max_age_minutes=max_age)
            with self.assertRaises(ValidationError):
                source.full_clean()

    def test_lease_and_due_prevent_duplicate_fetch_and_disabled_sources_never_read(self):
        self.refresh()
        self.fetch.reset_mock()
        self.assertIsNone(misp.sync_source(self.source.pk, due=True))
        self.fetch.assert_not_called()
        MISPInstance.objects.filter(pk=self.source.pk).update(
            syncing_until=timezone.now() + timedelta(minutes=1)
        )
        self.assertIsNone(misp.sync_source(self.source.pk))
        self.fetch.assert_not_called()
        MISPInstance.objects.filter(pk=self.source.pk).update(enabled=False, syncing_until=None)
        with self.assertRaises(ConnectorError):
            misp.sync_source(self.source.pk)
        self.fetch.assert_not_called()

    def test_expired_worker_lease_is_recovered_before_normal_interval(self):
        self.refresh()
        MISPInstance.objects.filter(pk=self.source.pk).update(
            syncing_until=timezone.now() - timedelta(seconds=1)
        )
        self.fetch.reset_mock()
        self.assertEqual(misp.sync_source(self.source.pk, due=True), 1)
        self.assertEqual(self.fetch.call_count, 1)

    def test_command_does_not_starve_short_interval_source_behind_long_interval_source(self):
        from io import StringIO
        from django.core.management import call_command

        self.refresh()
        MISPInstance.objects.filter(pk=self.source.pk).update(
            last_attempt=timezone.now() - timedelta(hours=2), refresh_minutes=1440, max_age_minutes=1440
        )
        other = MISPInstance.objects.create(
            name="Due second source",
            token_env_var="MISP_SECOND_TOKEN",
            enabled=True,
            refresh_minutes=5,
            last_attempt=timezone.now() - timedelta(minutes=10),
        )
        call_command("sync_misp", all=True, due=True, limit=1, stdout=StringIO())
        self.assertTrue(MISPEvent.objects.filter(source=other).exists())

    def test_operator_configuration_disables_source_and_invalidates_old_recipient_attestation(self):
        import io
        from django.core.management import call_command

        event = self.refresh()
        misp.grant_readers(
            self.platform, event.pk, [self.analyst], "Synthetic recipients", expected_digest=event.digest
        )
        body = {
            "name": self.source.name,
            "base_url": self.source.base_url,
            "token_env_var": self.source.token_env_var,
        }
        with patch("sys.stdin", io.StringIO(json.dumps(body))):
            call_command("configure_misp", actor=self.platform.username, stdout=io.StringIO())
        self.source.refresh_from_db()
        event.refresh_from_db()
        self.assertFalse(self.source.enabled)
        self.assertIsNone(self.source.last_success)
        self.assertEqual(event.review_digest, "")
        self.assertEqual(event.payload, self.payload["Event"])

    def test_entire_merge_rolls_back_if_later_event_identity_or_timestamp_regresses(self):
        event = self.refresh()
        previous = event.payload
        second = event_payload(timestamp=1600000000)["Event"]
        second["id"] = "52"
        self.fetch.return_value = [second]
        misp.sync_source(self.source.pk)
        changed = copy.deepcopy(self.payload["Event"])
        changed["info"] = "Must roll back"
        old_second = copy.deepcopy(second)
        old_second["timestamp"] = "1599999999"
        self.fetch.return_value = [changed, old_second]
        with self.assertRaises(ConnectorError):
            misp.sync_source(self.source.pk)
        event.refresh_from_db()
        self.assertEqual(event.payload, previous)
        self.assertFalse(misp.visible_events(self.platform).exists())

    def test_credential_reconfiguration_invalidates_old_worker_even_after_reenable(self):
        import io
        from django.core.management import call_command

        self.refresh()

        def rotate(source):
            body = {"name": source.name, "base_url": source.base_url, "token_env_var": source.token_env_var}
            with patch("sys.stdin", io.StringIO(json.dumps(body))):
                call_command("configure_misp", actor=self.platform.username, stdout=io.StringIO())
            MISPInstance.objects.filter(pk=source.pk).update(enabled=True)
            return [self.payload["Event"]]

        self.fetch.side_effect = rotate
        with self.assertRaises(ConnectorError):
            misp.sync_source(self.source.pk)
        self.assertFalse(misp.visible_events(self.platform).exists())

    def test_configuration_change_during_fetch_refuses_publication(self):
        self.refresh()

        def disable(source):
            MISPInstance.objects.filter(pk=source.pk).update(enabled=False)
            return [self.payload["Event"]]

        self.fetch.side_effect = disable
        with self.assertRaises(ConnectorError):
            misp.sync_source(self.source.pk)
        self.assertFalse(misp.visible_events(self.platform).exists())

    def test_local_research_requires_verified_current_visible_scope_and_dns_boundary(self):
        event = self.refresh()
        misp.grant_readers(
            self.platform, event.pk, [self.analyst], "Synthetic handling review", expected_digest=event.digest
        )
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
        rows, truncated = misp.research(self.analyst, event)
        self.assertEqual({r["organization"].pk for r in rows}, {self.a.pk})
        self.assertFalse(truncated)
        claim.status = "declared"
        claim.save()
        self.assertEqual(misp.research(self.analyst, event)[0], [])
        claim.status, claim.value = "verified", "notexample.invalid"
        claim.save()
        self.assertEqual(misp.research(self.analyst, event)[0], [])
        claim.value, claim.valid_until = "example.invalid", timezone.now() - timedelta(hours=1)
        claim.save()
        self.assertEqual(misp.research(self.analyst, event)[0], [])
        with self.assertRaises(PermissionDenied):
            misp.research(self.admin, event)

    def test_restricted_ui_uses_local_cache_escaped_json_and_csrf_for_research_and_grants(self):
        self.payload["Event"]["info"] = '<script>alert("synthetic")</script>'
        event = self.refresh()
        self.fetch.reset_mock()
        self.login(self.platform)
        response = self.client.get(f"/circl/misp/{event.pk}/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("synthetic")</script>')
        self.assertIn("no-store", response["Cache-Control"])
        self.fetch.assert_not_called()
        from django.test import Client

        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.platform)
        self.assertEqual(csrf.post(f"/circl/misp/{event.pk}/", {"action": "research"}).status_code, 403)
        response = self.client.post(
            f"/circl/misp/{event.pk}/",
            {
                "action": "grant",
                "readers": [self.analyst.pk],
                "note": "Synthetic explicit recipients",
                "expected_digest": event.digest,
                "acknowledged": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.login(self.analyst)
        self.assertEqual(self.client.get(f"/circl/misp/{event.pk}/").status_code, 200)
        self.assertEqual(self.client.post(f"/circl/misp/{event.pk}/", {"action": "grant"}).status_code, 403)


class MISPConnectorTests(TestCase):
    def test_bounded_read_search_uses_only_operator_endpoint_and_stops_at_final_page(self):
        source = MISPInstance(name="MISP", enabled=True)
        row = event_payload()
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic-test-key"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch("portal.connectors.misp.request_json", return_value={"response": [row]}) as http,
        ):
            result = snapshot(source)
        self.assertEqual(result, [row["Event"]])
        args, kwargs = http.call_args
        self.assertEqual(args, ("POST", "https://misppriv.circl.lu/events/restSearch"))
        self.assertFalse(kwargs["json"]["withAttachments"])
        self.assertEqual(kwargs["headers"]["Authorization"], "synthetic-test-key")
        self.assertNotIn("url", kwargs["json"])

    def test_missing_secret_disabled_source_and_unsupported_responses_fail_closed(self):
        source = MISPInstance(name="MISP", enabled=True)
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
                patch("portal.connectors.misp.request_json", return_value=data),
            ):
                with self.assertRaises(ConnectorError):
                    snapshot(source)

    def test_snapshot_size_and_time_budget_do_not_publish_partial_events(self):
        source = MISPInstance(name="MISP", enabled=True)
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch("portal.connectors.misp.request_json", return_value={"response": [event_payload()]}),
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
            http.assert_not_called()

    def test_duplicate_pages_bounds_and_invalid_event_metadata_never_yield_partial_success(self):
        source = MISPInstance(name="MISP", enabled=True)
        rows = []
        for i in range(10):
            row = event_payload()
            row["Event"]["id"] = str(i + 1)
            rows.append(row)
        with (
            patch.dict("os.environ", {"MISP_CIRCL_TOKEN": "synthetic"}),
            patch("portal.connectors.misp.approved_base", return_value=source.base_url),
            patch("portal.connectors.misp.request_json", return_value={"response": rows}),
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
            source = MISPInstance.objects.create(name="Lease fixture", enabled=True)
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
            source = MISPInstance(
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
