"""Native PostgreSQL deployment behind the bundled trusted Unix-socket HTTPS edge."""

import os
from urllib.parse import urlsplit

os.environ.setdefault("BEARINGS_DATA_DIR", "/var/lib/bearings")
os.environ.setdefault("DJANGO_STATIC_ROOT", "/var/www/bearings/static")

from . import settings as base  # noqa: E402

globals().update({name: getattr(base, name) for name in dir(base) if name.isupper()})

if base.DEBUG or len(base.SECRET_KEY) < 50 or base.SECRET_KEY.startswith("REPLACE_"):
    raise RuntimeError("Production requires DEBUG=0 and a dedicated random secret of at least 50 characters")
if base.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("Production requires PostgreSQL")
origin = urlsplit(base.PUBLIC_BASE_URL)
if (
    origin.scheme != "https"
    or not origin.hostname
    or origin.username
    or origin.password
    or origin.path not in ("", "/")
    or origin.query
    or origin.fragment
):
    raise RuntimeError("Set BEARINGS_PUBLIC_URL to the trusted public HTTPS origin")
if (
    not os.getenv("DJANGO_ALLOWED_HOSTS")
    or "*" in base.ALLOWED_HOSTS
    or origin.hostname not in base.ALLOWED_HOSTS
):
    raise RuntimeError("Explicit allowed hosts must include the public hostname, without wildcard")
if os.getenv("BEARINGS_DEV_STACK") == "1" or os.getenv("BEARINGS_SSO_LAB") == "1":
    raise RuntimeError("Lab bootstrap is not a production deployment")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
CSRF_TRUSTED_ORIGINS = [base.PUBLIC_BASE_URL.rstrip("/")]
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))
if not 3600 <= SECURE_HSTS_SECONDS <= 31536000:
    raise RuntimeError("Choose an HSTS lifetime between one hour and one year")
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
PUBLIC_REGISTRATION_ENABLED = os.getenv("BEARINGS_PUBLIC_REGISTRATION", "0") == "1"
if PUBLIC_REGISTRATION_ENABLED and base.SERVICE_MAIL_TRANSPORT != "smtp":
    raise RuntimeError("Public registration requires explicitly configured service SMTP")

# X-Real-IP is accepted only because the web process has no public TCP listener.
MIDDLEWARE = ["portal.production_edge.ClientAddress", *base.MIDDLEWARE]

# Initial domain-only, non-preload policy is intentional; do not hide any other deploy warning.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# Collectstatic may run under a private administrative umask; only static output is public.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        "OPTIONS": {"file_permissions_mode": 0o644, "directory_permissions_mode": 0o755},
    },
}
