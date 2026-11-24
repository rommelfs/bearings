"""One-use enrollment transport; no persistent plaintext credentials or device private keys."""

import base64
import json
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ValidationError


def trusted_origin():
    endpoint = settings.PUBLIC_BASE_URL.rstrip("/")
    origin = urlsplit(endpoint)
    if (
        origin.scheme != "https"
        or not origin.netloc
        or origin.username
        or origin.password
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise ValidationError("Configure BEARINGS_PUBLIC_URL with the trusted HTTPS origin before enrolling")
    return endpoint


def payload(grant, token):
    endpoint = trusted_origin()
    return {
        "schema": "bearings.agent.grant.v1",
        "url": endpoint,
        "grant": token,
        "public_key": grant.public_key,
        "asset_id": str(grant.asset_id) if grant.asset_id else "",
        "register_host": grant.asset_id is None,
        "expires_at": grant.expires_at.isoformat(),
    }


def encode(data):
    return "bearings-enroll-v1." + base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def windows_code(grant, token):
    return "bearings-windows-v1." + base64.urlsafe_b64encode(
        json.dumps(
            {
                "schema": "bearings.agent.grant.windows.v1",
                "url": trusted_origin(),
                "grant": token,
                "asset_id": str(grant.asset_id),
                "expires_at": grant.expires_at.isoformat(),
            },
            separators=(",", ":"),
        ).encode()
    ).decode().rstrip("=")
