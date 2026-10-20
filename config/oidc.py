"""Shared pre-approved OIDC backend for Bearings and the bundled NetBox.

No automatic account creation, email linking, claim-to-role mapping or token persistence.
"""

import hashlib
import json
import logging
import re
import time
from urllib.parse import urlsplit
import requests
from social_core.backends.open_id_connect import OpenIdConnectAuth
from social_core.exceptions import AuthForbidden, AuthTokenError


def identity_uid(issuer, subject):
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise ValueError("Invalid OIDC subject")
    return hashlib.sha256(json.dumps([issuer, subject], separators=(",", ":")).encode()).hexdigest()


class ApprovedOpenIdConnect(OpenIdConnectAuth):
    def validate_claims(self, id_token):
        client, _ = self.get_key_and_secret()
        aud = id_token.get("aud")
        if (isinstance(aud, list) and len(aud) > 1 and id_token.get("azp") != client) or (
            "azp" in id_token and id_token["azp"] != client
        ):
            raise AuthTokenError(self, "Invalid authorized party")
        return super().validate_claims(id_token)

    def get_user_id(self, details, response):
        try:
            return identity_uid(self.id_token_issuer(), super().get_user_id(details, response))
        except ValueError:
            raise AuthTokenError(self, "Invalid identity") from None

    def request(self, url, *, method="GET", **kwargs):
        # Explicit operator endpoints: do not discover or follow response-provided URLs.
        allowed = {
            self.setting(name)
            for name in ["AUTHORIZATION_URL", "ACCESS_TOKEN_URL", "USERINFO_URL", "JWKS_URI"]
        }
        parsed = urlsplit(url)
        if (
            url not in allowed
            or parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise AuthForbidden(self)
        verify = self.setting("VERIFY_SSL", True)
        if verify is False:
            raise AuthForbidden(self)
        kwargs.pop("timeout", None)
        try:
            with requests.request(
                method, url, timeout=10, verify=verify, allow_redirects=False, stream=True, **kwargs
            ) as response:
                if response.status_code != 200:
                    raise AuthTokenError(self, "Identity provider request failed")
                chunks, size = [], 0
                for chunk in response.iter_content(16384):
                    size += len(chunk)
                    if size > 1_000_000:
                        raise AuthTokenError(self, "Identity response exceeds limit")
                    chunks.append(chunk)
                response._content = b"".join(chunks)
                response._content_consumed = True
                return response
        except requests.RequestException:
            raise AuthTokenError(self, "Identity provider unavailable") from None

    def validate_userinfo_sub(self, userinfo):
        if not isinstance(userinfo, dict) or not userinfo.get("sub"):
            raise AuthTokenError(self, "Identity subject missing")
        return super().validate_userinfo_sub(userinfo)

    def get_user(self, user_id):
        user = super().get_user(user_id)
        if not user or not user.is_active:
            return None
        for binding in user.social_auth.filter(provider=self.name, extra_data__issuer=self.id_token_issuer()):
            if not binding.extra_data.get("enabled", False):
                continue
            verified = binding.extra_data.get("last_verified", 0)
            if isinstance(verified, (int, float)) and 0 <= time.time() - verified < self.setting(
                "MAX_SESSION_LENGTH", 1800
            ):
                return user
        return None


def require_approved_user(backend, user=None, social=None, **kwargs):
    if (
        not social
        or not user
        or social.user_id != user.pk
        or not user.is_active
        or not social.extra_data.get("enabled", False)
    ):
        raise AuthForbidden(backend)
    social.extra_data["last_verified"] = time.time()
    social.save(update_fields=["extra_data"])
    # A fixed absolute lifetime bounds IdP revocation delay, independent of application activity.
    backend.strategy.session_set("bearings_sso_binding", social.pk)
    backend.strategy.session_set("bearings_sso_generation", social.extra_data.get("generation"))
    backend.strategy.session_set("bearings_sso_started", time.time())


class RedactAuthQueries(logging.Filter):
    def filter(self, record):
        def redact(value):
            return (
                re.sub(r"(/oauth/complete/[^?\s]+)\?[^\s\"]+", r"\1?[redacted]", value)
                if isinstance(value, str)
                else value
            )

        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        return True
