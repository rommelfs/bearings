import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib import auth
from django.test import Client, override_settings
from social_django.models import UserSocialAuth
from config.oidc import identity_uid
from . import tests
from .models import Membership

ISSUER = "https://idp.example.invalid/realms/bearings"
SETTINGS = dict(
    SSO_ENABLED=True,
    SSO_ISSUER=ISSUER,
    SSO_SESSION_SECONDS=1800,
    AUTHENTICATION_BACKENDS=[
        "django.contrib.auth.backends.ModelBackend",
        "config.oidc.ApprovedOpenIdConnect",
    ],
    SOCIAL_AUTH_OIDC_ID_TOKEN_ISSUER=ISSUER,
    SOCIAL_AUTH_OIDC_KEY="bearings",
    SOCIAL_AUTH_OIDC_SECRET="synthetic-client-secret",
    SOCIAL_AUTH_OIDC_VERIFY_SSL=True,
    SOCIAL_AUTH_OIDC_AUTHORIZATION_URL=ISSUER + "/auth",
    SOCIAL_AUTH_OIDC_ACCESS_TOKEN_URL=ISSUER + "/token",
    SOCIAL_AUTH_OIDC_USERINFO_URL=ISSUER + "/userinfo",
    SOCIAL_AUTH_OIDC_JWKS_URI=ISSUER + "/certs",
)


@override_settings(**SETTINGS)
class SSOTests(tests.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key(), as_dict=True)
        cls.jwk.update(kid="synthetic-key", alg="RS256")

    def setUp(self):
        self.binding = UserSocialAuth.objects.create(
            user=self.admin,
            provider="oidc",
            uid=identity_uid(ISSUER, "subject-alice"),
            extra_data={
                "issuer": ISSUER,
                "subject": "subject-alice",
                "enabled": True,
                "generation": "test-generation",
            },
        )
        self.http = patch("config.oidc.requests.request", side_effect=self.provider).start()
        self.addCleanup(patch.stopall)
        self.claim_overrides = {}
        self.userinfo_sub = "subject-alice"
        self.signing_key = self.key

    def start(self, next_url="/issues/"):
        response = self.client.post("/oauth/login/oidc/", {"next": next_url})
        self.assertEqual(response.status_code, 302)
        self.params = {key: value[0] for key, value in parse_qs(urlsplit(response.url).query).items()}
        return response

    def provider(self, method, url, **kwargs):
        self.assertTrue(kwargs["verify"])
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], 10)
        now = int(time.time())
        if url.endswith("/token"):
            verifier = kwargs["data"]["code_verifier"]
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            )
            self.assertEqual(challenge, self.params["code_challenge"])
            claims = {
                "iss": ISSUER,
                "sub": "subject-alice",
                "aud": "bearings",
                "exp": now + 300,
                "iat": now,
                "nonce": self.params["nonce"],
                **self.claim_overrides,
            }
            claims = {k: v for k, v in claims.items() if v is not None}
            payload = {
                "access_token": "synthetic-access-token",
                "id_token": jwt.encode(
                    claims, self.signing_key, algorithm="RS256", headers={"kid": "synthetic-key"}
                ),
            }
        elif url.endswith("/certs"):
            payload = {"keys": [self.jwk]}
        elif url.endswith("/userinfo"):
            payload = {
                "sub": self.userinfo_sub,
                "email": self.admin.email,
                "preferred_username": "platform",
                "groups": ["CIRCL analysts"],
                "is_superuser": True,
            }
        else:
            raise AssertionError("Unexpected provider URL")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        response._content_consumed = True
        return response

    def finish(self, **params):
        return self.client.get(
            "/oauth/complete/oidc/",
            {"code": "synthetic-once-only-code", "state": self.params["state"], **params},
        )

    def test_real_signed_code_flow_pkce_nonce_and_roles_remain_local(self):
        self.start()
        self.assertEqual(self.params["code_challenge_method"], "S256")
        response = self.finish()
        self.assertRedirects(response, "/issues/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session[auth.SESSION_KEY]), self.admin.pk)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)
        self.assertFalse(self.admin.groups.exists())
        self.assertEqual(Membership.objects.get(user=self.admin).role, "admin")
        self.binding.refresh_from_db()
        self.assertNotIn("access_token", self.binding.extra_data)
        self.assertNotIn("id_token", self.binding.extra_data)
        self.assertEqual(self.client.get("/issues/").status_code, 200)

    def test_unapproved_same_email_does_not_create_or_link_account(self):
        self.claim_overrides = {"sub": "unapproved"}
        self.userinfo_sub = "unapproved"
        before = self.admin.__class__.objects.count()
        self.start()
        self.assertRedirects(self.finish(), "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn(auth.SESSION_KEY, self.client.session)
        self.assertEqual(self.admin.__class__.objects.count(), before)
        self.assertEqual(UserSocialAuth.objects.count(), 1)

    def test_invalid_issuer_audience_expiry_required_claims_nonce_and_signature_fail_closed(self):
        for field, value in [
            ("iss", "https://other.example.invalid"),
            ("aud", "netbox"),
            ("exp", int(time.time()) - 60),
            ("exp", None),
            ("iat", int(time.time()) + 300),
            ("nonce", "wrong"),
        ]:
            with self.subTest(field=field, value=value):
                self.client = Client()
                self.claim_overrides = {field: value}
                self.start()
                self.assertRedirects(self.finish(), "/accounts/login/", fetch_redirect_response=False)
                self.assertNotIn(auth.SESSION_KEY, self.client.session)
        self.claim_overrides = {}
        self.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.client = Client()
        self.start()
        self.assertRedirects(self.finish(), "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn(auth.SESSION_KEY, self.client.session)

    def test_state_replay_and_userinfo_subject_mismatch_denied(self):
        self.start()
        self.assertRedirects(self.finish(state="wrong"), "/accounts/login/", fetch_redirect_response=False)
        self.http.assert_not_called()
        self.userinfo_sub = "someone-else"
        self.start()
        self.assertRedirects(self.finish(), "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn(auth.SESSION_KEY, self.client.session)
        self.userinfo_sub = "subject-alice"
        self.start()
        self.finish()
        self.client.post("/accounts/logout/")
        self.assertRedirects(self.finish(), "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn(auth.SESSION_KEY, self.client.session)

    def test_revoked_disabled_and_expired_sessions_end_without_changing_local_password_access(self):
        self.admin.set_password("synthetic-local-emergency-password")
        self.admin.save()
        self.start()
        self.finish()
        self.binding.delete()
        self.assertEqual(self.client.get("/issues/").status_code, 302)
        self.assertNotIn(auth.SESSION_KEY, self.client.session)
        self.assertTrue(
            self.client.login(username=self.admin.username, password="synthetic-local-emergency-password")
        )
        self.assertEqual(self.client.get("/issues/").status_code, 200)
        self.client.logout()
        self.binding = UserSocialAuth.objects.create(
            user=self.admin,
            provider="oidc",
            uid=identity_uid(ISSUER, "subject-alice"),
            extra_data={
                "issuer": ISSUER,
                "subject": "subject-alice",
                "enabled": True,
                "generation": "test-generation",
            },
        )
        self.start()
        self.finish()
        session = self.client.session
        session["bearings_sso_started"] = time.time() - 1801
        session.save()
        self.assertEqual(self.client.get("/issues/").status_code, 302)
        self.start()
        self.finish()
        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(self.client.get("/issues/").status_code, 302)

    def test_issuer_rebinding_open_redirect_and_arbitrary_backend_are_denied(self):
        self.assertNotEqual(
            identity_uid(ISSUER, "subject-alice"), identity_uid(ISSUER + "-other", "subject-alice")
        )
        self.start("https://attacker.example.invalid/")
        self.assertRedirects(self.finish(), "/", fetch_redirect_response=False)
        self.assertEqual(self.client.post("/oauth/login/unapproved/").status_code, 404)
        self.http.assert_called()

    @override_settings(SSO_ENABLED=False)
    def test_optional_feature_off_retains_local_login(self):
        self.assertNotContains(self.client.get("/accounts/login/"), "Sign in with SSO")
        self.assertRedirects(
            self.client.post("/oauth/login/oidc/"), "/accounts/login/", fetch_redirect_response=False
        )
        self.http.assert_not_called()

    def test_operator_link_revoke_tombstone_cannot_reassign_or_restore_old_session(self):
        from django.core.management import call_command, CommandError

        self.start()
        self.finish()
        old_cookie = self.client.cookies.copy()
        with self.assertRaises(CommandError):
            call_command(
                "link_oidc_identity",
                actor=self.admin.username,
                username=self.admin.username,
                subject="subject-alice",
            )
        call_command(
            "link_oidc_identity",
            actor=self.platform.username,
            username=self.admin.username,
            subject="subject-alice",
            revoke=True,
        )
        self.binding.refresh_from_db()
        self.assertFalse(self.binding.extra_data["enabled"])
        with self.assertRaises(CommandError):
            call_command(
                "link_oidc_identity",
                actor=self.platform.username,
                username=self.platform.username,
                subject="subject-alice",
            )
        call_command(
            "link_oidc_identity",
            actor=self.platform.username,
            username=self.admin.username,
            subject="subject-alice",
        )
        self.start()
        self.finish()
        old = Client()
        old.cookies = old_cookie
        self.assertEqual(old.get("/issues/").status_code, 302)
        self.assertEqual(self.client.get("/issues/").status_code, 200)

    def test_multi_audience_authorized_party_must_match_client(self):
        self.claim_overrides = {"aud": ["bearings", "netbox"], "azp": "netbox"}
        self.start()
        self.assertRedirects(self.finish(), "/accounts/login/", fetch_redirect_response=False)
        self.assertNotIn(auth.SESSION_KEY, self.client.session)

    def test_redirects_arbitrary_endpoints_and_large_provider_responses_are_refused(self):
        from config.oidc import ApprovedOpenIdConnect
        from social_core.exceptions import AuthForbidden, AuthTokenError

        backend = ApprovedOpenIdConnect()
        with self.assertRaises(AuthForbidden):
            backend.request("https://attacker.example.invalid/token")
        self.http.assert_not_called()
        response = requests.Response()
        response.status_code = 302
        response._content = b""
        response._content_consumed = True
        self.http.side_effect = None
        self.http.return_value = response
        with self.assertRaises(AuthTokenError):
            backend.request(ISSUER + "/token")
        response.status_code = 200
        response._content = b"x" * 1_000_001
        with self.assertRaises(AuthTokenError):
            backend.request(ISSUER + "/certs")

    def test_provider_errors_do_not_echo_sensitive_error_details(self):
        self.start()
        self.http.side_effect = requests.RequestException("synthetic-sensitive-provider-detail")
        result = self.finish()
        self.assertRedirects(result, "/accounts/login/", fetch_redirect_response=False)
        page = self.client.get(result.url)
        self.assertNotContains(page, "synthetic-sensitive-provider-detail")
        self.assertContains(page, "SSO sign-in failed")
        self.assertNotIn(auth.SESSION_KEY, self.client.session)

    def test_login_initiation_requires_post_and_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.get("/oauth/login/oidc/").status_code, 405)
        self.assertEqual(strict.post("/oauth/login/oidc/").status_code, 403)
        self.http.assert_not_called()

    def test_legacy_lab_ca_upgrade_preserves_key_and_existing_server_chain(self):
        import subprocess
        import tempfile
        from pathlib import Path
        from docker.sso.trust import ensure_ca_usage

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def openssl(*args):
                return subprocess.run(
                    ["openssl", *[str(arg) for arg in args]], check=True, capture_output=True
                )

            key, cert = root / "ca.key", root / "ca.crt"
            openssl(
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "2",
                "-subj",
                "/CN=Bearings isolated development CA",
                "-keyout",
                key,
                "-out",
                cert,
            )
            before = key.read_bytes()
            leaf_key, csr, leaf = root / "server.key", root / "server.csr", root / "server.crt"
            openssl(
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=localhost",
                "-keyout",
                leaf_key,
                "-out",
                csr,
            )
            config = root / "server.cnf"
            config.write_text(
                "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n"
            )
            openssl(
                "x509",
                "-req",
                "-in",
                csr,
                "-CA",
                cert,
                "-CAkey",
                key,
                "-CAcreateserial",
                "-days",
                "1",
                "-extfile",
                config,
                "-out",
                leaf,
            )
            self.assertTrue(ensure_ca_usage(cert, key))
            self.assertEqual(key.read_bytes(), before)
            openssl("verify", "-x509_strict", "-CAfile", cert, leaf)
            saved = cert.read_bytes()
            self.assertFalse(ensure_ca_usage(cert, key))
            self.assertEqual(cert.read_bytes(), saved)

    def test_callback_codes_are_redacted_from_development_access_logs(self):
        import logging
        from config.oidc import RedactAuthQueries

        record = logging.LogRecord(
            "django.server",
            logging.INFO,
            "",
            0,
            '"%s" %s',
            ("GET /oauth/complete/oidc/?code=sensitive&state=secret HTTP/1.1", 302),
            None,
        )
        RedactAuthQueries().filter(record)
        self.assertNotIn("sensitive", record.getMessage())
        self.assertNotIn("state=secret", record.getMessage())
        self.assertIn("[redacted]", record.getMessage())
