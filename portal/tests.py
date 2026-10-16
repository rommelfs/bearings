import hashlib
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .access import ANALYST_GROUP
from .connectors.http import ConnectorError, approved_base
from .connectors.netbox import write_asset
from .connectors.vulnerability_lookup import lookup
from .models import (
    Asset,
    AuditEvent,
    Contact,
    ContactToken,
    Finding,
    FindingHistory,
    InfrastructureClaim,
    Installation,
    InventorySource,
    NetBoxInstance,
    InventoryWrite,
    Membership,
    Organization,
    Product,
    SourceRecord,
)
from .scope import matches, normalize
from .services import (
    issue_contact_token,
    persist_lookup,
    process_write,
    redeem_contact_token,
    review_contact,
    transition_finding,
)


class Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user("alice", email="alice@example.invalid")
        cls.reader = User.objects.create_user("reader")
        cls.editor = User.objects.create_user("editor")
        cls.analyst = User.objects.create_user("analyst")
        cls.platform = User.objects.create_superuser(
            "platform", "platform@example.invalid", "test-only-password"
        )
        cls.analyst.groups.add(Group.objects.create(name=ANALYST_GROUP))
        cls.a = Organization.objects.create(name="Alpha", slug="alpha", operator_visibility=True)
        cls.b = Organization.objects.create(name="Beta", slug="beta", operator_visibility=False)
        for user, role in [(cls.admin, "admin"), (cls.reader, "reader"), (cls.editor, "editor")]:
            Membership.objects.create(user=user, organization=cls.a, role=role)
        cls.sa = InventorySource.objects.create(organization=cls.a, mode="development")
        cls.sb = InventorySource.objects.create(organization=cls.b, mode="development")
        cls.asset = Asset.objects.create(
            organization=cls.a, source=cls.sa, name="alpha-secret", kind="server"
        )
        cls.other = Asset.objects.create(organization=cls.b, source=cls.sb, name="beta-secret", kind="server")
        cls.product = Product.objects.create(organization=cls.a, name="Example product")
        cls.installation = Installation.objects.create(asset=cls.asset, product=cls.product, version="")
        cls.contact = Contact.objects.create(
            organization=cls.a, name="Security", email="security@example.invalid"
        )

    def login(self, user=None):
        self.client.force_login(user or self.admin)

    def url(self, name, org=None, **kwargs):
        return reverse(name, kwargs={"slug": (org or self.a).slug, **kwargs})

    def record_finding(self, shareable=True):
        r = SourceRecord.objects.create(
            organization=self.a,
            source="fixture://test",
            external_id="CVE-2021-44228",
            payload={},
            shareable=shareable,
        )
        return Finding.objects.create(
            organization=self.a,
            installation=self.installation,
            record=r,
            explanation="Uncertain applicability",
        )


class AccessTests(Fixture):
    def test_unauthenticated_requires_login(self):
        for name in ["organization", "api-inventory", "api-findings"]:
            self.assertEqual(self.client.get(self.url(name)).status_code, 302)

    def test_cross_organization_read_denied(self):
        self.login()
        for name in ["organization", "api-inventory", "api-findings"]:
            self.assertEqual(self.client.get(self.url(name, self.b)).status_code, 404)
        response = self.client.get(self.url("api-inventory"))
        self.assertContains(response, "alpha-secret")
        self.assertNotContains(response, "beta-secret")

    def test_cross_organization_object_injection_denied(self):
        self.login()
        url = self.url("create-installation", pk=self.other.pk)
        self.assertEqual(self.client.post(url, {"product_name": "injected", "version": "1"}).status_code, 404)
        self.assertFalse(Product.objects.filter(name="injected").exists())

    def test_multi_membership_roles_are_independent(self):
        Membership.objects.create(user=self.admin, organization=self.b, role="reader")
        self.login()
        self.assertEqual(self.client.get(self.url("organization", self.b)).status_code, 200)
        self.assertEqual(self.client.post(self.url("create-asset", self.b), {"name": "bad"}).status_code, 403)
        self.assertEqual(self.client.get(self.url("create-asset")).status_code, 200)

    def test_reader_cannot_mutate(self):
        self.login(self.reader)
        for name in ["create-asset", "create-contact", "create-claim"]:
            self.assertEqual(self.client.post(self.url(name), {}).status_code, 403)

    def test_editors_cannot_review_contacts(self):
        self.login(self.editor)
        self.assertEqual(
            self.client.post(self.url("contact-action", pk=self.contact.pk, action="review")).status_code, 403
        )

    def test_analyst_policy_and_audit(self):
        self.login(self.analyst)
        self.assertEqual(self.client.get(self.url("organization")).status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.analyst, action="operator.access", organization=self.a
            ).exists()
        )
        self.assertEqual(self.client.get(self.url("organization", self.b)).status_code, 404)
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.url("api-inventory")).status_code, 404)

    def test_platform_admin_explicit_access(self):
        self.login(self.platform)
        self.assertEqual(self.client.get(self.url("organization", self.b)).status_code, 200)

    def test_organization_cannot_change_visibility_via_form(self):
        self.login()
        response = self.client.post(
            self.url("create-contact"),
            {
                "name": "new",
                "role": "Primary",
                "email": "new@example.invalid",
                "language": "en",
                "time_zone": "UTC",
                "escalation_order": 1,
                "operator_visibility": False,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.a.refresh_from_db()
        self.assertTrue(self.a.operator_visibility)
        self.assertEqual(self.client.get("/admin/portal/organization/").status_code, 302)

    def test_policy_change_is_audited_in_admin(self):
        self.login(self.platform)
        response = self.client.post(
            f"/admin/portal/organization/{self.a.pk}/change/",
            {"name": self.a.name, "slug": self.a.slug, "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(action="operator.configuration_changed")
        self.assertEqual(event.details["previous_visibility"], True)
        self.assertEqual(event.details["visibility"], False)

    def test_operator_dashboard_does_not_leak_restricted_counts(self):
        self.record_finding(shareable=False)
        self.login()
        response = self.client.get("/")
        org = response.context["orgs"][0]
        self.assertEqual(org.finding_count, 0)

    def test_restricted_evidence_hidden_from_member_and_derived_api(self):
        finding = self.record_finding(shareable=False)
        self.login()
        response = self.client.get(self.url("api-findings"))
        self.assertEqual(response.json()["findings"], [])
        self.assertNotContains(self.client.get(self.url("organization")), "Uncertain applicability")
        self.assertEqual(
            self.client.post(
                self.url("finding-review", pk=finding.pk), {"status": "confirmed", "reason": "not allowed"}
            ).status_code,
            404,
        )
        self.login(self.analyst)
        self.assertEqual(len(self.client.get(self.url("api-findings")).json()["findings"]), 1)

    def test_csrf_required_for_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url("create-asset"), {}).status_code, 403)

    def test_untrusted_content_is_escaped(self):
        self.asset.name = '<script>alert("x")</script>'
        self.asset.save()
        self.login()
        response = self.client.get(self.url("organization"))
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")


class ScopeTests(Fixture):
    def claim(self, kind, value, **kw):
        return InfrastructureClaim.objects.create(
            organization=self.a,
            kind=kind,
            value=normalize(kind, value),
            status="verified",
            valid_from=timezone.now() - timedelta(days=2),
            **kw,
        )

    def test_domain_boundary_and_idna(self):
        claim = self.claim("domain", "EXAMPLE.invalid.")
        for good in ["example.invalid", "www.example.invalid"]:
            self.assertTrue(matches(claim, good, timezone.now()))
        for bad in ["notexample.invalid", "example.invalid.evil.test"]:
            self.assertFalse(matches(claim, bad, timezone.now()))
        self.assertEqual(normalize("domain", "bücher.example"), "xn--bcher-kva.example")

    def test_ipv4_ipv6_ranges_and_cidr(self):
        for kind, value, good, bad in [
            ("network", "8.8.8.0/24", "8.8.8.8", "8.8.9.8"),
            ("network", "2606:4700::/32", "2606:4700:4700::1111", "2607::1"),
            ("range", "8.8.8.1-8.8.8.9", "8.8.8.9", "8.8.8.10"),
            ("ip", "1.1.1.1", "1.1.1.1", "1.1.1.2"),
        ]:
            claim = self.claim(kind, value)
            self.assertTrue(matches(claim, good, timezone.now()))
            self.assertFalse(matches(claim, bad, timezone.now()))

    def test_private_scope_requires_same_org_and_context(self):
        claim = self.claim("network", "10.0.0.0/8", network_context="office")
        self.assertFalse(matches(claim, "10.0.0.1", timezone.now()))
        self.assertFalse(matches(claim, "10.0.0.1", timezone.now(), self.b.pk, "office"))
        self.assertFalse(matches(claim, "10.0.0.1", timezone.now(), self.a.pk, "other"))
        self.assertTrue(matches(claim, "10.0.0.1", timezone.now(), self.a.pk, "office"))

    def test_historical_shared_and_disputed_claims(self):
        claim = self.claim("ip", "1.1.1.1", valid_until=timezone.now() - timedelta(days=1))
        self.assertFalse(matches(claim, "1.1.1.1", timezone.now()))
        self.assertTrue(matches(claim, "1.1.1.1", timezone.now() - timedelta(days=1, hours=1)))
        second = self.claim("ip", "1.1.1.1")
        self.assertTrue(matches(second, "1.1.1.1", timezone.now()))
        second.status = "disputed"
        self.assertFalse(matches(second, "1.1.1.1", timezone.now()))

    def test_invalid_claims_rejected(self):
        for kind, value in [
            ("network", "10.0.0.1/8"),
            ("range", "8.8.8.9-8.8.8.1"),
            ("domain", "*.example.invalid"),
            ("ip", "junk"),
        ]:
            with self.assertRaises(ValidationError):
                normalize(kind, value)

    def test_members_cannot_self_verify_authority(self):
        claim = self.claim("ip", "1.1.1.1")
        self.login()
        self.assertEqual(
            self.client.post(
                self.url("claim-review", pk=claim.pk), {"status": "verified", "method": "trust me"}
            ).status_code,
            403,
        )
        self.login(self.analyst)
        self.assertEqual(
            self.client.post(
                self.url("claim-review", pk=claim.pk),
                {"status": "disputed", "method": "Shared assignment unresolved"},
            ).status_code,
            302,
        )
        claim.refresh_from_db()
        self.assertEqual(claim.status, "disputed")
        self.assertEqual(claim.reviewed_by, self.analyst)


class ContactTests(Fixture):
    def test_review_does_not_verify_channel_or_availability(self):
        review_contact(self.admin, self.contact)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.overdue)
        self.assertIsNone(self.contact.reachable_at)
        self.assertIsNone(self.contact.availability_confirmed_at)

    @override_settings(CONTACT_REVIEW_DAYS=10)
    def test_review_interval_configurable(self):
        review_contact(self.admin, self.contact)
        self.assertEqual(self.contact.next_review, timezone.localdate() + timedelta(days=10))

    @patch("portal.services.send_mail")
    def test_token_is_hashed_expiring_and_one_use(self, mail):
        issue_contact_token(self.admin, self.contact)
        raw = mail.call_args.args[1].split("token: ")[1].split()[0]
        token = ContactToken.objects.get(contact=self.contact)
        self.assertNotEqual(token.digest, raw)
        self.assertEqual(token.digest, hashlib.sha256(raw.encode()).hexdigest())
        self.assertTrue(redeem_contact_token(raw))
        self.assertFalse(redeem_contact_token(raw))
        self.contact.refresh_from_db()
        self.assertIsNotNone(self.contact.reachable_at)
        self.assertIsNone(self.contact.reviewed_at)
        self.assertIsNone(self.contact.availability_confirmed_at)

    def test_expired_token_rejected(self):
        ContactToken.objects.create(
            contact=self.contact,
            digest=hashlib.sha256(b"expired").hexdigest(),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertFalse(redeem_contact_token("expired"))

    @patch("portal.management.commands.remind_contacts.send_mail")
    def test_reminders_deduplicate_and_address_admin_only(self, mail):
        call_command("remind_contacts")
        call_command("remind_contacts")
        self.assertEqual(mail.call_count, 1)
        self.assertEqual(mail.call_args.args[3], [self.admin.email])


class InventoryTests(Fixture):
    def test_portal_submission_persisted_then_confirmed(self):
        self.login()
        response = self.client.post(
            self.url("create-asset"),
            {
                "name": "new-device",
                "kind": "server",
                "criticality": "high",
                "lifecycle": "active",
                "organization": self.b.pk,
                "source": self.sb.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        asset = Asset.objects.get(name="new-device")
        self.assertEqual(asset.organization, self.a)
        self.assertEqual(asset.source, self.sa)
        self.assertEqual(asset.state, "pending")
        call_command("process_jobs")
        asset.refresh_from_db()
        self.assertEqual(asset.state, "synced")
        self.assertEqual(asset.object_type, "development.asset")
        call_command("process_jobs")
        self.assertEqual(InventoryWrite.objects.get(asset=asset).attempts, 1)

    @patch("portal.services.write_asset", side_effect=ConnectorError("upstream denied"))
    def test_external_failure_visible_and_last_data_retained(self, write):
        self.asset.external_id = "42"
        self.asset.save()
        job = InventoryWrite.objects.create(asset=self.asset)
        process_write(job.pk)
        self.asset.refresh_from_db()
        self.sa.refresh_from_db()
        self.assertEqual(self.asset.state, "failed")
        self.assertEqual(self.asset.external_id, "42")
        self.assertIsNone(self.sa.last_success)
        self.assertTrue(self.sa.error)
        process_write(job.pk)
        self.assertEqual(write.call_count, 1)
        with patch("portal.services.write_asset", return_value=("dcim.device", "42")):
            process_write(job.pk, force=True)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.state, "synced")
        self.sa.refresh_from_db()
        self.assertFalse(self.sa.error)
        self.assertIsNotNone(self.sa.last_success)

    def test_cross_org_model_links_rejected(self):
        for obj in [
            Asset(organization=self.a, source=self.sb, name="bad", kind="server"),
            Installation(asset=self.other, product=self.product),
        ]:
            with self.assertRaises(ValidationError):
                obj.full_clean()

    def test_unknown_version_not_converted_to_safe(self):
        self.login()
        self.assertIsNone(
            self.client.get(self.url("api-inventory")).json()["assets"][0]["software"][0]["version"]
        )
        self.assertContains(self.client.get(self.url("organization")), "Unknown — applicability uncertain")

    @patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic"})
    @patch("portal.connectors.netbox.approved_base", return_value="https://netbox.example.invalid")
    @patch("portal.connectors.netbox.request_json")
    def test_netbox_recovers_lost_post_without_duplicate(self, request, approved):
        self.sa.instance = NetBoxInstance.objects.create(
            name="test",
            base_url="https://netbox.example.invalid",
            token_env_var="NETBOX_TEST_TOKEN",
            access_mode="read_write",
            site_id=1,
            role_id=2,
            device_type_id=3,
        )
        self.sa.mode, self.sa.tenant_id = "central", 7
        self.sa.save()
        self.asset.refresh_from_db()
        result = {"id": 42, "tenant": {"id": 7}, "custom_fields": {"bearings_id": str(self.asset.pk)}}
        request.side_effect = [{"count": 0, "results": [], "next": None}, ConnectorError("lost response")]
        with self.assertRaises(ConnectorError):
            write_asset(self.asset)
        request.reset_mock()
        request.side_effect = [{"count": 1, "results": [result], "next": None}]
        self.assertEqual(write_asset(self.asset), ("dcim.device", "42"))
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0], "GET")

    @patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic"})
    @patch("portal.connectors.netbox.approved_base", return_value="https://netbox.example.invalid")
    @patch("portal.connectors.netbox.request_json")
    def test_partial_query_never_becomes_delete_or_create(self, request, approved):
        self.sa.instance = NetBoxInstance.objects.create(
            name="test",
            base_url="https://netbox.example.invalid",
            token_env_var="NETBOX_TEST_TOKEN",
            access_mode="read_write",
            site_id=1,
            role_id=2,
            device_type_id=3,
        )
        self.sa.mode, self.sa.tenant_id = "central", 7
        self.sa.save()
        self.asset.refresh_from_db()
        request.return_value = {"count": 2, "results": [{"id": 42}], "next": "untrusted"}
        with self.assertRaises(ConnectorError):
            write_asset(self.asset)
        self.assertEqual(request.call_count, 1)


class EvidenceTests(Fixture):
    def test_lookup_deduplicates_without_changing_analyst_review(self):
        payload = {"cveMetadata": {"cveId": "CVE-2021-44228"}}
        finding = persist_lookup(self.admin, self.installation, "fixture://test", "CVE-2021-44228", payload)
        self.assertEqual(finding.applicability, "unknown")
        self.assertEqual(finding.category, "technological_relevance")
        self.assertIn("applicability has not been established", finding.explanation)
        transition_finding(self.admin, finding, "accepted_risk", "Reviewed; compensating control")
        again = persist_lookup(self.admin, self.installation, "fixture://test", "CVE-2021-44228", payload)
        self.assertEqual(again.pk, finding.pk)
        self.assertEqual(again.status, "accepted_risk")
        self.assertEqual(FindingHistory.objects.get().reason, "Reviewed; compensating control")
        self.assertEqual(SourceRecord.objects.count(), 1)

    def test_workflow_requires_reason(self):
        finding = self.record_finding()
        self.login()
        self.client.post(self.url("finding-review", pk=finding.pk), {"status": "resolved", "reason": ""})
        finding.refresh_from_db()
        self.assertEqual(finding.status, "new")
        self.assertEqual(FindingHistory.objects.count(), 0)

    @patch(
        "portal.connectors.vulnerability_lookup.approved_base", return_value="https://vulnerability.circl.lu"
    )
    @patch("portal.connectors.vulnerability_lookup.request_json")
    def test_real_adapter_contract_and_identity_validation(self, request, approved):
        request.return_value = {"cveMetadata": {"cveId": "CVE-2021-44228", "state": "PUBLISHED"}}
        base, data = lookup("cve-2021-44228")
        self.assertEqual(data["cveMetadata"]["cveId"], "CVE-2021-44228")
        self.assertTrue(request.call_args.args[1].endswith("/api/vulnerability/CVE-2021-44228"))
        request.return_value = {}
        with self.assertRaises(ConnectorError):
            lookup("CVE-2021-44228")
        request.return_value = {"cveMetadata": {"cveId": "CVE-2021-9999"}}
        with self.assertRaises(ConnectorError):
            lookup("CVE-2021-44228")

    def test_destination_controls(self):
        for url in [
            "http://example.invalid",
            "https://user:secret@example.invalid",
            "https://example.invalid?token=x",
        ]:
            with self.assertRaises(ConnectorError):
                approved_base(url)
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ConnectorError):
                approved_base("https://internal.example.invalid")

    def test_demo_repeatable_and_clearly_labeled(self):
        call_command("seed_demo", no_users=True)
        call_command("seed_demo", no_users=True)
        org = Organization.objects.get(slug="example-labs")
        self.assertEqual(org.assets.count(), 1)
        self.assertEqual(org.findings.count(), 1)
        self.assertTrue(org.findings.get().record.payload["fixture"])


class ExtendedWorkflowTests(Fixture):
    def test_contact_edit_invalidates_only_appropriate_verification(self):
        self.contact.reachable_at = self.contact.reviewed_at = self.contact.availability_confirmed_at = (
            timezone.now()
        )
        self.contact.next_review = timezone.localdate() + timedelta(days=10)
        self.contact.save()
        ContactToken.objects.create(
            contact=self.contact, digest="a" * 64, expires_at=timezone.now() + timedelta(days=1)
        )
        self.login()
        response = self.client.post(
            self.url("edit-contact", pk=self.contact.pk),
            {
                "name": "Security",
                "role": self.contact.role,
                "email": "changed@example.invalid",
                "language": "en",
                "time_zone": self.contact.time_zone,
                "escalation_order": 1,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.contact.refresh_from_db()
        self.assertIsNone(self.contact.reachable_at)
        self.assertIsNone(self.contact.reviewed_at)
        self.assertIsNone(self.contact.next_review)
        self.assertIsNotNone(self.contact.availability_confirmed_at)
        self.assertIsNotNone(ContactToken.objects.get(contact=self.contact).used_at)

    def test_product_selection_is_scoped_and_persists_relationship(self):
        foreign = Product.objects.create(organization=self.b, name="foreign-product")
        self.login()
        url = self.url("create-installation", pk=self.asset.pk)
        response = self.client.post(url, {"existing_product": foreign.pk, "version": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Installation.objects.count(), 1)
        response = self.client.post(url, {"existing_product": self.product.pk, "version": "1.2"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Installation.objects.get(version="1.2").product, self.product)

    def test_analyst_override_keeps_original_evidence_and_assessment(self):
        finding = self.record_finding()
        original = finding.explanation
        self.login(self.analyst)
        response = self.client.post(
            self.url("finding-review", pk=finding.pk),
            {"status": "under_review", "assessment": "not_affected", "reason": "Vendor backport verified"},
        )
        self.assertEqual(response.status_code, 302)
        finding.refresh_from_db()
        self.assertEqual(finding.applicability, "unknown")
        self.assertEqual(finding.analyst_applicability, "not_affected")
        self.assertEqual(finding.explanation, original)
        self.assertEqual(finding.history.get().previous_assessment, "unassessed")

    def test_restricted_raw_evidence_is_also_denied(self):
        finding = self.record_finding(shareable=False)
        self.login()
        self.assertEqual(self.client.get(self.url("api-evidence", pk=finding.pk)).status_code, 404)
        self.login(self.analyst)
        self.assertEqual(self.client.get(self.url("api-evidence", pk=finding.pk)).status_code, 200)
        self.assertEqual(self.client.get(self.url("api-evidence", self.b, pk=finding.pk)).status_code, 404)

    @override_settings(CONNECTOR_PROXY_DNS=True, CONNECTOR_ALLOWED_HOSTS=["approved.example.invalid"])
    @patch.dict("os.environ", {"HTTPS_PROXY": "http://proxy.example.invalid:8080"})
    def test_proxy_dns_requires_exact_operator_host_and_blocks_private_literal(self):
        self.assertEqual(
            approved_base("https://approved.example.invalid"), "https://approved.example.invalid"
        )
        for url in ["https://unapproved.example.invalid", "https://127.0.0.1"]:
            with self.assertRaises(ConnectorError):
                approved_base(url)

    def test_existing_source_cannot_be_repointed(self):
        self.sa.mode = "central"
        self.sa.tenant_id = 123
        with self.assertRaises(ValidationError):
            self.sa.full_clean()

    @patch.dict("os.environ", {"NETBOX_TEST_TOKEN": "synthetic"})
    @patch("portal.connectors.netbox.approved_base", return_value="https://netbox.example.invalid")
    @patch("portal.connectors.netbox.request_json")
    def test_netbox_rejects_cross_tenant_identity(self, request, approved):
        self.sa.instance = NetBoxInstance.objects.create(
            name="test",
            base_url="https://netbox.example.invalid",
            token_env_var="NETBOX_TEST_TOKEN",
            access_mode="read_write",
            site_id=1,
            role_id=2,
            device_type_id=3,
        )
        self.sa.mode, self.sa.tenant_id = "central", 7
        self.sa.save()
        self.asset.refresh_from_db()
        request.return_value = {
            "count": 1,
            "results": [
                {"id": 42, "tenant": {"id": 999}, "custom_fields": {"bearings_id": str(self.asset.pk)}}
            ],
            "next": None,
        }
        with self.assertRaises(ConnectorError):
            write_asset(self.asset)

    def test_end_to_end_inventory_to_both_views(self):
        self.login()
        response = self.client.post(
            self.url("create-asset"),
            {"name": "vertical-slice", "kind": "vm", "criticality": "normal", "lifecycle": "active"},
        )
        self.assertEqual(response.status_code, 302)
        asset = Asset.objects.get(name="vertical-slice")
        response = self.client.post(
            self.url("create-installation", pk=asset.pk),
            {"product_name": "New platform", "product_identifier": "pkg:pypi/example", "version": "3.1"},
        )
        self.assertEqual(response.status_code, 302)
        call_command("process_jobs")
        for user in [self.admin, self.analyst]:
            self.login(user)
            page = self.client.get(self.url("organization"))
            self.assertContains(page, "vertical-slice")
            self.assertContains(page, "New platform")
            self.assertContains(page, "3.1")
            self.assertContains(page, "DEVELOPMENT fixture")
        self.login(self.reader)
        self.assertEqual(self.client.post(self.url("create-installation", pk=asset.pk), {}).status_code, 403)
