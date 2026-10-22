"""Human-readable catalog selection, scoped previews and reviewed-revision approval."""

from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.utils import timezone
from .test_intelligence import IntelligenceTests, RISK
from . import tests
from .models import RiskLink
from .intelligence import resolve_risk, link_risk


class ScenarioPickerTests(tests.Fixture):
    def setUp(self):
        IntelligenceTests.setUp(self)
        self.revision = resolve_risk(self.source.pk, RISK)
        self.risk = self.revision.risk
        self.network.reset_mock()
        self.login()
        self.path = self.url("create-risk-link", pk=self.finding.pk)

    def confirmation(self, **overrides):
        return {
            "source": self.source.pk,
            "risk_uuid": RISK,
            "reviewed_revision": self.revision.pk,
            "reason": "Review possible impact on this server",
            **overrides,
        }

    def test_integrated_search_preview_never_asks_for_uuid_and_get_does_not_link(self):
        response = self.client.get(self.path)
        self.assertContains(response, "Search the MOSP catalog")
        self.assertContains(response, "Preview this scenario")
        self.assertNotContains(response, 'name="risk_uuid"')
        response = self.client.get(self.path, {"risk": self.risk.pk})
        self.assertContains(response, "Threat")
        self.assertContains(response, "Catalog asset type")
        self.assertContains(response, "General weakness")
        self.assertContains(response, "Confirm scenario &amp; pin evidence")
        self.assertContains(response, 'type="hidden" name="risk_uuid"')
        self.assertNotContains(response, "MONARC risk UUID:")
        self.assertFalse(RiskLink.objects.exists())
        self.network.assert_not_called()

    def test_guided_case_context_survives_search_preview_and_confirmation(self):
        response = self.client.get(self.path, {"risk": self.risk.pk, "return": "guide"})
        self.assertContains(response, "Return to the guided case")
        self.assertContains(response, 'name="return" value="guide"')
        response = self.client.post(self.path + "?return=guide", self.confirmation())
        self.assertRedirects(response, self.url("case-guide", pk=self.finding.pk) + "?step=action")

    def test_searches_related_threat_and_empty_search_has_clear_state(self):
        response = self.client.get(self.path, {"q": "Synthetic threat"})
        self.assertContains(response, "Synthetic risk")
        response = self.client.get(self.path, {"q": "unmatched-query"})
        self.assertContains(response, "No matching scenarios")
        self.network.assert_not_called()

    def test_confirmation_pins_reviewed_revision_and_requires_reason_and_preview(self):
        response = self.client.post(self.path, self.confirmation(reason=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertFalse(RiskLink.objects.exists())
        self.network.assert_not_called()
        response = self.client.post(self.path, self.confirmation(reviewed_revision=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RiskLink.objects.exists())
        response = self.client.post(self.path, self.confirmation())
        self.assertEqual(response.status_code, 302)
        link = RiskLink.objects.get()
        self.assertEqual(link.risk_revision_id, self.revision.pk)
        self.assertEqual(link.created_by, self.admin)

    def test_changed_catalog_requires_reconfirmation_and_retains_reason(self):
        self.bundle["threat"]["description"] = "Changed upstream description"
        response = self.client.post(self.path, self.confirmation())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "catalog scenario changed")
        self.assertContains(response, "Changed upstream description")
        self.assertContains(response, "Review possible impact on this server")
        self.assertFalse(RiskLink.objects.exists())
        self.risk.refresh_from_db()
        self.assertContains(response, f'name="reviewed_revision" value="{self.risk.current_revision_id}"')
        response = self.client.post(
            self.path, self.confirmation(reviewed_revision=self.risk.current_revision_id)
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RiskLink.objects.get().risk_revision_id, self.risk.current_revision_id)

    def test_unavailable_sources_and_missing_scenarios_cannot_be_confirmed(self):
        self.risk.missing_since = timezone.now()
        self.risk.save()
        self.assertEqual(self.client.get(self.path, {"risk": self.risk.pk}).status_code, 404)
        self.assertEqual(self.client.post(self.path, self.confirmation()).status_code, 200)
        self.assertFalse(RiskLink.objects.exists())
        self.source.enabled = False
        self.source.save()
        self.assertNotContains(self.client.get(self.path), "Preview this scenario")
        self.network.assert_not_called()

    def test_permissions_malformed_selection_and_untrusted_text(self):
        self.assertEqual(self.client.get(self.path, {"risk": "not-an-id"}).status_code, 404)
        self.assertEqual(self.client.get(self.path, {"catalog": "invalid"}).status_code, 404)
        self.login(self.reader)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.login()
        self.assertEqual(
            self.client.get(self.url("create-risk-link", self.b, pk=self.finding.pk)).status_code, 404
        )
        self.risk.description = '<script>alert("catalog")</script>'
        self.risk.save()
        response = self.client.get(self.path, {"risk": self.risk.pk})
        self.assertNotContains(response, '<script>alert("catalog")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_uncached_details_are_fetched_only_on_explicit_preview_and_outages_do_not_link(self):
        self.risk.current_revision = None
        self.risk.save()
        self.client.get(self.path)
        self.network.assert_not_called()
        from .connectors.http import ConnectorError

        with patch("portal.intelligence_views.resolve_risk", side_effect=ConnectorError("offline")):
            response = self.client.get(self.path, {"risk": self.risk.pk})
        self.assertContains(response, "Complete scenario details are unavailable")
        self.assertNotContains(response, "Confirm scenario &amp; pin evidence")
        self.assertFalse(RiskLink.objects.exists())
        self.assertEqual(self.client.get(self.path, {"risk": self.risk.pk}).status_code, 200)
        self.network.assert_called_once()
        self.assertFalse(RiskLink.objects.exists())

    def test_service_rejects_unreviewed_revision(self):
        with self.assertRaises(ValidationError):
            link_risk(
                self.admin, self.finding, self.source.pk, RISK, "Synthetic reason", expected_revision=-1
            )
        self.assertFalse(RiskLink.objects.exists())
