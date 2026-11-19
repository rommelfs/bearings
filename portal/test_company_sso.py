"""Constituent SSO proves both identities and leaves application/organization roles explicit."""

import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from django.contrib import auth
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import override_settings
from django.utils import timezone
from social_django.models import UserSocialAuth
from .tests import Fixture
from .test_sso import SSOTests, SETTINGS, ISSUER
from .models import InfrastructureRegistration, Membership, Asset, InventorySource
from .company_sso import plan, finalize
from .sso_onboarding import INTENT
from config.oidc import identity_uid, ApprovedOpenIdConnect
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt


@override_settings(**{**SETTINGS, "SOCIAL_AUTH_OIDC_JWKS_URI": ISSUER + "/onboarding/certs"})
class ConstituentSSOTests(Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key(), as_dict=True)
        cls.jwk.update(kid="synthetic-key", alg="RS256")

    provider = SSOTests.provider
    finish = SSOTests.finish

    def setUp(self):
        ApprovedOpenIdConnect.get_jwks_keys.invalidate()
        self.addCleanup(ApprovedOpenIdConnect.get_jwks_keys.invalidate)
        self.admin.set_password("Local-owner-Only!6428")
        self.admin.save()
        self.item = InfrastructureRegistration.objects.create(
            user=self.admin,
            organization=self.a,
            company_name=self.a.name,
            contact_name="Synthetic Owner",
            email="owner@example.invalid",
            status="approved",
            verification_digest="test-sso-digest",
            verification_expires=timezone.now(),
        )
        self.http = patch("config.oidc.requests.request", side_effect=self.provider).start()
        self.addCleanup(patch.stopall)
        self.claim_overrides = {"sub": "new-constituent-subject"}
        self.userinfo_sub = "new-constituent-subject"
        self.signing_key = self.key
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def begin_link(self):
        response = self.client.post("/account/sso/", {"password": "Local-owner-Only!6428", "checked": "on"})
        self.assertEqual(response.status_code, 302)
        self.params = {k: v[0] for k, v in parse_qs(urlsplit(response.url).query).items()}
        self.assertEqual(self.params["code_challenge_method"], "S256")

    def test_owner_links_signed_subject_then_normal_sso_login_keeps_roles_and_password(self):
        old = self.admin.password
        self.begin_link()
        self.finish()
        binding = UserSocialAuth.objects.get(user=self.admin)
        self.assertEqual(binding.uid, identity_uid(ISSUER, self.userinfo_sub))
        self.assertTrue(binding.extra_data["enabled"])
        self.assertNotIn("access_token", binding.extra_data)
        self.assertNotIn(INTENT, self.client.session if self.client.session.get(INTENT) is not None else {})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.password, old)
        self.assertFalse(self.admin.is_superuser or self.admin.is_staff or self.admin.groups.exists())
        self.client.logout()
        response = self.client.post("/oauth/login/oidc/", {"next": "/account/sso/"})
        self.params = {k: v[0] for k, v in parse_qs(urlsplit(response.url).query).items()}
        self.finish()
        self.assertEqual(int(self.client.session[auth.SESSION_KEY]), self.admin.pk)
        self.assertEqual(self.client.session[auth.BACKEND_SESSION_KEY], "config.oidc.ApprovedOpenIdConnect")

    def test_wrong_password_pending_approval_and_revoked_membership_do_not_start_linking(self):
        response = self.client.post("/account/sso/", {"password": "wrong", "checked": "on"})
        self.assertEqual(response.status_code, 200)
        self.http.assert_not_called()
        self.item.status = "awaiting_review"
        self.item.save()
        self.assertEqual(
            self.client.post(
                "/account/sso/", {"password": "Local-owner-Only!6428", "checked": "on"}
            ).status_code,
            403,
        )
        self.item.status = "approved"
        self.item.save()
        self.begin_link()
        Membership.objects.filter(user=self.admin).delete()
        self.finish()
        self.assertFalse(UserSocialAuth.objects.filter(user=self.admin).exists())

    def test_expired_intent_and_revoked_binding_are_not_restored(self):
        self.begin_link()
        session = self.client.session
        intent = session[INTENT]
        intent["expires"] = time.time() - 1
        session[INTENT] = intent
        session.save()
        self.finish()
        self.assertFalse(UserSocialAuth.objects.filter(user=self.admin).exists())
        UserSocialAuth.objects.create(
            user=self.admin,
            provider="oidc",
            uid=identity_uid(ISSUER, self.userinfo_sub),
            extra_data={"issuer": ISSUER, "subject": self.userinfo_sub, "enabled": False},
        )
        self.assertEqual(
            self.client.post(
                "/account/sso/", {"password": "Local-owner-Only!6428", "checked": "on"}
            ).status_code,
            403,
        )
        self.assertFalse(UserSocialAuth.objects.get(user=self.admin).extra_data["enabled"])

    def test_already_associated_subject_and_matching_email_do_not_reassign_identity(self):
        other = UserSocialAuth.objects.create(
            user=self.reader,
            provider="oidc",
            uid=identity_uid(ISSUER, self.userinfo_sub),
            extra_data={"issuer": ISSUER, "subject": self.userinfo_sub, "enabled": True},
        )
        self.begin_link()
        self.finish()
        other.refresh_from_db()
        self.assertEqual(other.user_id, self.reader.pk)
        self.assertFalse(UserSocialAuth.objects.filter(user=self.admin).exists())

    def test_link_attempts_are_rate_limited_per_owner_without_redirecting_passwords(self):
        for _ in range(11):
            response = self.client.post("/account/sso/", {"password": "wrong", "checked": "on"})
        self.assertContains(response, "Too many identity-link attempts")
        self.http.assert_not_called()
        self.assertFalse(UserSocialAuth.objects.filter(user=self.admin).exists())

    def test_operator_cannot_automatically_restore_a_revoked_binding(self):
        binding = UserSocialAuth.objects.create(
            user=self.admin,
            provider="oidc",
            uid=identity_uid(ISSUER, "revoked-owner"),
            extra_data={"issuer": ISSUER, "subject": "revoked-owner", "enabled": False},
        )
        with self.assertRaises(ValidationError):
            plan(self.platform, self.admin.username, False)
        binding.refresh_from_db()
        self.assertFalse(binding.extra_data["enabled"])

    def test_company_plan_and_empty_source_finalization_reject_changed_or_nonempty_inventory(self):
        with self.assertRaises(ValidationError):
            plan(self.platform, self.admin.username)
        current = plan(self.platform, self.admin.username, False)
        self.a.name = "Changed company display"
        self.a.save()
        # Display metadata does not prove identity; approval/membership and source are rechecked.
        Membership.objects.filter(user=self.admin).update(role="reader")
        with self.assertRaises(PermissionDenied):
            finalize(self.platform, current, {"issuer": ISSUER, "subject": "new-idp"}, None)
        self.assertFalse(UserSocialAuth.objects.filter(user=self.admin).exists())
        Membership.objects.filter(user=self.admin).update(role="admin")
        Asset.objects.filter(organization=self.a).delete()
        source = InventorySource.objects.get(organization=self.a)
        source.mode = "manual"
        source.save()
        current = plan(self.platform, self.admin.username)
        native = {
            "registration": str(self.item.pk),
            "subject": "new-idp",
            "browser_url": "https://localhost:8443",
            "tenant": 22,
            "site": 33,
            "role": 44,
            "device_type": 55,
        }
        result = finalize(self.platform, current, {"issuer": ISSUER, "subject": "new-idp"}, native)
        source.refresh_from_db()
        self.assertEqual(source.mode, "central")
        self.assertEqual(source.tenant_id, 22)
        self.assertEqual(result["subject"], "new-idp")
        self.assertTrue(source.import_requested)


class MISPOrganizationReferenceTests(Fixture):
    def test_platform_attests_uuid_without_changing_membership_and_owner_cannot_reassign_it(self):
        import uuid
        from django.urls import reverse

        value = uuid.uuid4()
        self.login(self.platform)
        url = reverse("admin:portal_organization_change", args=[self.a.pk])
        response = self.client.post(
            url,
            {
                "name": self.a.name,
                "slug": self.a.slug,
                "postal_address": "",
                "operator_visibility": "on",
                "misp_org_uuid": str(value),
                "misp_uuid_attested_by": self.admin.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.misp_org_uuid, value)
        self.assertEqual(self.a.misp_uuid_attested_by, self.platform)
        self.assertIsNotNone(self.a.misp_uuid_attested_at)
        self.assertEqual(Membership.objects.get(user=self.admin, organization=self.a).role, "admin")
        self.login(self.admin)
        self.client.post(
            reverse("company-address", args=[self.a.slug]),
            {"postal_address": "Synthetic office", "misp_org_uuid": str(uuid.uuid4())},
        )
        self.a.refresh_from_db()
        self.assertEqual(self.a.misp_org_uuid, value)
        self.assertContains(self.client.get(reverse("organization", args=[self.a.slug])), str(value))
        self.login(self.platform)
        response = self.client.post(
            reverse("admin:portal_organization_change", args=[self.b.pk]),
            {"name": self.b.name, "slug": self.b.slug, "postal_address": "", "misp_org_uuid": str(value)},
        )
        self.assertEqual(response.status_code, 200)
        self.b.refresh_from_db()
        self.assertIsNone(self.b.misp_org_uuid)
