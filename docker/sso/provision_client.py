"""One-off, isolated IdP client addition. Never reset an existing client or account."""

import hmac
import json
import os
from pathlib import Path

import requests


def ensure_client(request, desired, *, legacy_redirects=None):
    clients = request("GET", "clients", params={"clientId": desired["clientId"]})
    if not clients:
        request("POST", "clients", json=desired)
        return
    if len(clients) != 1:
        raise RuntimeError("Ambiguous retained IdP client")
    current = request("GET", "clients/" + clients[0]["id"])
    migrate = (
        desired["clientId"] == "bearings"
        and legacy_redirects is not None
        and current.get("redirectUris") == legacy_redirects
    )
    for name in [
        "clientId",
        "protocol",
        "publicClient",
        "standardFlowEnabled",
        "implicitFlowEnabled",
        "directAccessGrantsEnabled",
        "serviceAccountsEnabled",
        "fullScopeAllowed",
        "redirectUris",
    ]:
        if current.get(name) != desired[name] and not (migrate and name == "redirectUris"):
            raise RuntimeError("Retained IdP client policy differs; preserved without automatic changes")
    if current.get("attributes", {}).get("pkce.code.challenge.method") != "S256":
        raise RuntimeError("Retained IdP client PKCE differs; preserved")
    saved = request("GET", "clients/" + clients[0]["id"] + "/client-secret")["value"]
    if not hmac.compare_digest(saved, desired["secret"]):
        raise RuntimeError("Retained IdP client secret differs; neither copy was replaced")
    if migrate:
        # Only the exact generated legacy allowlist is migrated, after all policy and
        # secret checks. Keep disabled state, accounts, grants and custom fields intact.
        request("PUT", "clients/" + clients[0]["id"], json={"redirectUris": desired["redirectUris"]})


def main():
    kind = os.getenv("BEARINGS_SSO_CLIENT", "flowintel")
    if kind not in {"flowintel", "rt", "bearings"}:
        raise ValueError("Unknown bundled client")
    config = (
        json.loads(Path("/run/flowintel-sso/flowintel.json").read_text()) if kind == "flowintel" else None
    )
    root = "https://netbox.bearings.test:444"
    session = requests.Session()
    session.trust_env = False
    session.verify = {
        "flowintel": "/run/flowintel-sso/ca-bundle.pem",
        "rt": "/run/rt/ca-bundle.pem",
        "bearings": "/run/bearings/trust/ca-bundle.pem",
    }[kind]

    def bounded(method, url, **kwargs):
        with session.request(
            method, url, timeout=10, allow_redirects=False, stream=True, **kwargs
        ) as response:
            if response.status_code not in {200, 201, 204}:
                raise RuntimeError(
                    "IdP client setup failed; verify retained operator access and client policy"
                )
            data = bytearray()
            for chunk in response.iter_content(16384):
                data.extend(chunk)
                if len(data) > 1_000_000:
                    raise RuntimeError("IdP setup response exceeds limit")
            return json.loads(data) if data else None

    token = bounded(
        "POST",
        root + "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "sso-admin",
            "password": Path("/run/idp/bootstrap_password").read_text().strip(),
        },
    )["access_token"]
    session.headers["Authorization"] = "Bearer " + token

    def request(method, path, **kwargs):
        return bounded(method, root + "/admin/realms/bearings-lab/" + path, **kwargs)

    if kind == "bearings":
        saved = json.loads(Path("/run/bearings/secrets/oidc-bearings-client.json").read_text())
        ensure_client(request, saved["client"], legacy_redirects=saved["legacy_redirects"])
    else:
        ensure_client(
            request,
            json.loads(Path("/run/rt-sso/keycloak-client.json").read_text())
            if kind == "rt"
            else {
                "clientId": "flowintel",
                "protocol": "openid-connect",
                "enabled": True,
                "publicClient": False,
                "secret": Path("/run/flowintel-sso/client_secret").read_text().strip(),
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "fullScopeAllowed": False,
                "redirectUris": [config["callback"]],
                "defaultClientScopes": ["profile"],
                "attributes": {"pkce.code.challenge.method": "S256"},
            },
        )
    print(kind + " IdP client verified; retained credentials, disabled state and user policies preserved.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, requests.RequestException, ValueError, KeyError):
        raise SystemExit(
            "SSO client setup failed. Inspect retained IdP access/configuration; no secrets were logged."
        ) from None
