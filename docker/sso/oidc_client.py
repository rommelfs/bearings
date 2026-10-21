"""Small OIDC code client for the FlowIntel adapter; no discovery or provisioning."""

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode, urlsplit

import jwt
import requests


class SignInError(Exception):
    """An authentication failure with no provider response included."""


def identity_key(issuer, subject):
    import json

    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise SignInError("Invalid subject")
    return hashlib.sha256(json.dumps([issuer, subject], separators=(",", ":")).encode()).hexdigest()


class Client:
    def __init__(self, settings):
        self.settings = settings
        for name in ["issuer", "authorization", "token", "userinfo", "jwks", "callback"]:
            url = urlsplit(settings[name])
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("OIDC requires fixed HTTPS endpoints without credentials or query")
        if not settings.get("ca") or not settings.get("secret"):
            raise ValueError("OIDC requires certificate trust and a private client secret")

    def request(self, endpoint, method="GET", **kwargs):
        try:
            with requests.request(
                method,
                self.settings[endpoint],
                timeout=10,
                verify=self.settings["ca"],
                allow_redirects=False,
                stream=True,
                **kwargs,
            ) as response:
                if response.status_code != 200:
                    raise SignInError("Provider unavailable")
                data = bytearray()
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data) > 1_000_000:
                        raise SignInError("Provider response exceeds limit")
                import json

                result = json.loads(data)
                if not isinstance(result, dict):
                    raise SignInError("Invalid provider response")
                return result
        except (requests.RequestException, ValueError):
            raise SignInError("Provider unavailable") from None

    def begin(self):
        pending = {name: secrets.token_urlsafe(48) for name in ["state", "nonce", "verifier"]}
        pending["started"] = time.time()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest())
        url = (
            self.settings["authorization"]
            + "?"
            + urlencode(
                {
                    "client_id": self.settings["client"],
                    "redirect_uri": self.settings["callback"],
                    "response_type": "code",
                    "scope": "openid profile",
                    "state": pending["state"],
                    "nonce": pending["nonce"],
                    "code_challenge": challenge.rstrip(b"=").decode(),
                    "code_challenge_method": "S256",
                }
            )
        )
        return url, pending

    def complete(self, pending, args):
        if (
            not pending
            or not 0 <= time.time() - pending.get("started", 0) <= 300
            or not hmac.compare_digest(pending.get("state", ""), args.get("state", ""))
            or not args.get("code")
            or args.get("error")
        ):
            raise SignInError("Invalid authentication transaction")
        response = self.request(
            "token",
            "POST",
            auth=(self.settings["client"], self.settings["secret"]),
            data={
                "grant_type": "authorization_code",
                "code": args["code"],
                "redirect_uri": self.settings["callback"],
                "code_verifier": pending["verifier"],
            },
        )
        try:
            token = response["id_token"]
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise SignInError("Invalid signing key")
            keys = self.request("jwks")["keys"]
            matches = [
                key
                for key in keys
                if key.get("kid") == header["kid"]
                and key.get("kty") == "RSA"
                and key.get("use", "sig") == "sig"
                and key.get("alg", "RS256") == "RS256"
            ]
            if len(matches) != 1:
                raise SignInError("Unknown signing key")
            claims = jwt.decode(
                token,
                jwt.PyJWK(matches[0], algorithm="RS256").key,
                algorithms=["RS256"],
                audience=self.settings["client"],
                issuer=self.settings["issuer"],
                options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
            )
            if not hmac.compare_digest(claims["nonce"], pending["nonce"]):
                raise SignInError("Invalid nonce")
            aud = claims["aud"]
            if (isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != self.settings["client"]) or (
                "azp" in claims and claims["azp"] != self.settings["client"]
            ):
                raise SignInError("Invalid authorized party")
            identity = identity_key(self.settings["issuer"], claims["sub"])
            info = self.request("userinfo", headers={"Authorization": "Bearer " + response["access_token"]})
            if info.get("sub") != claims["sub"]:
                raise SignInError("UserInfo subject mismatch")
            return identity
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, AttributeError):
            raise SignInError("Invalid identity response") from None
