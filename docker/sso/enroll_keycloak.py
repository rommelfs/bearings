"""Explicit local operator run; create a constituent IdP identity without resetting existing users."""

import json
import secrets
import sys
from pathlib import Path
from urllib.parse import quote
import requests


def main(data):
    manifest = json.loads(Path("/run/bearings/secrets/oidc-lab.json").read_text())
    if data["issuer"] != manifest["issuer"] or not data["issuer"].endswith("/realms/bearings-lab"):
        raise ValueError("Issuer mismatch")
    session = requests.Session()
    session.trust_env = False
    session.verify = "/run/bearings/trust/ca-bundle.pem"
    root = "https://netbox.bearings.test:444"

    def call(method, path, **kwargs):
        with session.request(
            method, root + path, timeout=10, allow_redirects=False, stream=True, **kwargs
        ) as response:
            if response.status_code not in {200, 201, 204}:
                raise ValueError("Provider operation failed: HTTP " + str(response.status_code))
            raw = bytearray()
            for chunk in response.iter_content(16384):
                raw.extend(chunk)
                if len(raw) > 1000000:
                    raise ValueError("Provider response too large")
            return json.loads(raw) if raw else None

    token = call(
        "POST",
        "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "sso-admin",
            "password": Path("/run/idp/bootstrap_password").read_text().strip(),
        },
    )["access_token"]
    session.headers["Authorization"] = "Bearer " + token
    path = "/admin/realms/bearings-lab/users"
    initial = None
    expected_subject = data.get("subject") or data.get("managed_subject")
    if expected_subject:
        user = call("GET", path + "/" + quote(expected_subject, safe=""))
        if user["id"] != expected_subject or not user.get("enabled"):
            raise ValueError("Retained identity disabled or changed")
    else:
        users = call("GET", path, params={"username": data["username"], "exact": "true", "max": 2})
        if users:
            raise ValueError("Existing unbound IdP username retained; prove/link its subject explicitly")
        initial = secrets.token_urlsafe(24)
        call(
            "POST",
            path,
            json={
                "username": data["username"],
                "enabled": True,
                "firstName": data["first_name"],
                "lastName": data["last_name"],
                "email": data["email"],
                "emailVerified": data["email_verified"],
                "credentials": [{"type": "password", "value": initial, "temporary": True}],
            },
        )
        users = call("GET", path, params={"username": data["username"], "exact": "true", "max": 2})
        if len(users) != 1:
            raise ValueError("Ambiguous newly-created identity; operator review required")
        user = call("GET", path + "/" + quote(users[0]["id"], safe=""))
        if not user.get("enabled"):
            raise ValueError("New identity is disabled; operator review required")
    return {
        "registration": data["registration"],
        "issuer": data["issuer"],
        "subject": user["id"],
        "username": user["username"],
        "initial_password": initial,
    }


if __name__ == "__main__":
    try:
        print("SSO_RESULT:" + json.dumps(main(json.load(sys.stdin))))
    except Exception as error:
        print("Enrollment failure category: " + type(error).__name__, file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        raise SystemExit(
            "Constituent IdP enrollment refused or unavailable; existing credentials/policy preserved. No provider body was logged."
        ) from None
