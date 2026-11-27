import os
from pathlib import Path

from django.test import Client
from django.urls import reverse
from .tests import Fixture
from .models import InventoryReviewPolicy, Organization, Membership, InventorySource
from .workspace_views import SESSION_COMPANY
from .member_views import MergeForm


class WorkspaceTests(Fixture):
    def test_visible_view_switch_marks_actual_company_and_national_destinations(self):
        org = Organization.objects.create(name="CIRCL", slug="circl")
        InventorySource.objects.create(organization=org, mode="manual")
        Membership.objects.create(user=self.platform, organization=org, role="reader")
        self.login(self.platform)
        national = self.client.get(reverse("circl-overview"))
        self.assertContains(national, 'aria-label="Switch workspace"')
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
        self.assertNotContains(self.client.get(reverse("overview")), 'aria-label="Switch workspace"')

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

    def test_company_and_national_menus_have_contextual_scoped_destinations(self):
        circl = Organization.objects.create(name="CIRCL", slug="circl")
        InventorySource.objects.create(organization=circl, mode="manual")
        Membership.objects.create(user=self.platform, organization=circl, role="admin")
        self.login(self.platform)
        response = self.client.get(reverse("overview"), {"organization": "circl"})
        items = {
            item["key"]: item for group in response.context["navigation_groups"] for item in group["items"]
        }
        self.assertIn("clients", items)
        self.assertEqual(response.context["workspace_landing"]["key"], "overview")
        self.assertEqual(response.context["workspace_scope_label"], "CIRCL infrastructure")
        self.assertNotIn("national", items)
        self.assertNotIn("registrations", items)
        self.assertNotIn("platform", items)
        self.assertNotIn("research", items)
        self.assertEqual(items["inventory"]["url"], reverse("organization", args=["circl"]))
        self.assertEqual(items["review"]["url"], reverse("intelligence", args=["circl"]))
        self.assertEqual(items["clients"]["url"], reverse("client-platforms") + "?organization=circl")
        self.assertEqual(items["discovery"]["url"], reverse("discovery") + "?organization=circl")
        directory = os.environ.get("BEARINGS_WORKSPACE_UI_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "company.html").write_bytes(response.content)
        national = self.client.get(reverse("circl-overview"))
        items = {
            item["key"]: item for group in national.context["navigation_groups"] for item in group["items"]
        }
        self.assertEqual(national.context["workspace_landing"]["key"], "national")
        self.assertEqual(national.context["workspace_scope_label"], "National")
        self.assertIn("research", items)
        self.assertIn("followups", items)
        self.assertIn("registrations", items)
        self.assertEqual(items["organizations"]["url"], reverse("inventory"))
        self.assertEqual(items["infrastructure-status"]["url"], reverse("overview"))
        self.assertEqual(items["national-evidence"]["url"], reverse("circl-findings"))
        self.assertTrue({"clients", "settings", "members", "actions", "risks", "exposure"}.isdisjoint(items))
        self.assertNotContains(national, 'class="nav-client-group"')
        self.assertNotContains(national, 'href="/downloads/rollout/"')
        self.assertNotContains(national, 'href="/downloads/profiles/"')
        self.assertEqual(national.context["switch_company_url"], reverse("overview") + "?organization=circl")
        if directory:
            (Path(directory) / "national.html").write_bytes(national.content)
        self.assertEqual(Membership.objects.get(user=self.platform, organization=circl).role, "admin")

    def test_explicit_company_links_survive_other_tab_context_and_global_routes_stay_wide(self):
        self.login(self.platform)
        self.client.post(reverse("workspace-switch"), {"action": "company", "organization": self.a.pk})
        self.client.get(reverse("circl-overview"))
        company = self.client.get(
            reverse("discovery"), {"organization": self.a.slug, "workspace": "national"}
        )
        self.assertTrue(company.context["switch_company_active"])
        self.assertEqual(company.context["navigation_company"].pk, self.a.pk)
        wide = self.client.get(reverse("home"))
        self.assertTrue(wide.context["workspace_national"])
        self.assertFalse(wide.context["switch_company_active"])
        self.assertFalse(wide.context["navigation_company"])
        self.login(self.reader)
        self.assertEqual(
            self.client.get(reverse("circl-overview"), {"workspace": "national"}).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse("discovery"), {"organization": self.b.slug, "workspace": "company"}
            ).status_code,
            404,
        )

    def test_national_infrastructure_status_and_explicit_company_transition(self):
        self.login(self.platform)
        status = self.client.get(reverse("overview"))
        self.assertEqual(status.context["workspace_scope_label"], "National")
        self.assertEqual(status.context["workspace_area"], "infrastructure-status")
        self.assertContains(status, "<h1>Company infrastructure status</h1>", html=True)
        if directory := os.environ.get("BEARINGS_WORKSPACE_UI_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "wide.html").write_bytes(status.content)
        organizations = self.client.get(reverse("inventory"))
        self.assertContains(organizations, "Open company workspace")
        link = reverse("overview") + "?organization=" + self.a.slug
        self.assertContains(organizations, f'href="{link}"')
        company = self.client.get(link)
        self.assertContains(company, "<h1>Infrastructure overview</h1>", html=True)
        self.assertEqual(company.context["workspace_scope_label"], self.a.name + " infrastructure")

    def test_inventory_disclosures_open_on_active_child_and_keep_company_permissions(self):
        self.login(self.admin)
        url = reverse("windows-client-downloads") + "?organization=" + self.a.slug
        response = self.client.get(url)
        groups = {group["label"]: group["open"] for group in response.context["navigation_groups"]}
        self.assertTrue(groups["Inventory"])
        self.assertFalse(groups["Security"])
        self.assertContains(response, '<details class="nav-client-group" open>', count=2)
        self.assertContains(response, f'href="{url}" aria-current="page"')
        self.assertContains(response, f'href="{reverse("client-rollouts")}?organization={self.a.slug}"')
        if directory := os.environ.get("BEARINGS_WORKSPACE_UI_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "windows.html").write_bytes(response.content)
        self.login(self.reader)
        response = self.client.get(url)
        self.assertNotContains(response, f'href="{reverse("client-rollouts")}?organization={self.a.slug}"')
        self.assertNotContains(response, f'href="{reverse("client-profiles")}?organization={self.a.slug}"')

    def test_company_help_link_survives_navigation_to_another_company(self):
        self.login(self.platform)
        first = self.client.get(reverse("overview"), {"organization": self.a.slug})
        links = {
            item["key"]: item["url"]
            for group in first.context["navigation_groups"]
            for item in group["items"]
        }
        self.client.get(reverse("overview"), {"organization": self.b.slug})
        help_page = self.client.get(links["start"])
        self.assertEqual(help_page.context["navigation_company"].pk, self.a.pk)
        self.assertEqual(help_page.context["workspace_scope_label"], self.a.name + " infrastructure")

    def test_review_followup_keeps_the_context_of_its_explicit_entry_point(self):
        InventoryReviewPolicy.objects.create(organization=self.b)
        self.login(self.platform)
        self.client.get(reverse("overview"), {"organization": self.a.slug})
        followup = reverse("review-followup", args=[self.b.slug])
        queue = self.client.get(reverse("review-followups"))
        self.assertContains(queue, f'href="{followup}?workspace=national"')
        national = self.client.get(followup, {"workspace": "national"})
        self.assertEqual(national.context["workspace_area"], "followups")
        self.assertEqual(national.context["workspace_scope_label"], "National")
        self.assertEqual(self.client.session[SESSION_COMPANY], self.a.pk)
        company = self.client.get(followup)
        self.assertEqual(company.context["workspace_area"], "inventory")
        self.assertEqual(company.context["navigation_company"].pk, self.b.pk)
