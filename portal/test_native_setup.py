import io
import json
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from config.smtp import relay_hostname
from portal.models import Organization, InventorySource, NetBoxInstance
from portal.service_mail import mail_subject


class NativeSetupTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="operator", is_superuser=True)
        self.data = {"key": str(uuid.uuid4()), "tenant": 42, "flow_org": 4}

    def invoke(self, **kwargs):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(self.data))):
            call_command("native_circl", actor="operator", stdout=output, **kwargs)
        return json.loads(output.getvalue())

    def test_plan_then_create_and_repeat_without_inventing_consent_or_contacts(self):
        self.assertIsNone(self.invoke()["organization"])
        self.assertFalse(Organization.objects.exists())
        first = self.invoke(apply=True)
        self.assertEqual(first, self.invoke(apply=True))
        org = Organization.objects.get(name="CIRCL")
        self.assertTrue(org.operator_visibility)
        self.assertEqual(org.postal_address, "")
        self.assertEqual(org.membership_set.count(), 0)
        self.assertEqual(org.inventory_source.tenant_id, 42)
        self.assertEqual(org.inventory_source.instance.access_mode, "read_only")

    def test_disabled_connector_and_other_authoritative_source_are_preserved(self):
        self.invoke(apply=True)
        nb = NetBoxInstance.objects.get()
        nb.enabled = False
        nb.save()
        with self.assertRaises(CommandError):
            self.invoke(apply=True)
        nb.refresh_from_db()
        self.assertFalse(nb.enabled)
        self.data["tenant"] = 43
        with self.assertRaises(CommandError):
            self.invoke(apply=True)
        self.assertEqual(InventorySource.objects.get().tenant_id, 42)

    def test_archived_duplicate_name_does_not_block_native_binding_retry(self):
        initial = self.invoke(apply=True)
        target = Organization.objects.get(pk=initial["organization"])
        Organization.objects.create(name="CIRCL", slug="archived-circl", merged_into=target)
        self.assertEqual(self.invoke(apply=True), initial)

    def test_non_admin_denied_and_ambiguous_company_not_adopted(self):
        self.actor.is_superuser = False
        self.actor.save()
        with self.assertRaises(CommandError):
            self.invoke(apply=True)
        self.actor.is_superuser = True
        self.actor.save()
        Organization.objects.create(name="CIRCL", slug="first")
        Organization.objects.create(name="circl", slug="second")
        with self.assertRaises(CommandError):
            self.invoke(apply=True)
        self.assertFalse(NetBoxInstance.objects.exists())

    def test_bracketed_relay_and_invalid_header_destination(self):
        self.assertEqual(relay_hostname("[cped.circl.lu]"), "cped.circl.lu")
        self.assertEqual(relay_hostname("[2001:db8::1]"), "2001:db8::1")
        for value in ["https://cped.circl.lu", "cped.circl.lu:25", "[cped.circl.lu", "a\r\nBcc:x"]:
            with self.assertRaises(ValueError):
                relay_hostname(value)

    @override_settings(
        MAIL_SUBJECT_PREFIX="[CIRCL BEARINGS]",
        EMAIL_HOST="cped.circl.lu",
        EMAIL_RELAY_HOST="[cped.circl.lu]",
        EMAIL_PORT=25,
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL="info@circl.lu",
        PUBLIC_BASE_URL="https://bearings.example.invalid",
    )
    def test_explicit_probe_never_sends_and_test_sends_exactly_one_tagged_email(self):
        self.assertEqual(mail_subject("Subject"), "[CIRCL BEARINGS] Subject")
        self.assertEqual(mail_subject(mail_subject("Subject")), mail_subject("Subject"))
        with (
            patch("portal.management.commands.service_mail_check.get_connection") as connect,
            patch("portal.management.commands.service_mail_check.EmailMessage") as message,
        ):
            connect.return_value.__enter__.return_value = MagicMock()
            call_command("service_mail_check", actor="operator", probe=True, stdout=io.StringIO())
            message.assert_not_called()
            message.return_value.send.return_value = 1
            call_command(
                "service_mail_check",
                actor="operator",
                send_test_to="operator@example.invalid",
                stdout=io.StringIO(),
            )
            self.assertEqual(message.call_args.args[0], "[CIRCL BEARINGS] SMTP connection test")
            self.assertEqual(message.call_args.args[3], ["operator@example.invalid"])
            message.return_value.send.assert_called_once()
        with override_settings(EMAIL_USE_TLS=False):
            with self.assertRaises(CommandError):
                call_command("service_mail_check", actor="operator", probe=True)
