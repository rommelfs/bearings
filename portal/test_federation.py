import copy
import os
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from . import tests, issues, federation
from .connectors.http import ConnectorError
from .models import AssetIssue, CompanyInstance, FederatedReport, Membership


class FederationTests(tests.Fixture):
    def setUp(self):
        self.issue = issues.save_issue(
            self.admin,
            AssetIssue(organization=self.a),
            {
                "asset": self.asset,
                "kind": "support",
                "title": "Synthetic support expiry",
                "source_label": "Synthetic",
                "evidence_text": "Synthetic evidence",
                "shareable": True,
            },
            "Initial review",
        )
        self.client_id = uuid.uuid4()
        self.grant, self.token = federation.create_grant(self.admin, self.a, self.client_id)

    def export(self, **kwargs):
        return self.client.get(
            reverse("federation-export"),
            secure=True,
            HTTP_AUTHORIZATION="Bearer " + self.token,
            HTTP_X_BEARINGS_CLIENT=str(self.client_id),
            **kwargs,
        )

    def test_company_consent_secret_client_binding_and_tls(self):
        with self.assertRaises(PermissionDenied):
            federation.create_grant(self.analyst, self.a, uuid.uuid4())
        self.assertNotIn(self.token.split(".")[1], self.grant.token_hash)
        self.assertEqual(
            self.client.get(
                reverse("federation-export"),
                HTTP_AUTHORIZATION="Bearer " + self.token,
                HTTP_X_BEARINGS_CLIENT=str(self.client_id),
            ).status_code,
            403,
        )
        self.client_id = uuid.uuid4()
        self.assertEqual(self.export().status_code, 403)

    def test_current_sharing_operator_restrictions_and_consent_revocation(self):
        payload = self.export().json()
        self.assertEqual(len(payload["issues"]), 1)
        self.assertEqual(payload["inventory"], [])
        self.assertNotIn("evidence_text", payload["issues"][0])
        self.issue.operator_only = True
        self.issue.save()
        self.assertEqual(self.export().json()["issues"], [])
        self.issue.operator_only = False
        self.issue.shareable = False
        self.issue.save()
        self.assertEqual(self.export().json()["issues"], [])
        Membership.objects.filter(organization=self.a, user=self.admin).update(role="reader")
        self.assertEqual(self.export().status_code, 403)

    def test_expired_disabled_grants_and_bounded_export(self):
        self.grant.expires_at = timezone.now() - timedelta(seconds=1)
        self.grant.save()
        self.assertEqual(self.export().status_code, 403)
        self.grant.expires_at = timezone.now() + timedelta(days=1)
        self.grant.save()
        with patch("portal.federation.MAX_RECORDS", 0):
            self.assertEqual(self.export().status_code, 413)

    def source(self):
        return CompanyInstance.objects.create(
            name="Company pilot",
            organization=self.a,
            remote_organization=self.grant.pk,
            client_id=self.client_id,
            base_url="https://company.example.invalid",
            token_env_var="FEDERATION_ALPHA_TOKEN",
            enabled=True,
        )

    def test_atomic_import_current_config_and_missing_history_no_local_assets(self):
        source = self.source()
        payload = self.export().json()
        with (
            patch.dict(os.environ, {source.token_env_var: self.token}),
            patch("portal.federation.approved_base", return_value=source.base_url),
            patch("portal.federation.request_json", return_value=payload) as request,
        ):
            self.assertEqual(federation.pull(source.pk), 1)
            self.assertEqual(federation.pull(source.pk), 1)
            self.assertEqual(FederatedReport.objects.count(), 1)
            self.assertEqual(request.call_args.args[0], "GET")
            payload["issues"] = []
            federation.pull(source.pk)
        self.assertIsNotNone(FederatedReport.objects.get().missing_since)
        self.assertEqual(AssetIssue.objects.count(), 1)
        self.assertEqual(source.reports.get().payload["title"], self.issue.title)

    def test_partial_wrong_identity_duplicate_or_stale_snapshots_never_replace(self):
        source = self.source()
        original = self.export().json()
        with (
            patch.dict(os.environ, {source.token_env_var: self.token}),
            patch("portal.federation.approved_base", return_value=source.base_url),
            patch("portal.federation.request_json") as request,
        ):
            request.return_value = original
            federation.pull(source.pk)
            for key, value in [
                ("complete", False),
                ("organization", str(uuid.uuid4())),
                ("issues", original["issues"] * 2),
                ("issues", [{"id": 123}]),
                ("generated_at", (timezone.now() - timedelta(days=1)).isoformat()),
            ]:
                payload = copy.deepcopy(original)
                payload[key] = value
                request.return_value = payload
                with self.assertRaises(ConnectorError):
                    federation.pull(source.pk)
                self.assertEqual(FederatedReport.objects.count(), 1)
                self.assertIsNone(FederatedReport.objects.get().missing_since)
        source.refresh_from_db()
        self.assertTrue(source.error)

    def test_disabled_foreign_sources_hide_reports_and_payload_is_escaped(self):
        source = self.source()
        FederatedReport.objects.create(
            source=source,
            resource="issues",
            remote_id=uuid.uuid4(),
            payload={"title": "<script>unsafe</script>"},
            digest="a" * 64,
            seen_at=timezone.now(),
        )
        self.login()
        self.assertContains(self.client.get(reverse("companies")), "&lt;script&gt;unsafe&lt;/script&gt;")
        Membership.objects.filter(user=self.reader).update(organization=self.b)
        self.login(self.reader)
        self.assertNotContains(self.client.get(reverse("companies")), "unsafe")
        source.enabled = False
        source.save()
        self.login()
        self.assertNotContains(self.client.get(reverse("companies")), "unsafe")
