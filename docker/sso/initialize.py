"""Generate private, repeatable local IdP inputs; existing realms/passwords are never reset."""

import json
import uuid
from pathlib import Path

NAMESPACE = uuid.UUID("f41faab5-9f09-4640-9809-cbc5e5b6b853")


def initialize(root, write, secret, ports):
    issuer = f"https://localhost:{ports['sso']}/realms/bearings-lab"
    users = {
        name: str(uuid.uuid5(NAMESPACE, name))
        for name in ["company-admin", "circl-analyst", "unassigned-demo"]
    }
    manifest = {"issuer": issuer, "users": users, "ports": ports}
    path = root / "secrets/oidc-lab.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError(
            "SSO lab identity/ports changed; configure an isolated project instead of repointing retained identities"
        )
    write(path, json.dumps(manifest), public=True)
    app_secret = secret(root / "secrets/oidc_client_secret", app=True)
    netbox_secret = secret(root / "netbox-secrets/oidc_client_secret")
    secret(root / "sso/bootstrap_password")
    password = (root / "secrets/demo_password").read_text().strip()
    clients = []
    for name, client_secret, redirects in [
        (
            "bearings",
            app_secret,
            [
                f"http://{host}:{ports['bearings']}/oauth/complete/oidc/"
                for host in ["localhost", "127.0.0.1"]
            ],
        ),
        (
            "netbox",
            netbox_secret,
            [f"https://{host}:{ports['netbox']}/oauth/complete/oidc/" for host in ["localhost", "127.0.0.1"]],
        ),
    ]:
        clients.append(
            {
                "clientId": name,
                "protocol": "openid-connect",
                "enabled": True,
                "publicClient": False,
                "secret": client_secret,
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "fullScopeAllowed": False,
                "redirectUris": redirects,
                "defaultClientScopes": ["profile", "email"],
                "attributes": {"pkce.code.challenge.method": "S256"},
            }
        )
    realm = {
        "realm": "bearings-lab",
        "enabled": True,
        "displayName": "Bearings synthetic SSO lab",
        "sslRequired": "external",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "loginWithEmailAllowed": False,
        "bruteForceProtected": True,
        "accessTokenLifespan": 300,
        "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 28800,
        "clients": clients,
        "users": [
            {
                "id": subject,
                "username": name,
                "enabled": True,
                "emailVerified": False,
                "firstName": "Synthetic",
                "lastName": name,
                "email": name + "@example.com",
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            }
            for name, subject in users.items()
        ],
    }
    legacy = root / "sso/bearings-realm.json"
    if legacy.exists():
        if json.loads(legacy.read_text()).get("realm") != "bearings-lab":
            raise ValueError("Unexpected legacy IdP input; refusing replacement")
        legacy.unlink()
    write(root / "sso/bearings-lab-realm.json", json.dumps(realm))
    (root / "sso/bearings-lab-realm.json").chmod(0o640)


def initialize_flowintel(root, write, secret, port):
    """Separate secrets and immutable callback for the optional third application."""
    import certifi

    manifest = json.loads((root / "secrets/oidc-lab.json").read_text())
    target = root / "flowintel-sso"
    info = {
        "issuer": manifest["issuer"],
        "subject": manifest["users"]["circl-analyst"],
        "callback": f"https://localhost:{port}/bearings-sso/callback",
    }
    path = target / "flowintel.json"
    if path.exists() and json.loads(path.read_text()) != info:
        raise ValueError("Retained FlowIntel SSO issuer/callback changed; refusing identity repointing")
    write(path, json.dumps(info), public=True)
    secret(target / "client_secret")
    write(
        target / "ca-bundle.pem",
        Path(certifi.where()).read_text() + "\n" + (root / "tls/ca.crt").read_text(),
        public=True,
    )
