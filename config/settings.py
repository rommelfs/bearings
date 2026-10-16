import os
from pathlib import Path
from urllib.parse import urlsplit, unquote

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
DEFAULT_FROM_EMAIL = "bearings@example.invalid"
CONTACT_REVIEW_DAYS = int(os.getenv("CONTACT_REVIEW_DAYS", "183"))
NETBOX_ALLOW_PRIVATE = os.getenv("NETBOX_ALLOW_PRIVATE", "0") == "1"
NETBOX_URL = os.getenv("NETBOX_URL", "")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "")
NETBOX_SITE_ID = os.getenv("NETBOX_SITE_ID", "")
NETBOX_ROLE_ID = os.getenv("NETBOX_ROLE_ID", "")
NETBOX_DEVICE_TYPE_ID = os.getenv("NETBOX_DEVICE_TYPE_ID", "")
VULNERABILITY_LOOKUP_URL = os.getenv("VULNERABILITY_LOOKUP_URL", "https://vulnerability.circl.lu")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Opt-in for environments whose approved HTTPS proxy resolves external DNS.
CONNECTOR_PROXY_DNS = os.getenv("CONNECTOR_PROXY_DNS", "0") == "1"
CONNECTOR_ALLOWED_HOSTS = [
    h.strip().lower()
    for h in os.getenv("CONNECTOR_ALLOWED_HOSTS", "vulnerability.circl.lu").split(",")
    if h.strip()
]
