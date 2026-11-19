"""Customer-native permissions never inherit universal CIRCL access."""

import copy
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from .tests import Fixture
from .models import MISPInstance, MISPServer, InfrastructureClaim, AuditEvent, Membership
from . import misp
from .misp_customer import connect, disconnect
from .misp_credentials import encrypt, decrypt
from .connectors.misp import snapshot
from .connectors.http import ConnectorError
from .test_misp import event_payload
from django.utils import timezone
from datetime import timedelta


@override_settings(SECRET_KEY="synthetic-private-customer-test-encryption-material-64")
class CustomerMISPTests(Fixture):
    def setUp(self):
        self.server = MISPServer.objects.create(
            name="Approved MISP", base_url="https://misp.example.invalid", enabled=True
        )
        self.key = "synthetic-customer-private-key"
        self.payload = event_payload()
        self.http = patch(
            "portal.misp_customer.request_json",
            return_value={"User": {"id": "71", "authkey": "must-not-be-stored"}},
        ).start()
        self.base = patch("portal.misp_customer.approved_base", return_value=self.server.base_url).start()
        self.addCleanup(patch.stopall)

    def connected(self, user=None, org=None):
        return connect(user or self.admin, org or self.a, self.server, self.key)

    def imported(self, source):
        with patch("portal.misp.snapshot", return_value=[self.payload["Event"]]):
            misp.sync_source(source.pk)
        source.refresh_from_db()
        return source.events.get()

    def test_customer_key_is_encrypted_and_does_not_grant_peers_or_circl_access(self):
        source = self.connected()
        self.assertEqual(source.credential_kind, "encrypted")
        self.assertNotIn(self.key, source.credential_ciphertext)
        self.assertEqual(decrypt(source), self.key)
        event = self.imported(source)
        self.assertTrue(misp.visible_events(self.admin).filter(pk=event.pk).exists())
        for user in [self.editor, self.reader, self.analyst, self.platform]:
            self.assertFalse(misp.visible_events(user).filter(pk=event.pk).exists())
        self.assertFalse(AuditEvent.objects.filter(details__icontains=self.key).exists())
        self.assertNotIn("must-not-be-stored", source.credential_ciphertext)

    def test_real_connector_uses_only_customer_key_and_never_circl_cache_for_same_uuid(self):
        source = self.connected()
        circ = MISPInstance.objects.create(
            name="CIRCL universal (synthetic)",
            owner=self.analyst,
            misp_user_id=1,
            enabled=True,
            token_env_var="MISP_UNIVERSAL_TOKEN",
            base_url=self.server.base_url,
        )
        customer = event_payload()["Event"]
        customer["Attribute"] = [{"type": "domain", "value": "customer-visible.example.invalid"}]
        universal = copy.deepcopy(customer)
        universal["Attribute"].append(
            {"type": "domain", "value": "CIRCL-restricted.example.invalid", "distribution": "0"}
        )
        headers = []

        def upstream(method, url, **kwargs):
            token = kwargs["headers"]["Authorization"]
            headers.append(token)
            if url.endswith("/users/view/me"):
                return {"User": {"id": 71 if token == self.key else 1}}
            return {"response": [{"Event": customer if token == self.key else universal}]}

        with (
            patch.dict(
                "os.environ",
                {"MISP_UNIVERSAL_TOKEN": "synthetic-circl-key", source.token_env_var: "must-not-fallback"},
            ),
            patch("portal.connectors.misp.approved_base", return_value=self.server.base_url),
            patch("portal.connectors.misp.request_json", side_effect=upstream),
        ):
            misp.sync_source(source.pk)
            self.assertEqual(headers, [self.key, self.key])
            misp.sync_source(circ.pk)
        customer_event = misp.visible_events(self.admin).get()
        circ_event = misp.visible_events(self.analyst).get()
        self.assertNotEqual(customer_event.pk, circ_event.pk)
        self.assertNotIn("CIRCL-restricted", str(customer_event.payload))
        self.assertIn("CIRCL-restricted", str(circ_event.payload))

    def test_cipher_tamper_different_owner_and_missing_key_have_no_environment_fallback(self):
        source = self.connected()
        other = self.connected(self.editor)
        other.credential_ciphertext = source.credential_ciphertext
        with self.assertRaises(ConnectorError):
            decrypt(other)
        source.credential_ciphertext = "invalid-encrypted-data"
        source.save(update_fields=["credential_ciphertext"])
        with (
            patch.dict("os.environ", {source.token_env_var: "universal-must-not-be-used"}),
            patch("portal.connectors.misp.request_json") as http,
        ):
            with self.assertRaises(ConnectorError):
                snapshot(source)
            http.assert_not_called()
        source.credential_ciphertext = ""
        with self.assertRaises(ConnectorError):
            decrypt(source)

    def test_current_membership_and_server_approval_control_read_and_refresh(self):
        source = self.connected()
        event = self.imported(source)
        Membership.objects.filter(user=self.admin, organization=self.a).delete()
        self.assertFalse(misp.visible_events(self.admin).exists())
        with self.assertRaises(PermissionDenied):
            self.connected()
        Membership.objects.create(user=self.admin, organization=self.a, role="reader")
        self.assertTrue(misp.visible_events(self.admin).filter(pk=event.pk).exists())
        Membership.objects.filter(user=self.admin, organization=self.a).delete()
        self.login(self.admin)
        response = self.client.get("/misp/connections/")
        self.assertNotContains(response, self.a.name)
        self.assertContains(response, "Remove my inactive personal key")
        self.assertEqual(
            self.client.post("/misp/connections/", {"action": "disconnect", "source": source.pk}).status_code,
            302,
        )
        source.refresh_from_db()
        self.assertEqual(source.credential_ciphertext, "")
        Membership.objects.create(user=self.admin, organization=self.a, role="reader")
        self.server.enabled = False
        self.server.save()
        self.assertFalse(misp.visible_events(self.admin).exists())
        with self.assertRaises(ValidationError):
            self.connected()

    def test_customer_research_stays_in_connection_company_even_if_user_has_two_memberships(self):
        Membership.objects.create(user=self.admin, organization=self.b, role="admin")
        for org in [self.a, self.b]:
            InfrastructureClaim.objects.create(
                organization=org,
                kind="domain",
                value="example.invalid",
                status="verified",
                valid_from=timezone.now() - timedelta(days=1),
            )
        source = self.connected()
        event = self.imported(source)
        rows, _ = misp.research(self.admin, event)
        self.assertEqual({r["organization"].pk for r in rows}, {self.a.pk})
        other = self.connected(org=self.b)
        self.imported(other)
        self.assertEqual(misp.visible_events(self.admin).count(), 2)

    def test_rotation_keeps_native_identity_and_disconnect_erases_key_without_deleting_cache(self):
        source = self.connected()
        self.imported(source)
        old = source.credential_ciphertext
        self.http.return_value = {"User": {"id": "99"}}
        with self.assertRaises(ValidationError):
            self.connected()
        source.refresh_from_db()
        self.assertEqual(source.credential_ciphertext, old)
        self.http.return_value = {"User": {"id": "71"}}
        rotated = self.connected()
        self.assertEqual(rotated.pk, source.pk)
        self.assertIsNone(rotated.last_success)
        self.assertFalse(misp.visible_events(self.admin).exists())
        self.imported(rotated)
        disconnect(self.admin, source.pk)
        source.refresh_from_db()
        self.assertFalse(source.enabled)
        self.assertEqual(source.credential_ciphertext, "")
        self.assertTrue(source.events.exists())
        self.assertFalse(misp.visible_events(self.admin).exists())
        with self.assertRaises(MISPInstance.DoesNotExist):
            disconnect(self.editor, source.pk)

    def test_failed_native_probe_or_changed_approval_never_creates_a_connection(self):
        self.http.side_effect = ConnectorError("Synthetic key unavailable")
        with self.assertRaises(ConnectorError):
            self.connected()
        self.assertFalse(MISPInstance.objects.exists())

        def revoked(*args, **kwargs):
            MISPServer.objects.filter(pk=self.server.pk).update(enabled=False)
            return {"User": {"id": "71"}}

        self.http.side_effect = revoked
        with self.assertRaises(ValidationError):
            self.connected()
        self.assertFalse(MISPInstance.objects.exists())

    def test_ui_is_optional_write_only_csrf_protected_and_rejects_foreign_company(self):
        self.login(self.admin)
        response = self.client.get("/misp/connections/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.server.base_url)
        data = {
            "action": "connect",
            "organization": self.a.pk,
            "server": self.server.pk,
            "api_key": self.key,
            "consent": "on",
        }
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post("/misp/connections/", data).status_code, 403)
        self.assertEqual(self.client.post("/misp/connections/", data).status_code, 302)
        self.assertNotContains(self.client.get("/misp/connections/"), self.key)
        response = self.client.post("/misp/connections/", {**data, "organization": self.b.pk})
        self.assertContains(response, "Select a valid choice")
        self.assertNotContains(response, self.key)
        source = MISPInstance.objects.get()
        event = self.imported(source)
        self.assertEqual(self.client.get(f"/misp/events/{event.pk}/").status_code, 200)
        self.login(self.analyst)
        self.assertEqual(self.client.get(f"/misp/events/{event.pk}/").status_code, 404)
        self.login(self.admin)
        self.assertEqual(
            self.client.post("/misp/connections/", {"action": "disconnect", "source": "bad"}).status_code, 404
        )

    @override_settings(
        SECRET_KEY="new-test-encryption-secret-material-long-enough",
        SECRET_KEY_FALLBACKS=["old-test-encryption-secret-material-long-enough"],
    )
    def test_documented_django_secret_rotation_can_decrypt_with_explicit_fallback(self):
        source = MISPInstance(owner=self.admin, organization=self.a)
        with override_settings(SECRET_KEY="old-test-encryption-secret-material-long-enough"):
            value = encrypt(source, self.key)
        source.credential_ciphertext = value
        self.assertEqual(decrypt(source), self.key)
        with override_settings(SECRET_KEY_FALLBACKS=[]):
            with self.assertRaises(ConnectorError):
                decrypt(source)

    def test_customer_environment_key_cannot_borrow_the_universal_staff_key(self):
        source = MISPInstance(
            owner=self.admin,
            organization=self.a,
            server=self.server,
            misp_user_id=1,
            name="Wrong universal source",
            token_env_var="MISP_UNIVERSAL_TOKEN",
            enabled=True,
        )
        with self.assertRaises(ValidationError):
            source.full_clean()

    def test_disconnect_allows_new_misp_identity_without_reassigning_old_cache(self):
        old = self.connected()
        event = self.imported(old)
        disconnect(self.admin, old.pk)
        self.http.return_value = {"User": {"id": "99"}}
        new = self.connected()
        self.assertNotEqual(new.pk, old.pk)
        self.assertEqual(new.misp_user_id, 99)
        event.refresh_from_db()
        self.assertEqual(event.source_id, old.pk)
        self.assertFalse(misp.visible_events(self.admin).exists())

    def test_default_development_secret_cannot_store_a_key_and_probes_are_limited(self):
        with override_settings(SECRET_KEY="development-only-unsafe-key-do-not-deploy"):
            with self.assertRaises(ValidationError):
                self.connected()
        self.http.assert_not_called()
        now = timezone.now()
        with patch("portal.misp_customer.timezone.now", return_value=now):
            self.http.side_effect = ConnectorError("Bad synthetic key")
            for _ in range(10):
                with self.assertRaises(ConnectorError):
                    self.connected()
            with self.assertRaises(ValidationError):
                self.connected()
        self.assertEqual(self.http.call_count, 10)

    def test_server_url_cannot_be_repointed_under_a_personal_key(self):
        self.connected()
        self.server.base_url = "https://other.example.invalid"
        with self.assertRaises(ValidationError):
            self.server.full_clean()
