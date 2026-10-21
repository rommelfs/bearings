"""OIDC signature/transaction, retained-client and deployment-generator regressions."""

import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase
import jwt

from docker.sso.oidc_client import Client, SignInError
from docker.sso.provision_client import ensure_client
from scripts.rt_sso import generate


class FlowOIDCTests(SimpleTestCase):
    def setUp(self):
        self.config = {
            "issuer": "https://idp.example/realms/test",
            "authorization": "https://idp.example/auth",
            "token": "https://internal.example/token",
            "jwks": "https://internal.example/keys",
            "userinfo": "https://internal.example/user",
            "callback": "https://flow.example/bearings-sso/callback",
            "client": "flowintel",
            "secret": "synthetic-private-client-key",
            "ca": "/approved/ca.pem",
        }
        self.client = Client(self.config)
        _, self.pending = self.client.begin()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid="one", use="sig", alg="RS256")
        self.claims = {
            "iss": self.config["issuer"],
            "sub": "immutable-CIRCL",
            "aud": "flowintel",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "nonce": self.pending["nonce"],
        }

    def complete(self, claims=None, info=None, key=None, keys=None):
        token = jwt.encode(claims or self.claims, key or self.key, algorithm="RS256", headers={"kid": "one"})
        responses = {
            "token": {"id_token": token, "access_token": "not-persisted"},
            "jwks": {"keys": keys if keys is not None else [self.jwk]},
            "userinfo": info if info is not None else {"sub": "immutable-CIRCL"},
        }
        with patch.object(self.client, "request", side_effect=lambda endpoint, *a, **kw: responses[endpoint]):
            return self.client.complete(self.pending, {"state": self.pending["state"], "code": "single-use"})

    def test_pkce_transaction_and_verified_identity_ignores_privilege_claims(self):
        from urllib.parse import parse_qs, urlsplit
        import hashlib

        url, pending = self.client.begin()
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(
            params["code_challenge"],
            [
                base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest())
                .rstrip(b"=")
                .decode()
            ],
        )
        identity = self.complete()
        self.assertEqual(
            identity, self.complete({**self.claims, "groups": ["admin"], "email": "other@example.com"})
        )
        self.assertNotIn("not-persisted", identity)

    def test_invalid_signed_claims_and_foreign_signatures_are_rejected(self):
        cases = [
            {"iss": "https://foreign.example"},
            {"aud": "netbox"},
            {"nonce": "wrong"},
            {"exp": 1},
            {"iat": time.time() + 3600},
            {"azp": "netbox"},
            {"aud": ["flowintel", "other"]},
            {"sub": ""},
        ]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(SignInError):
                self.complete({**self.claims, **update})
        with self.assertRaises(SignInError):
            self.complete(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
        for field in ["iss", "sub", "aud", "exp", "iat", "nonce"]:
            claims = dict(self.claims)
            del claims[field]
            with self.subTest(missing=field), self.assertRaises(SignInError):
                self.complete(claims)
        for info in [{}, {"sub": "foreign"}]:
            with self.assertRaises(SignInError):
                self.complete(info=info)
        for keys in [[], ["malformed"], [self.jwk, self.jwk]]:
            with self.assertRaises(SignInError):
                self.complete(keys=keys)

    def test_state_age_provider_error_and_missing_transaction_fail_before_http(self):
        for pending, args in [
            (None, {}),
            (self.pending, {"state": "foreign", "code": "code"}),
            ({**self.pending, "started": 1}, {"state": self.pending["state"], "code": "code"}),
            (self.pending, {"state": self.pending["state"], "code": "code", "error": "denied"}),
        ]:
            with patch.object(self.client, "request") as request, self.assertRaises(SignInError):
                self.client.complete(pending, args)
            request.assert_not_called()

    def test_transport_retains_tls_timeout_limits_and_refuses_redirects(self):
        response = MagicMock(status_code=200)
        response.iter_content.return_value = [b'{"sub":"good"}']
        with patch("docker.sso.oidc_client.requests.request") as request:
            request.return_value.__enter__.return_value = response
            self.assertEqual(self.client.request("userinfo"), {"sub": "good"})
            self.assertEqual(request.call_args.kwargs["verify"], "/approved/ca.pem")
            self.assertFalse(request.call_args.kwargs["allow_redirects"])
            self.assertEqual(request.call_args.kwargs["timeout"], 10)
            response.status_code = 302
            with self.assertRaises(SignInError):
                self.client.request("userinfo")
            response.status_code = 200
            response.iter_content.return_value = [b"x" * 1_000_001]
            with self.assertRaises(SignInError):
                self.client.request("userinfo")
        with self.assertRaises(ValueError):
            Client({**self.config, "token": "http://internal.example/token"})


class RetainedOIDCClientTests(SimpleTestCase):
    def test_flowintel_initializer_preserves_secrets_and_refuses_callback_repointing(self):
        from docker.sso.initialize import initialize_flowintel
        import secrets

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "secrets").mkdir()
            (root / "tls").mkdir()
            (root / "secrets/oidc-lab.json").write_text(
                json.dumps(
                    {
                        "issuer": "https://localhost:9444/realms/bearings-lab",
                        "users": {"circl-analyst": "immutable-sub"},
                    }
                )
            )
            (root / "tls/ca.crt").write_text("synthetic-public-ca")

            def write(path, value, **kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)

            def secret(path):
                if not path.exists():
                    write(path, secrets.token_urlsafe(48))
                return path.read_text()

            initialize_flowintel(root, write, secret, 9443)
            saved = (root / "flowintel-sso/client_secret").read_text()
            initialize_flowintel(root, write, secret, 9443)
            self.assertEqual(saved, (root / "flowintel-sso/client_secret").read_text())
            self.assertEqual(
                json.loads((root / "flowintel-sso/flowintel.json").read_text())["callback"],
                "https://localhost:9443/bearings-sso/callback",
            )
            with self.assertRaises(ValueError):
                initialize_flowintel(root, write, secret, 9555)

    def test_creates_only_missing_client_and_preserves_existing_disabled_policy(self):
        desired = {
            "clientId": "flowintel",
            "protocol": "openid-connect",
            "secret": "synthetic-secret",
            "publicClient": False,
            "standardFlowEnabled": True,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False,
            "fullScopeAllowed": False,
            "redirectUris": ["https://flow.example/callback"],
            "attributes": {"pkce.code.challenge.method": "S256"},
        }
        request = MagicMock(side_effect=[[], None])
        ensure_client(request, desired)
        self.assertEqual(request.call_args.args[:2], ("POST", "clients"))
        for changed, key, succeeds in [
            ({}, "synthetic-secret", True),
            ({"redirectUris": []}, "synthetic-secret", False),
            ({}, "different", False),
        ]:
            request = MagicMock(
                side_effect=[[{"id": "one"}], {**desired, "enabled": False, **changed}, {"value": key}]
            )
            if succeeds:
                ensure_client(request, desired)
            else:
                with self.assertRaises(RuntimeError):
                    ensure_client(request, desired)
            self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))


class RTSSOGeneratorTests(SimpleTestCase):
    def test_simple_cli_generates_private_credential_and_reuses_it_without_docker(self):
        from scripts import dev
        from contextlib import redirect_stdout
        import io

        with tempfile.TemporaryDirectory() as directory:
            argv = [
                "dev.py",
                "rt-sso",
                "--issuer",
                "https://idp.example/realm",
                "--rt-url",
                "https://rt.example",
                "--subject",
                "immutable-circl",
                "--rt-user",
                "analyst",
                "--output",
                directory,
            ]
            output = io.StringIO()
            with patch("sys.argv", argv), patch.object(dev, "check_docker") as check, redirect_stdout(output):
                dev.main()
                saved = (Path(directory) / "keycloak-client.json").read_bytes()
                dev.main()
                self.assertEqual(saved, (Path(directory) / "keycloak-client.json").read_bytes())
                check.assert_not_called()
            self.assertNotIn(json.loads(saved)["secret"], output.getvalue())

    def test_private_repeatable_bundle_case_sensitive_binding_and_executable_perl(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "rt"
            args = (
                path,
                "https://idp.example/realms/test",
                "https://rt.example",
                {"Subject-CIRCL": "analyst"},
                "synthetic-safe-client-secret-123456",
            )
            generate(*args)
            original = {p.name: p.read_bytes() for p in path.iterdir()}
            generate(*args)
            self.assertEqual(original, {p.name: p.read_bytes() for p in path.iterdir()})
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in path.iterdir()))
            code = "package RT; sub SystemUser {} package RT::User; our $disabled=0; sub new {bless {},shift} sub LoadByCols {$_[0]->{name}=$_[2]} sub Id {42} sub Name {$_[0]->{name}} sub Disabled {$disabled} package RT::Interface::Web; our $subject; sub RequestENV { $subject }; do $ARGV[0] or die $@; $subject='Subject-CIRCL'; die unless WebCanonicalizeInfo() == 42; $RT::User::disabled=1; die if defined WebCanonicalizeInfo(); $RT::User::disabled=0; $subject='subject-circl'; die if defined WebCanonicalizeInfo(); $subject='foreign'; die if defined WebCanonicalizeInfo();"
            subprocess.run(["perl", "-e", code, str(path / "Web_Local.pm")], check=True, capture_output=True)
            apache = (path / "apache-oidc.conf").read_text()
            self.assertIn("OIDCRemoteUserClaim sub", apache)
            self.assertIn("OIDCSSLValidateServer On", apache)
            self.assertIn("AuthType None", apache)
            with self.assertRaises(ValueError):
                generate(path, args[1], args[2], {"foreign": "analyst"}, args[4])
            self.assertEqual(original, {p.name: p.read_bytes() for p in path.iterdir()})

    def test_rejects_config_injection_duplicate_users_and_symlink_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            for url, mapping, secret in [
                ("https://rt.example/\nInclude hacked", {"sub": "analyst"}, "safe-key-1234567890"),
                ("http://rt.example", {"sub": "analyst"}, "safe-key-1234567890"),
                ("https://rt.example/rt", {"sub": "analyst"}, "safe-key-1234567890"),
                ("https://rt.example", {"one": "Analyst", "two": "analyst"}, "safe-key-1234567890"),
                ("https://rt.example", {"sub": "analyst"}, 'unsafe-${secret}"'),
            ]:
                with self.assertRaises(ValueError):
                    generate(Path(root) / "rt", "https://idp.example/realm", url, mapping, secret)
            path = Path(root) / "linked"
            path.symlink_to(Path(root), target_is_directory=True)
            with self.assertRaises(ValueError):
                generate(
                    path,
                    "https://idp.example/realm",
                    "https://rt.example",
                    {"sub": "analyst"},
                    "safe-key-1234567890",
                )
