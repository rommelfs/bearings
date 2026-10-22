"""New navigation entry points must preserve evidence and organization visibility."""

from django.urls import reverse

from .models import AuditEvent, Membership, Organization
from .tests import Fixture


class WorkspaceTests(Fixture):
    def test_inventory_is_scoped_searchable_and_does_not_leak_restricted_counts(self):
        self.record_finding(shareable=False)
        # Multiple memberships must not multiply inventory aggregate counts.
        Membership.objects.create(user=self.platform, organization=self.a, role="editor")
        self.login(self.reader)
        response = self.client.get(reverse("inventory"))
        self.assertEqual(response.status_code, 200)
        organizations = list(response.context["page"])
        self.assertEqual([org.pk for org in organizations], [self.a.pk])
        self.assertEqual(organizations[0].asset_count, 1)
        self.assertEqual(organizations[0].finding_count, 0)
        self.assertNotContains(response, self.b.name)
        response = self.client.get(reverse("inventory"), {"q": self.b.name})
        self.assertEqual(response.context["page"].paginator.count, 0)
        response = self.client.get(reverse("inventory"), {"q": "<script>"})
        self.assertNotContains(response, "<script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_operator_inventory_respects_policy_and_audits_sensitive_reads(self):
        self.record_finding(shareable=False)
        self.login(self.analyst)
        response = self.client.get(reverse("inventory"))
        self.assertEqual([org.pk for org in response.context["page"]], [self.a.pk])
        self.assertEqual(response.context["page"][0].finding_count, 1)
        self.assertEqual(response.context["page"][0].asset_count, 1)
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.analyst, organization=self.a, action="operator.access"
            ).exists()
        )
        self.a.operator_visibility = False
        self.a.save()
        response = self.client.get(reverse("inventory"))
        self.assertEqual(response.context["page"].paginator.count, 0)

    def test_nested_routes_keep_orientation_without_granting_admin_or_incident_access(self):
        self.login(self.reader)
        response = self.client.get(self.url("asset", pk=self.asset.pk))
        self.assertEqual(response.context["workspace_area"], "inventory")
        self.assertEqual(response.context["workflow_stage"], "inventory")
        items = [item for group in response.context["navigation_groups"] for item in group["items"]]
        self.assertEqual([item["key"] for item in items if item["active"]], ["inventory"])
        self.assertNotIn("response", [item["key"] for item in items])
        self.assertNotIn("administration", [item["key"] for item in items])
        self.assertNotIn("platform", [item["key"] for item in items])
        self.assertContains(response, self.url("organization") + "#inventory")
        self.assertEqual(self.client.get(reverse("rtir")).status_code, 403)
        self.assertEqual(self.client.get(reverse("demo-data")).status_code, 403)

    def test_inventory_requires_login_and_anonymous_page_has_no_workspace_menu(self):
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 302)
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, 'aria-label="Workspace"')

    def test_empty_inventory_without_a_source_can_be_opened(self):
        org = Organization.objects.create(name="New company", slug="new-company")
        Membership.objects.create(user=self.reader, organization=org, role="reader")
        self.login(self.reader)
        response = self.client.get(reverse("inventory"), {"q": org.name})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Source: Not configured")
        self.assertEqual(response.context["page"][0].asset_count, 0)
