"""Registration navigation must stay cheap and must not mutate an existing identity."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from .models import Organization, Membership
from .tests import Fixture


@override_settings(PUBLIC_REGISTRATION_ENABLED=True)
class RegistrationEntryTests(Fixture):
    def test_anonymous_form_needs_no_inventory_or_showcase_database_query(self):
        with self.assertNumQueries(0):
            response = self.client.get(reverse("registration"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="company_name"')
        self.assertNotIn("Location", response)
        self.assertIn("registration;dur=", response.headers["Server-Timing"])
        self.assertIn("database;dur=0.0", response.headers["Server-Timing"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_optional_invalid_or_retained_values_remain_visible(self):
        for values in ({"notification_email": "invalid-address"}, {"company_address": "Synthetic address"}):
            response = self.client.post(reverse("registration"), values)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'class="registration-optional" open')
            self.assertContains(response, 'name="notification_email"')
            self.assertContains(response, 'name="consent"')
            self.assertFalse(Organization.objects.filter(name="Synthetic address").exists())

    def test_signed_in_registration_does_not_redirect_or_load_dashboard_data(self):
        self.client.force_login(self.admin)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("registration"))
        self.assertContains(response, "You are already signed in")
        self.assertContains(response, self.a.name)
        self.assertNotContains(response, self.b.name)
        self.assertNotContains(response, 'name="company_name"')
        self.assertNotIn("Location", response)
        for table in [
            "portal_asset",
            "portal_installation",
            "portal_finding",
            "portal_assetissue",
            "portal_mispevent",
        ]:
            self.assertFalse(any(f'"{table}"' in q["sql"] for q in queries), table)

    def test_operator_visibility_does_not_list_other_companies_on_registration(self):
        self.client.force_login(self.analyst)
        response = self.client.get(reverse("registration"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.a.name)
        self.assertNotContains(response, self.b.name)

    def test_signed_in_post_never_creates_another_account_or_company(self):
        self.client.force_login(self.admin)
        counts = [get_user_model().objects.count(), Organization.objects.count(), Membership.objects.count()]
        response = self.client.post(
            reverse("registration"), {"username": "unwanted", "company_name": "Unwanted"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            counts,
            [get_user_model().objects.count(), Organization.objects.count(), Membership.objects.count()],
        )

    def test_switch_account_is_explicit_csrf_protected_logout(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.get(reverse("registration"))
        self.assertContains(response, "Sign out to register a different account")
        self.assertEqual(client.post(reverse("logout"), {"next": reverse("registration")}).status_code, 403)
        response = client.post(
            reverse("logout"),
            {"next": reverse("registration"), "csrfmiddlewaretoken": client.cookies["csrftoken"].value},
        )
        self.assertRedirects(response, reverse("registration"))
        self.assertNotIn("_auth_user_id", client.session)

    @override_settings(PUBLIC_REGISTRATION_ENABLED=False)
    def test_closed_registration_policy_remains_closed(self):
        self.assertEqual(self.client.get(reverse("registration")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("registration")).status_code, 403)
