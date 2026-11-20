"""SMTP-only exception, actual local self-signed TLS, and mandatory STARTTLS failure."""

import datetime
import socket
import ssl
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from smtplib import SMTPNotSupportedError
from .smtp import EmailBackend, backend_path


@override_settings(
    EMAIL_HOST="localhost",
    EMAIL_HOST_USER="",
    EMAIL_HOST_PASSWORD="",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=False,
    EMAIL_TLS_UNVERIFIED_HOST="localhost",
)
class SMTPPolicyTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .sign(key, hashes.SHA256())
        )
        root = Path(self.directory.name)
        (root / "cert").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (root / "key").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        self.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server_context.load_cert_chain(root / "cert", root / "key")

    def handshake(self, context):
        client, server = socket.socketpair()
        client.settimeout(3)
        server.settimeout(3)
        errors = []

        def serve():
            try:
                with self.server_context.wrap_socket(server, server_side=True):
                    pass
            except ssl.SSLError as error:
                errors.append(type(error).__name__)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with client, context.wrap_socket(client, server_hostname="localhost") as tls:
                self.assertIn(tls.version(), {"TLSv1.2", "TLSv1.3"})
        finally:
            thread.join(timeout=4)
            server.close()
        self.assertFalse(thread.is_alive())

    def test_default_rejects_self_signed_and_explicit_matching_relay_accepts(self):
        with override_settings(EMAIL_TLS_VERIFY=True):
            self.assertEqual(backend_path(), "django.core.mail.backends.smtp.EmailBackend")
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.handshake(EmailBackend().ssl_context)
        with override_settings(EMAIL_TLS_VERIFY=False):
            self.assertEqual(backend_path(), "portal.smtp.EmailBackend")
            self.handshake(EmailBackend().ssl_context)
        # No global HTTPS/SSO trust mutation.
        self.assertTrue(ssl.create_default_context().check_hostname)
        self.assertEqual(ssl.create_default_context().verify_mode, ssl.CERT_REQUIRED)

    @override_settings(EMAIL_TLS_VERIFY=False)
    def test_different_destination_or_plaintext_is_rejected_before_connecting(self):
        for options in [{"host": "other.example.invalid"}, {"use_tls": False}]:
            with self.assertRaises(ImproperlyConfigured):
                EmailBackend(**options)

    @override_settings(EMAIL_TLS_VERIFY=False)
    def test_missing_starttls_never_falls_back_to_plaintext_or_auth(self):
        with patch("django.core.mail.backends.smtp.smtplib.SMTP") as smtp:
            smtp.return_value.starttls.side_effect = SMTPNotSupportedError("No STARTTLS")
            with self.assertRaises(SMTPNotSupportedError):
                EmailBackend().open()
            smtp.return_value.login.assert_not_called()
            smtp.return_value.sendmail.assert_not_called()
