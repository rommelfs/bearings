"""Settings exclusively for the isolated, synthetic PostgreSQL scale lab."""

import os
from pathlib import Path
from config.settings import *  # noqa: F403

if os.environ.get("BEARINGS_SCALE_TEST") != "1":
    raise RuntimeError("Scale settings require an explicitly isolated scale lab")
if not DATABASES["default"]["NAME"].startswith("bearings_scale_"):  # noqa: F405
    raise RuntimeError("Scale database name must start with bearings_scale_")
DEBUG = False
ALLOWED_HOSTS = ["testserver", "127.0.0.1", "localhost"]
SSO_ENABLED = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = Path(__file__).resolve().parents[1] / ".local/scale-test/mail"
SERVICE_MAIL_TRANSPORT = NOTIFICATION_TRANSPORT = "file"
PUBLIC_BASE_URL = "https://scale.example.invalid"
DATABASES["default"]["OPTIONS"]["options"] = "-c statement_timeout=5000"  # noqa: F405
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "loggers": {"django.request": {"handlers": ["null"], "propagate": False}},
}

MIDDLEWARE = ["portal.scale_benchmark.ScaleMetricsMiddleware", *MIDDLEWARE]  # noqa: F405
