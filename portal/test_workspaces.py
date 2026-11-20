from django.test import Client
from django.urls import reverse
from .tests import Fixture
from .models import Organization, Membership, InventorySource
from .workspace_views import SESSION_COMPANY
from .member_views import MergeForm


class WorkspaceTests(Fixture):
    def test_visible_view_switch_marks_actual_company_and_national_destinations(self):
        org = Organization.objects.create(name="CIRCL", slug="circl")
        InventorySource.objects.create(organization=org, mode="manual")
        Membership.objects.create(user=self.platform, organization=org, role="reader")
        self.login(self.platform)
        national = self.client.get(reverse("circl-overview"))
        self.assertContains(national, 'aria-label="Infrastructure view"')
        self.assertContains(national, "CIRCL infrastructure")
        self.assertTrue(national.context["switch_national_active"])
        company_url = reverse("overview") + "?organization=circl"
        self.assertEqual(national.context["switch_company_url"], company_url)
        company = self.client.get(company_url)
        self.assertTrue(company.context["switch_company_active"])
        self.assertFalse(company.context["switch_national_active"])
        self.assertEqual(Membership.objects.get(user=self.platform, organization=org).role, "reader")
        self.client.post(reverse("workspace-switch"), {"action": "company", "organization": self.a.pk})
        selected = self.client.get(reverse("overview"), {"organization": self.a.slug})
        self.assertEqual(selected.context["switch_company_label"], self.a.name + " infrastructure")
        self.assertTrue(selected.context["switch_company_active"])
        self.login(self.reader)
        self.assertNotContains(self.client.get(reverse("overview")), 'aria-label="Infrastructure view"')

    def test_duplicate_selectors_identify_slug_id_and_inventory(self):
        first = Organization.objects.create(name="CIRCL", slug="circl-native")
        second = Organization.objects.create(name="CIRCL", slug="circl-registration")
        form = MergeForm()
        html = str(form)
        self.assertIn(first.display_label, html)
        self.assertIn(second.display_label, html)
        self.assertIn("retire_personal_misp", html)
        self.assertNotEqual(str(first), str(second))

    def test_operator_can_open_company_and_platform_without_changing_grants(self):
        self.client.force_login(self.platform)
        response = self.client.post(
            reverse("workspace-switch"), {"action": "company", "organization": self.a.pk}
        )
        self.assertRedirects(response, reverse("overview") + "?organization=" + self.a.slug)
        self.assertEqual(self.client.session[SESSION_COMPANY], self.a.pk)
        self.assertRedirects(
            self.client.get(reverse("workspace-switch") + "?open=company"),
            reverse("overview") + "?organization=" + self.a.slug,
        )
        self.assertRedirects(
            self.client.post(reverse("workspace-switch"), {"action": "platform"}), reverse("circl-overview")
        )
        self.platform.refresh_from_db()
        self.assertTrue(self.platform.is_superuser)
        self.assertFalse(Membership.objects.filter(user=self.platform).exists())

    def test_foreign_company_and_platform_are_denied_to_company_user(self):
        self.client.force_login(self.reader)
        self.assertEqual(
            self.client.post(reverse("workspace-switch"), {"action": "platform"}).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                reverse("workspace-switch"), {"action": "company", "organization": self.b.pk}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("workspace-switch"), {"action": "company", "organization": "https://foreign.invalid"}
            ).status_code,
            403,
        )
        self.assertNotContains(self.client.get(reverse("workspace-switch")), self.b.display_label)

    def test_remembered_company_is_reauthorized_after_membership_revocation(self):
        self.client.force_login(self.reader)
        self.client.post(reverse("workspace-switch"), {"action": "company", "organization": self.a.pk})
        Membership.objects.filter(user=self.reader, organization=self.a).delete()
        response = self.client.get(reverse("workspace-switch") + "?open=company")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.a.display_label)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_selector_is_bounded_searchable_and_post_requires_csrf(self):
        Organization.objects.bulk_create(
            [Organization(name="Same company", slug=f"workspace-{i}") for i in range(30)]
        )
        self.client.force_login(self.platform)
        response = self.client.get(reverse("workspace-switch"), {"q": "Same company"})
        self.assertEqual(len(response.context["workspace_companies"]), 25)
        self.assertTrue(response.context["workspace_more"])
        self.assertEqual(
            len(
                self.client.get(reverse("workspace-switch"), {"q": "workspace-29"}).context[
                    "workspace_companies"
                ]
            ),
            1,
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.platform)
        self.assertEqual(
            client.post(
                reverse("workspace-switch"), {"action": "company", "organization": self.a.pk}
            ).status_code,
            403,
        )

    def test_merge_choices_are_bounded_and_keep_submitted_company_ids(self):
        companies = Organization.objects.bulk_create(
            [Organization(name="Repeated", slug=f"merge-select-{i}") for i in range(65)]
        )
        form = MergeForm()
        self.assertLessEqual(form.fields["source"].queryset.count(), 50)
        form = MergeForm({"source": str(companies[-2].pk), "target": str(companies[-1].pk)})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["target"], companies[-1])
        self.assertLessEqual(form.fields["source"].queryset.count(), 52)
        searched = MergeForm(query="merge-select-64")
        self.assertEqual(list(searched.fields["source"].queryset), [companies[-1]])
