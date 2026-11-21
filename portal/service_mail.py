"""Operator-configured registration/review mail; separate from vulnerability outreach."""

from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, get_connection
from .smtp import backend_path


def public_base():
    base = (
        settings.PUBLIC_BASE_URL
        or settings.CANVAS_ORIGIN
        or ("http://localhost:8000" if settings.DEBUG else "")
    )
    url = urlsplit(base)
    local_http = settings.DEBUG and url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}
    if (
        (url.scheme != "https" and not local_http)
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ImproperlyConfigured("Configure an operator-owned public HTTPS URL for service emails")
    return base.rstrip("/")


def mail_subject(subject):
    prefix = settings.MAIL_SUBJECT_PREFIX
    return (
        subject
        if not prefix or subject == prefix or subject.startswith(prefix + " ")
        else prefix + " " + subject
    )


def send_service_mail(subject, body, recipient, fingerprint=None):
    backend = backend_path() if settings.SERVICE_MAIL_TRANSPORT == "smtp" else settings.EMAIL_BACKEND
    connection = get_connection(backend=backend)
    headers = (
        {"Message-ID": f"<bearings-review-{fingerprint}@{urlsplit(public_base()).hostname}>"}
        if fingerprint
        else {}
    )
    message = EmailMessage(
        mail_subject(subject),
        body,
        settings.DEFAULT_FROM_EMAIL,
        [recipient],
        connection=connection,
        headers=headers,
    )
    if message.send(fail_silently=False) != 1:
        raise OSError("Service message was not accepted")
