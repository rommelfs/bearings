"""Native NetBox configuration. Identity/roles are local and explicitly linked."""

import os

ALLOWED_HOSTS = [os.environ["NETBOX_HOST"]]
SECRET_KEY = os.environ["NETBOX_SECRET_KEY"]
API_TOKEN_PEPPERS = {1: os.environ["NETBOX_TOKEN_PEPPER"]}
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "bearings_netbox",
        "USER": "bearings_netbox",
        "HOST": "/var/run/postgresql",
        "CONN_MAX_AGE": 300,
    }
}
REDIS = {
    name: {
        "HOST": "/run/bearings-netbox-redis/redis.sock",
        "PORT": 0,
        "DATABASE": index,
        "URL": f"unix:///run/bearings-netbox-redis/redis.sock?db={index}",
        "SSL": False,
    }
    for index, name in enumerate(("tasks", "caching"))
}
MEDIA_ROOT = "/var/lib/bearings-netbox/media"
# NetBox fixes settings.STATIC_ROOT to <NETBOX_ROOT>/static and ignores that
# name in configuration.py. Its supported STORAGES option sets the actual
# destination without granting the application write access to source code.
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        "OPTIONS": {
            "location": "/var/www/bearings-netbox/static",
            "base_url": "/static/",
            "file_permissions_mode": 0o644,
            "directory_permissions_mode": 0o755,
        },
    }
}
SCRIPTS_ROOT = "/var/lib/bearings-netbox/scripts"
REPORTS_ROOT = "/var/lib/bearings-netbox/reports"
SESSION_COOKIE_NAME = "netboxsessionid"
CSRF_COOKIE_NAME = "netboxcsrftoken"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = ["https://" + os.environ["NETBOX_HOST"]]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CENSUS_REPORTING_ENABLED = False
RELEASE_CHECK_URL = ""
EMAIL = {"SERVER": "127.0.0.1", "PORT": 1, "TIMEOUT": 1, "FROM_EMAIL": "bearings@circl.lu"}
REMOTE_AUTH_BACKEND = ("oidc.ApprovedOpenIdConnect",)
SOCIAL_AUTH_OIDC_KEY = "netbox"
SOCIAL_AUTH_OIDC_SECRET = os.environ["OIDC_CLIENT_SECRET"]
SOCIAL_AUTH_OIDC_ID_TOKEN_ISSUER = os.environ["OIDC_ISSUER"]
SOCIAL_AUTH_OIDC_VERIFY_SSL = True
SOCIAL_AUTH_OIDC_USE_PKCE = True
SOCIAL_AUTH_OIDC_TOKEN_ENDPOINT_AUTH_METHOD = "client_secret_basic"
SOCIAL_AUTH_OIDC_JWT_ALGORITHMS = ["RS256"]
SOCIAL_AUTH_OIDC_JWT_DECODE_OPTIONS = {"require": ["iss", "sub", "aud", "exp", "iat"]}
for name, suffix in (
    ("AUTHORIZATION_URL", "auth"),
    ("ACCESS_TOKEN_URL", "token"),
    ("USERINFO_URL", "userinfo"),
    ("JWKS_URI", "certs"),
):
    globals()["SOCIAL_AUTH_OIDC_" + name] = os.environ["OIDC_ISSUER"] + "/protocol/openid-connect/" + suffix
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.social_user",
    "oidc.require_approved_user",
)
SOCIAL_AUTH_SESSION_EXPIRATION = True
SOCIAL_AUTH_MAX_SESSION_LENGTH = 1800
