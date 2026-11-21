"""An explicitly scoped SMTP encryption-only exception; never changes global SSL policy."""

import ssl
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend
from django.utils.functional import cached_property


def backend_path():
    return (
        "django.core.mail.backends.smtp.EmailBackend"
        if settings.EMAIL_TLS_VERIFY
        else "portal.smtp.EmailBackend"
    )


class EmailBackend(DjangoSMTPBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.EMAIL_TLS_VERIFY and (
            not settings.EMAIL_TLS_UNVERIFIED_HOST
            or self.host.lower().rstrip(".") != settings.EMAIL_TLS_UNVERIFIED_HOST.lower().rstrip(".")
            or self.use_tls == self.use_ssl
        ):
            raise ImproperlyConfigured("Encryption-only SMTP is restricted to its explicit TLS relay")

    @cached_property
    def ssl_context(self):
        if settings.EMAIL_TLS_VERIFY:
            return super().ssl_context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        if self.ssl_certfile or self.ssl_keyfile:
            context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
        return context
