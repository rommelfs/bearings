"""Resumption, approval, autosave conflicts, scoped inventory and manual AIL handoff."""

import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from django.db import connection, connections, close_old_connections, transaction
from django.test import TransactionTestCase
from datetime import datetime, timezone as dt_timezone
from django.test import Client, override_settings
from django.urls import reverse
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID
from .tests import Fixture
from .models import (
    AuditEvent,
    Asset,
    ConfigurationSection,
    InfrastructureClaim,
    InventoryWrite,
    Membership,
    OrganizationConfiguration,
)
from .configuration import digest, progress
from .configuration_forms import PublicKeysForm
from .registration import submit_registration, verify_registration, issue_verification, decide_registration
from .registration_forms import InfrastructureRegistrationForm
from .inventory_review import snapshot


def public_material():
    numbers = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_numbers()

    def mpi(n):
        return n.bit_length().to_bytes(2, "big") + n.to_bytes((n.bit_length() + 7) // 8, "big")

    packet = b"\x04" + b"\0" * 4 + b"\x01" + mpi(numbers.n) + mpi(numbers.e)
    raw = b"\xc6\xff" + len(packet).to_bytes(4, "big") + packet
    pgp = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n"
        + base64.b64encode(raw).decode()
        + "\n-----END PGP PUBLIC KEY BLOCK-----"
    )
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic contact")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime(2026, 1, 1, tzinfo=dt_timezone.utc))
        .not_valid_after(datetime(2027, 1, 1, tzinfo=dt_timezone.utc))
        .sign(key, None)
    )
    return pgp, cert.public_bytes(serialization.Encoding.PEM).decode()


class ConfigurationTests(Fixture):
    def setUp(self):
        self.login()
        self.sa.mode = "manual"
        self.sa.save()

    def address(self, section="scope", guided=False, org=None):
        return reverse(
            "setup-section" if guided else "configuration-section", args=[(org or self.a).slug, section]
        )

    def save(self, section, data, action="save", guided=False, baseline=None, revision=None):
        state = ConfigurationSection.objects.filter(organization=self.a, section=section).first()
        return self.client.post(
            self.address(section, guided),
            {
                "revision": revision if revision is not None else state.revision if state else 0,
                "baseline": baseline if baseline is not None else digest(self.a, section),
                "action": action,
                **data,
            },
            HTTP_ACCEPT="application/json",
        )

    def test_owner_only_private_headers_and_csrf(self):
        response = self.client.get(self.address())
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        for user in [self.reader, self.editor, self.analyst]:
            self.login(user)
            self.assertEqual(self.client.get(self.address()).status_code, 403)
            self.assertEqual(self.save("scope", {"domains": "private.invalid"}).status_code, 403)
        self.login()
        self.assertEqual(self.client.get(self.address(org=self.b)).status_code, 404)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(self.address(), {"domains": "private.invalid"}).status_code, 403)
        self.assertFalse(self.b.configuration_sections.exists())

    def test_approval_gate_and_revocation_do_not_hide_individual_settings(self):
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.address(guided=True)).status_code, 403)
        self.assertEqual(self.client.get(self.address()).status_code, 200)
        self.assertEqual(self.save("scope", {"domains": "alpha.invalid"}, guided=True).status_code, 403)
        self.a.operator_visibility = True
        self.a.save()
        self.assertEqual(self.client.get(self.address(guided=True)).status_code, 200)
        response = self.save("scope", {"domains": "alpha.invalid"}, guided=True)
        self.assertEqual(response.status_code, 200)
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.save("scope", {"domains": "other.invalid"}, guided=True).status_code, 403)
        self.assertTrue(self.a.claims.filter(value="alpha.invalid").exists())

    def test_scope_normalization_withdrawal_retains_verified_and_invalid_drafts(self):
        verified = InfrastructureClaim.objects.create(
            organization=self.a, kind="domain", value="verified.invalid", status="verified"
        )
        response = self.save(
            "scope",
            {"domains": "ALPHA.invalid.\nalpha.invalid", "networks": "192.0.2.0/24", "ips": "2001:db8::1"},
        )
        self.assertTrue(response.json()["valid"])
        self.assertEqual(self.a.claims.filter(status="declared").count(), 3)
        response = self.save("scope", {"ips": "invalid address"})
        self.assertFalse(response.json()["valid"])
        self.assertEqual(self.a.claims.filter(status="declared").count(), 3)
        response = self.client.get(self.address())
        self.assertEqual(response.context["form"]["ips"].value(), "invalid address")
        response = self.save("scope", {"domains": "alpha.invalid"}, "complete")
        self.assertTrue(response.json()["valid"])
        self.assertEqual(self.a.claims.filter(status="declared").count(), 1)
        self.assertEqual(self.a.claims.filter(status="expired").count(), 2)
        verified.refresh_from_db()
        self.assertEqual(verified.status, "verified")
        self.assertEqual(progress(self.a)["done"], 1)

    def test_revision_and_individual_editor_changes_are_conflicts(self):
        baseline = digest(self.a, "scope")
        self.save("scope", {"domains": "first.invalid"})
        response = self.save("scope", {"domains": "lost.invalid"}, baseline=baseline, revision=0)
        self.assertEqual(response.status_code, 409)
        baseline = digest(self.a, "scope")
        InfrastructureClaim.objects.create(organization=self.a, kind="domain", value="outside.invalid")
        response = self.save("scope", {"domains": "lost.invalid"}, baseline=baseline)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.a.claims.filter(value="lost.invalid").exists())

    def test_multiple_contexts_are_not_merged_and_scope_completion_requires_real_data(self):
        response = self.save("scope", {}, "complete")
        self.assertFalse(response.json()["valid"])
        for context in ["office", "lab"]:
            InfrastructureClaim.objects.create(
                organization=self.a, kind="network", value="10.0.0.0/24", network_context=context
            )
        response = self.save("scope", {"networks": "10.0.0.0/24"})
        self.assertFalse(response.json()["valid"])
        self.assertEqual(self.a.claims.filter(status="declared").count(), 2)

    def test_inventory_autosave_is_idempotent_scoped_local_and_resumable(self):
        data = {
            "asset_name": "wizard-server",
            "asset_kind": "server",
            "software_name": "Unknown demo OS",
            "version": "1.0",
            "is_operating_system": "on",
            "notes": "More hosts later",
        }
        before = InventoryWrite.objects.count()
        self.assertTrue(self.save("inventory", data).json()["valid"])
        asset = Asset.objects.get(name="wizard-server")
        self.assertEqual(asset.state, "recorded")
        self.assertTrue(self.save("inventory", {**data, "version": "1.1"}).json()["valid"])
        self.assertEqual(Asset.objects.filter(name="wizard-server").count(), 1)
        self.assertEqual(asset.installations.count(), 1)
        self.assertEqual(asset.installations.get().version, "1.1")
        self.assertTrue(asset.installations.get().is_operating_system)
        self.assertEqual(InventoryWrite.objects.count(), before)
        self.assertEqual(
            self.client.get(self.address("inventory")).context["form"]["asset_name"].value(), "wizard-server"
        )
        self.assertTrue(self.save("inventory", data, "another").json()["valid"])
        response = self.client.get(self.address("inventory"))
        self.assertFalse(response.context["form"]["asset_name"].value())
        self.save("inventory", {**data, "asset_name": "second-server"})
        self.assertEqual(Asset.objects.filter(organization=self.a, name__endswith="server").count(), 2)
        self.assertEqual(InventoryWrite.objects.count(), before)

    def test_nonmanual_inventory_cannot_be_written_by_autosave(self):
        self.sa.mode = "development"
        self.sa.save()
        response = self.save("inventory", {"asset_name": "not-written", "software_name": "Not written"})
        self.assertTrue(response.json()["valid"])
        self.assertFalse(Asset.objects.filter(name="not-written").exists())
        self.assertNotIn("asset_name", self.client.get(self.address("inventory")).context["form"].fields)

    def test_ail_export_separates_tokens_escapes_literals_and_never_sends_mail(self):
        data = {
            "enabled": "on",
            "keywords": 'Company "A"\nCompany "A"\nBack\\slash',
            "honeytokens": "Exact-Token",
            "notification_email": "noc@example.invalid",
        }
        response = self.save("ail", data, "complete")
        self.assertTrue(response.json()["valid"])
        profile = OrganizationConfiguration.objects.get(organization=self.a)
        self.assertEqual(len(profile.ail_keywords), 2)
        self.assertEqual(profile.ail_honeytokens, ["Exact-Token"])
        result = self.client.post(reverse("configuration-ail-export", args=[self.a.slug]))
        self.assertEqual(result.status_code, 200)
        self.assertIn('filename="bearings-ail.yar"', result.headers["Content-Disposition"])
        content = result.content.decode()
        self.assertIn(r"Company \x22A\x22", content)
        self.assertIn(r"Back\x5cslash", content)
        self.assertIn('"Exact-Token"\n', content)
        self.assertIn('"keywords"', content)
        self.assertIn('"honeytokens"', content)
        self.assertNotIn("noc@example.invalid", content)
        self.assertNotIn("Exact-Token", str(list(AuditEvent.objects.values("details"))))
        self.save("ail", {"enabled": "on", "keywords": ""})
        self.assertEqual(
            self.client.post(reverse("configuration-ail-export", args=[self.a.slug])).status_code, 302
        )
        self.login(self.analyst)
        self.assertEqual(
            self.client.post(reverse("configuration-ail-export", args=[self.a.slug])).status_code, 403
        )

    def test_progress_is_setup_review_not_fake_inventory_coverage_and_can_resume(self):
        self.contact.emergency_phone = "+352123456"
        self.contact.save()
        self.save("scope", {"domains": "alpha.invalid"}, "complete")
        self.save("inventory", {}, "complete")
        self.save("ail", {}, "complete")
        self.save("contacts", {"postal_address": "L-1111 Luxembourg"}, "complete")
        self.assertEqual(progress(self.a)["percent"], 100)
        resume = self.client.get(reverse("setup-resume", args=[self.a.slug]))
        self.assertRedirects(resume, self.address("contacts", guided=True))
        self.save("scope", {"domains": "another.invalid"})
        self.assertEqual(progress(self.a)["percent"], 75)
        self.asset.lifecycle = "retired"
        self.asset.save()
        self.assertEqual(progress(self.a)["percent"], 50)

    def test_oversized_and_rejected_private_material_are_not_saved_as_drafts(self):
        result = self.save(
            "contacts",
            {
                "pgp_public_key": "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsecret\n-----END PGP PRIVATE KEY BLOCK-----",
                "postal_address": "x" * 1100,
            },
        )
        self.assertFalse(result.json()["valid"])
        state = ConfigurationSection.objects.get(organization=self.a, section="contacts")
        self.assertNotIn("secret", str(state.draft))
        self.assertNotIn("postal_address", state.draft)
        self.assertIn("postal_address", result.json()["unsaved_fields"])
        self.assertFalse(OrganizationConfiguration.objects.filter(organization=self.a).exists())

    def test_current_public_keys_are_visible_to_permitted_circl_but_not_ail_indicators(self):
        pgp, smime = public_material()
        OrganizationConfiguration.objects.create(
            organization=self.a,
            pgp_public_key=pgp,
            smime_certificate=smime,
            ail_keywords=["private-keyword-canary"],
            ail_honeytokens=["private-honeytoken-canary"],
        )
        self.login(self.analyst)
        response = self.client.get(reverse("organization", args=[self.a.slug]))
        self.assertContains(response, "BEGIN PGP PUBLIC KEY BLOCK")
        self.assertContains(response, "BEGIN CERTIFICATE")
        self.assertNotContains(response, "private-keyword-canary")
        self.assertNotContains(response, "private-honeytoken-canary")
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(reverse("organization", args=[self.a.slug])).status_code, 404)

    def test_public_key_changes_invalidate_inventory_review_snapshot(self):
        before, _ = snapshot(self.a)
        pgp, smime = public_material()
        response = self.save("contacts", {"pgp_public_key": pgp, "smime_certificate": smime})
        self.assertTrue(response.json()["valid"])
        self.assertNotEqual(before, snapshot(self.a)[0])
        profile = OrganizationConfiguration.objects.get(organization=self.a)
        self.assertEqual(profile.pgp_public_key, pgp)
        self.assertEqual(profile.smime_certificate, smime.strip())
        self.assertNotIn(pgp, str(list(AuditEvent.objects.values("details"))))


class PublicKeyTests(Fixture):
    def test_public_material_is_optional_format_checked_and_private_material_refused(self):
        self.assertTrue(PublicKeysForm({}).is_valid())
        pgp, smime = public_material()
        self.assertTrue(PublicKeysForm({"pgp_public_key": pgp, "smime_certificate": smime}).is_valid())
        raw = b"\xc5\x08" + b"\x04" * 8
        fake = (
            "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
            + base64.b64encode(raw).decode()
            + "\n-----END PGP PUBLIC KEY BLOCK-----"
        )
        for values in [
            {"pgp_public_key": fake},
            {"pgp_public_key": "bad"},
            {"smime_certificate": smime + smime},
            {"smime_certificate": "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"},
        ]:
            self.assertFalse(PublicKeysForm(values).is_valid())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        SERVICE_MAIL_TRANSPORT="file",
        PUBLIC_BASE_URL="https://example.invalid",
    )
    def test_registration_keys_copy_on_mail_proof_wizard_waits_for_circl(self):
        import re
        from django.core import mail

        pgp, smime = public_material()
        form = InfrastructureRegistrationForm(
            {
                "username": "new-owner",
                "company_name": "New company",
                "first_name": "Synthetic",
                "last_name": "Owner",
                "job_title": "Security officer",
                "email": "new@example.invalid",
                "emergency_phone": "+352123456",
                "pgp_public_key": pgp,
                "smime_certificate": smime,
                "consent": "on",
                "attestation": "on",
                "periodic_consent": "on",
                "updates_consent": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        item = submit_registration(form)
        self.assertEqual(item.scopes, [])
        self.assertTrue(issue_verification(item.pk))
        code = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body)[1]
        item = verify_registration(code, "Synthetic-password-Only!247")
        self.assertEqual(item.organization.configuration.pgp_public_key, pgp)
        self.assertEqual(item.organization.configuration.smime_certificate, smime.strip())
        self.client.force_login(item.user)
        self.assertEqual(self.client.get(self.address_for(item.organization)).status_code, 403)
        decide_registration(self.analyst, item.pk, "approve", "Synthetic review")
        self.assertEqual(self.client.get(self.address_for(item.organization)).status_code, 200)
        Membership.objects.filter(user=item.user).delete()
        self.assertEqual(self.client.get(self.address_for(item.organization)).status_code, 404)

    def address_for(self, org):
        return reverse("setup-section", args=[org.slug, "scope"])


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL source-lock contention")
class ConfigurationConcurrencyTests(TransactionTestCase):
    def test_busy_inventory_source_retains_draft_without_waiting_on_org_fk(self):
        from django.contrib.auth import get_user_model
        from .models import Organization, InventorySource

        user = get_user_model().objects.create_user("configuration-owner")
        org = Organization.objects.create(
            name="Synthetic concurrent company", slug="concurrent-setup", operator_visibility=True
        )
        Membership.objects.create(user=user, organization=org, role="admin")
        source = InventorySource.objects.create(organization=org, mode="manual")
        acquired, release = Event(), Event()

        def writer():
            close_old_connections()
            try:
                with transaction.atomic():
                    InventorySource.objects.select_for_update().get(pk=source.pk)
                    acquired.set()
                    release.wait(5)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            try:
                self.assertTrue(acquired.wait(3))
                self.client.force_login(user)
                response = self.client.post(
                    reverse("configuration-section", args=[org.slug, "inventory"]),
                    {
                        "revision": "0",
                        "baseline": digest(org, "inventory"),
                        "asset_name": "pending-host",
                        "asset_kind": "server",
                        "action": "save",
                    },
                    HTTP_ACCEPT="application/json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["valid"])
                self.assertIn("being updated", str(response.json()["errors"]))
                self.assertFalse(Asset.objects.filter(organization=org).exists())
                self.assertEqual(
                    ConfigurationSection.objects.get(organization=org).draft["asset_name"], "pending-host"
                )
            finally:
                release.set()
                future.result(timeout=5)
