import os
import json
from pathlib import Path
from urllib.parse import urlsplit, unquote
from portal.browser_policy import origin as canvas_origin

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_DIR = BASE_DIR / ".local"
LOCAL_DIR.mkdir(exist_ok=True)
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY (and use DJANGO_DEBUG=1 only for local development)")
    SECRET_KEY = "development-only-unsafe-key-do-not-deploy"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "portal.context.deployment",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": LOCAL_DIR / "development.sqlite3"}}
if os.getenv("DATABASE_URL"):
    db = urlsplit(os.environ["DATABASE_URL"])
    if db.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use PostgreSQL")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(db.path.lstrip("/")),
            "USER": unquote(db.username or ""),
            "PASSWORD": unquote(db.password or ""),
            "HOST": db.hostname,
            "PORT": db.port or 5432,
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"sslmode": os.getenv("PGSSLMODE", "prefer")},
        }
    }
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
# Intentionally a local delivery sink. Production delivery requires a separate authorized change.
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = LOCAL_DIR / "mail"
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "bearings@example.invalid")
# Reviewed outreach has its own explicit transport switch; other application mail stays local.
NOTIFICATION_TRANSPORT = os.getenv("BEARINGS_NOTIFICATION_TRANSPORT", "file")
EMAIL_HOST = os.getenv("SMTP_HOST", "")
EMAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_HOST_USER = os.getenv("SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("SMTP_STARTTLS", "1") == "1"
EMAIL_USE_SSL = os.getenv("SMTP_TLS", "0") == "1"
EMAIL_TIMEOUT = 10
CONTACT_REVIEW_DAYS = int(os.getenv("CONTACT_REVIEW_DAYS", "183"))
VULNERABILITY_LOOKUP_URL = os.getenv("VULNERABILITY_LOOKUP_URL", "https://vulnerability.circl.lu")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Browser workspaces never proxy credentials or relax an external application's policy.
CANVAS_ORIGIN = os.getenv("BEARINGS_CANVAS_ORIGIN", "").rstrip("/")
CANVAS_FRAME_ORIGINS = json.loads(os.getenv("BEARINGS_CANVAS_FRAME_ORIGINS", "[]"))
if CANVAS_ORIGIN:
    CANVAS_ORIGIN = canvas_origin(CANVAS_ORIGIN)
if not isinstance(CANVAS_FRAME_ORIGINS, list) or len(CANVAS_FRAME_ORIGINS) > 50:
    raise ValueError("Configure at most 50 explicit canvas frame origins")
CANVAS_FRAME_ORIGINS = [canvas_origin(value) for value in CANVAS_FRAME_ORIGINS]
if os.getenv("DJANGO_TRUST_PROXY_SSL") == "1":
    # Enable only behind an edge which overwrites this header and blocks direct upstream access.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Opt-in for environments whose approved HTTPS proxy resolves external DNS.
CONNECTOR_PROXY_DNS = os.getenv("CONNECTOR_PROXY_DNS", "0") == "1"
CONNECTOR_ALLOWED_HOSTS = [
    h.strip().lower()
    for h in os.getenv("CONNECTOR_ALLOWED_HOSTS", "vulnerability.circl.lu,objects.monarc.lu").split(",")
    if h.strip()
]

MOSP_URL = os.getenv("MOSP_URL", "https://objects.monarc.lu")
MOSP_PUBLISHER = os.getenv("MOSP_PUBLISHER", "MONARC")
MOSP_PROXY_DNS = os.getenv("MOSP_PROXY_DNS", "1" if CONNECTOR_PROXY_DNS else "0") == "1"
VULNERABILITY_LOOKUP_PROXY_DNS = (
    os.getenv("VULNERABILITY_LOOKUP_PROXY_DNS", "1" if CONNECTOR_PROXY_DNS else "0") == "1"
)

# OIDC is optional. Accounts/roles are explicitly managed locally; IdP claims cannot grant access.
SSO_ENABLED = os.getenv("BEARINGS_SSO_ENABLED", "0") == "1"
SSO_ISSUER = os.getenv("OIDC_ISSUER", "").rstrip("/")
SSO_SESSION_SECONDS = int(os.getenv("OIDC_SESSION_SECONDS", "1800"))
INSTALLED_APPS += ["social_django"]
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1, "portal.sso.SessionGuard"
)
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.social_user",
    "config.oidc.require_approved_user",
)
SOCIAL_AUTH_MAX_SESSION_LENGTH = SSO_SESSION_SECONDS
SOCIAL_AUTH_SESSION_EXPIRATION = True
SOCIAL_AUTH_LOGIN_REDIRECT_URL = "/"
SOCIAL_AUTH_LOGIN_ERROR_URL = "/accounts/login/"
SOCIAL_AUTH_REDIRECT_IS_HTTPS = not DEBUG
SOCIAL_AUTH_RAISE_EXCEPTIONS = True  # Sanitized by SessionGuard, including in DEBUG mode.
SOCIAL_AUTH_OIDC_USE_PKCE = True
SOCIAL_AUTH_OIDC_PKCE_CODE_CHALLENGE_METHOD = "S256"
SOCIAL_AUTH_OIDC_JWT_ALGORITHMS = ["RS256"]
SOCIAL_AUTH_OIDC_JWT_DECODE_OPTIONS = {"require": ["iss", "sub", "aud", "exp", "iat"]}
SOCIAL_AUTH_OIDC_TOKEN_ENDPOINT_AUTH_METHOD = "client_secret_basic"
SOCIAL_AUTH_OIDC_ID_TOKEN_ISSUER = SSO_ISSUER
SOCIAL_AUTH_OIDC_KEY = os.getenv("OIDC_CLIENT_ID", "bearings")
SOCIAL_AUTH_OIDC_LAB_CALLBACK = (
    os.getenv("OIDC_LAB_CALLBACK", "")
    if DEBUG and os.getenv("BEARINGS_DEV_STACK") == "1" and os.getenv("BEARINGS_SSO_LAB") == "1"
    else ""
)
SOCIAL_AUTH_OIDC_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
SOCIAL_AUTH_OIDC_VERIFY_SSL = os.getenv("OIDC_CA_BUNDLE") or True
SOCIAL_AUTH_OIDC_AUTHORIZATION_URL = os.getenv("OIDC_AUTHORIZATION_URL", "")
SOCIAL_AUTH_OIDC_ACCESS_TOKEN_URL = os.getenv("OIDC_TOKEN_URL", "")
SOCIAL_AUTH_OIDC_USERINFO_URL = os.getenv("OIDC_USERINFO_URL", "")
SOCIAL_AUTH_OIDC_JWKS_URI = os.getenv("OIDC_JWKS_URL", "")
if SSO_ENABLED:
    from django.core.exceptions import ImproperlyConfigured
    from portal.connectors.http import ConnectorError, validate_base

    try:
        for endpoint in [
            SSO_ISSUER,
            SOCIAL_AUTH_OIDC_AUTHORIZATION_URL,
            SOCIAL_AUTH_OIDC_ACCESS_TOKEN_URL,
            SOCIAL_AUTH_OIDC_USERINFO_URL,
            SOCIAL_AUTH_OIDC_JWKS_URI,
        ]:
            validate_base(endpoint)
    except ConnectorError:
        raise ImproperlyConfigured(
            "SSO requires explicit credential-free HTTPS issuer and endpoints"
        ) from None
    if not SOCIAL_AUTH_OIDC_SECRET or not 60 <= SSO_SESSION_SECONDS <= 86400:
        raise ImproperlyConfigured("Configure an OIDC client secret and session lifetime of 60–86400 seconds")
    AUTHENTICATION_BACKENDS += ["config.oidc.ApprovedOpenIdConnect"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"oidc_redaction": {"()": "config.oidc.RedactAuthQueries"}},
    "handlers": {"django.server": {"class": "logging.StreamHandler", "filters": ["oidc_redaction"]}},
    "loggers": {"django.server": {"handlers": ["django.server"], "level": "INFO", "propagate": False}},
}
