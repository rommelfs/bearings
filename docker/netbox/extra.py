import os
from pathlib import Path

# Local bundled NetBox only. No production delivery or telemetry.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True


if os.getenv("BEARINGS_SSO_LAB") == "1":
    REMOTE_AUTH_BACKEND = ("bearings_oidc.ApprovedOpenIdConnect",)
    # NetBox's ObjectPermissionBackend continues to provide local password authentication.
    SOCIAL_AUTH_OIDC_KEY = "netbox"
    SOCIAL_AUTH_OIDC_SECRET = Path("/run/secrets/oidc_client_secret").read_text().strip()
    SOCIAL_AUTH_OIDC_ID_TOKEN_ISSUER = (
        f"https://localhost:{os.getenv('SSO_PORT', '9444')}/realms/bearings-lab"
    )
    SOCIAL_AUTH_OIDC_AUTHORIZATION_URL = SOCIAL_AUTH_OIDC_ID_TOKEN_ISSUER + "/protocol/openid-connect/auth"
    _internal = "https://netbox.bearings.test:444/realms/bearings-lab/protocol/openid-connect/"
    SOCIAL_AUTH_OIDC_ACCESS_TOKEN_URL = _internal + "token"
    SOCIAL_AUTH_OIDC_USERINFO_URL = _internal + "userinfo"
    SOCIAL_AUTH_OIDC_JWKS_URI = _internal + "certs"
    SOCIAL_AUTH_OIDC_VERIFY_SSL = "/run/bearings/trust/ca-bundle.pem"
    SOCIAL_AUTH_OIDC_USE_PKCE = True
    SOCIAL_AUTH_OIDC_TOKEN_ENDPOINT_AUTH_METHOD = "client_secret_basic"
    SOCIAL_AUTH_OIDC_JWT_DECODE_OPTIONS = {"require": ["iss", "sub", "aud", "exp", "iat"]}
    SOCIAL_AUTH_OIDC_JWT_ALGORITHMS = ["RS256"]
    SOCIAL_AUTH_PIPELINE = (
        "social_core.pipeline.social_auth.social_details",
        "social_core.pipeline.social_auth.social_uid",
        "social_core.pipeline.social_auth.social_user",
        "bearings_oidc.require_approved_user",
    )
    SOCIAL_AUTH_SESSION_EXPIRATION = True
    SOCIAL_AUTH_MAX_SESSION_LENGTH = 1800
