"""Controlled SMTP readiness; never changes registration or queued delivery policy."""

import hashlib
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from portal.access import audit
from portal.service_mail import mail_subject, public_base
from portal.smtp import backend_path


class Command(BaseCommand):
    help = "Inspect service mail, probe SMTP TLS, or send one explicit operator test; no queued mail"

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument("--probe", action="store_true")
        parser.add_argument("--send-test-to")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=options["actor"], is_active=True, is_superuser=True)
            .first()
        )
        if not actor:
            raise CommandError("An active platform administrator is required")
        details = {
            "relay": settings.EMAIL_RELAY_HOST,
            "host": settings.EMAIL_HOST,
            "port": settings.EMAIL_PORT,
            "starttls": settings.EMAIL_USE_TLS,
            "implicit_tls": settings.EMAIL_USE_SSL,
            "certificate_verification": settings.EMAIL_TLS_VERIFY,
            "unverified_relay": settings.EMAIL_TLS_UNVERIFIED_HOST,
            "authentication": bool(settings.EMAIL_HOST_USER),
            "sender": settings.DEFAULT_FROM_EMAIL,
            "subject_prefix": settings.MAIL_SUBJECT_PREFIX,
            "service_transport": settings.SERVICE_MAIL_TRANSPORT,
            "public_registration": settings.PUBLIC_REGISTRATION_ENABLED,
        }
        if options["probe"] or options["send_test_to"]:
            if not settings.EMAIL_HOST or settings.EMAIL_USE_TLS == settings.EMAIL_USE_SSL:
                raise CommandError("Configure a relay and exactly one TLS mode before testing SMTP")
            try:
                validate_email(settings.DEFAULT_FROM_EMAIL)
                if options["send_test_to"]:
                    validate_email(options["send_test_to"])
            except ValidationError:
                raise CommandError("A valid single sender and test recipient address are required") from None
            try:
                with get_connection(backend=backend_path()) as connection:
                    if options["send_test_to"]:
                        sent = EmailMessage(
                            mail_subject("SMTP connection test"),
                            "Controlled Bearings service-mail test. No registration or data review was completed.\n\n"
                            + public_base(),
                            settings.DEFAULT_FROM_EMAIL,
                            [options["send_test_to"]],
                            connection=connection,
                        ).send(fail_silently=False)
                        if sent != 1:
                            raise OSError("SMTP did not accept the controlled test")
                    else:
                        connection.open()
            except Exception as error:
                raise CommandError(
                    f"SMTP TLS check failed ({type(error).__name__}); no transport policy was changed"
                ) from None
            details["smtp"] = (
                "test accepted by relay; inbox delivery still needs confirmation"
                if options["send_test_to"]
                else "TLS connection ready; no email sent"
            )
            audit(
                actor,
                None,
                "service_mail.smtp_test" if options["send_test_to"] else "service_mail.smtp_probe",
                "operator",
                recipient_hash=hashlib.sha256((options["send_test_to"] or "").encode()).hexdigest(),
                tls_verify=settings.EMAIL_TLS_VERIFY,
            )
        self.stdout.write(json.dumps(details))
