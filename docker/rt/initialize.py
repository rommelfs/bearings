"""Private, retained RT lab endpoint, credentials and optional OIDC inputs."""

import json
import os
from pathlib import Path

import certifi


def initialize(root, write, secret, *, sso):
    port, recovery = int(os.getenv("RT_PORT", "9445")), int(os.getenv("RT_RECOVERY_PORT", "9446"))
    if port == recovery or not all(1024 <= p <= 65535 for p in [port, recovery]):
        raise ValueError("Use distinct unprivileged RT ports")
    config = {
        "base_url": "https://rt.bearings.test",
        "browser_url": f"https://localhost:{port}",
        "port": port,
        "recovery_port": recovery,
    }
    path = root / "rt-secrets/config.json"
    if path.exists() and json.loads(path.read_text()) != config:
        raise ValueError(
            "Retained RT endpoint changed; use an isolated lab rather than repointing identities"
        )
    write(path, json.dumps(config), public=True)
    write(
        root / "rt-secrets/ca-bundle.pem",
        Path(certifi.where()).read_text() + "\n" + (root / "tls/ca.crt").read_text(),
        public=True,
    )
    for path in (root / "rt-secrets").iterdir():
        os.chown(path, 0, 33)
        path.chmod(0o640)
    if not sso:
        return
    from scripts.rt_sso import generate

    manifest = json.loads((root / "secrets/oidc-lab.json").read_text())
    directory = root / "rt-sso"
    key = secret(root / "rt-secrets/oidc_client_secret")
    # generate() refuses retained endpoint/map/secret changes; its default outputs stay byte-stable.
    generate(
        directory,
        manifest["issuer"],
        config["browser_url"],
        {
            manifest["users"]["company-admin"]: "company-admin",
            manifest["users"]["circl-analyst"]: "circl-analyst",
        },
        key,
        client_id="rt",
        ca_path="/run/rt/ca-bundle.pem",
    )
    original = directory / "apache-oidc.conf"
    # Preserve generator inputs for repeat checks; the lab-specific runtime config has fixed TLS backchannels.
    internal = "https://netbox.bearings.test:444/realms/bearings-lab/protocol/openid-connect/"
    explicit = "\n".join(
        [
            f'OIDCProviderIssuer "{manifest["issuer"]}"',
            f'OIDCProviderAuthorizationEndpoint "{manifest["issuer"]}/protocol/openid-connect/auth"',
            f'OIDCProviderTokenEndpoint "{internal}token"',
            f'OIDCProviderUserInfoEndpoint "{internal}userinfo"',
            f'OIDCProviderJwksUri "{internal}certs"',
        ]
    )
    value = original.read_text().replace(
        f'OIDCProviderMetadataURL "{manifest["issuer"]}/.well-known/openid-configuration"', explicit
    )
    write(directory / "apache-lab.conf", value)
    for path in directory.iterdir():
        os.chown(path, 0, 33)
        path.chmod(0o640)
    os.chown(directory, 0, 33)
    directory.chmod(0o750)
