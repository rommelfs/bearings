import io
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest import skipUnless
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import connection, close_old_connections, connections
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from . import tests, flowintel
from .connectors.http import ConnectorError
from .connectors import flowintel as connector
from .models import FlowIntelInstance, FlowIntelCase, AuditEvent


class FakeAPI:
    def __init__(self, instance):
        self.instance, self.case, self.tasks, self.writes = instance, None, [], []
        self.lose_case = self.lose_task = False

    def __call__(self, instance, method, path, *, payload=None):
        if method == "POST":
            self.writes.append((path, payload))
        if path == "case/create":
            self.case = {
                **payload,
                "id": 7,
                "uuid": str(uuid.uuid4()),
                "owner_org_id": instance.service_org_id,
                "orgs": [{"id": instance.service_org_id}],
                "completed": False,
                "status_id": 99,
                "deadline": "2026-12-01 17:00",
            }
            if self.lose_case:
                raise ConnectorError("Simulated lost acknowledgment")
            return {"case_id": 7}
        if path == "case/7/create_task":
            task = {
                **payload,
                "id": 100 + len(self.tasks),
                "case_id": 7,
                "completed": False,
                "status_id": 99,
                "deadline": "2026-12-01 17:00",
                "notes": "Do not import arbitrary notes",
            }
            self.tasks.append(task)
            if self.lose_task:
                raise ConnectorError("Simulated lost task acknowledgment")
            return {"task_id": task["id"]}
        if path == "case/7":
            return self.case.copy()
        if path == "case/all":
            return {"cases": [self.case] if self.case and not self.case["completed"] else []}
        if path == "case/completed":
            return {"cases": [self.case] if self.case and self.case["completed"] else []}
        if path == "case/7/tasks":
            return [t.copy() for t in self.tasks if not t["completed"]]
        if path == "case/7/tasks_finished":
            return [t.copy() for t in self.tasks if t["completed"]]
        if path == "case/list_status":
            return [{"id": 99, "name": "Review"}]
        raise AssertionError((method, path))


class FlowIntelTests(tests.Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.instance = FlowIntelInstance.objects.create(
            name="FlowIntel alpha",
            base_url="https://flowintel.example.invalid",
            browser_url="https://cases.example.invalid",
            token_env_var="FLOWINTEL_ALPHA_TOKEN",
            service_org_id=3,
        )
        self.fake = FakeAPI(self.instance)
        self.mock = patch("portal.flowintel.api", side_effect=self.fake).start()
        self.addCleanup(patch.stopall)

    def preview(self):
        return flowintel.preview(
            self.analyst,
            self.finding,
            self.instance,
            timezone.localdate() + timedelta(days=7),
            "Coordinate review and remediation",
        )

    def approve(self):
        binding = self.preview()
        flowintel.approve(self.analyst, binding.pk)
        return binding

    def complete(self):
        binding = self.approve()
        for _ in range(6):
            flowintel.process(binding.pk)
        flowintel.refresh(binding.pk)
        binding.refresh_from_db()
        return binding

    def test_preview_is_local_scoped_and_readable_before_approval(self):
        binding = self.preview()
        self.mock.assert_not_called()
        self.assertEqual(binding.tasks.count(), 4)
        self.assertEqual(binding.state, "draft")
        self.assertIn("unknown", binding.description)
        self.assertIn("business risk remains unassessed", binding.description)
        self.login(self.analyst)
        response = self.client.get(reverse("flowintel-case", args=[self.a.slug, binding.pk]))
        self.assertContains(response, "Approve private case &amp; task export")
        self.assertContains(response, "alpha-secret")
        self.assertTrue(AuditEvent.objects.filter(action="flowintel.preview").exists())

    def test_company_reader_and_foreign_organization_cannot_export(self):
        for user in [self.admin, self.reader, self.editor]:
            with self.assertRaises(PermissionDenied):
                flowintel.preview(user, self.finding, self.instance, None, "Attempt")
        self.a.operator_visibility = False
        self.a.save()
        with self.assertRaises(PermissionDenied):
            self.preview()
        self.mock.assert_not_called()

    def test_inconsistent_cross_organization_installation_is_denied_before_export(self):
        from .models import Finding, Installation, Product

        product = Product.objects.create(organization=self.b, name="Foreign private software")
        installation = Installation.objects.create(asset=self.other, product=product)
        Finding.objects.filter(pk=self.finding.pk).update(installation=installation)
        with self.assertRaises(PermissionDenied):
            self.preview()
        self.mock.assert_not_called()

    def test_restricted_evidence_even_operator_cannot_export(self):
        self.finding.record.shareable = False
        self.finding.record.save(update_fields=["shareable"])
        with self.assertRaises(PermissionDenied):
            self.preview()
        self.login(self.analyst)
        self.assertNotContains(self.client.get(self.url("intelligence")), "Prepare private FlowIntel case")
        self.mock.assert_not_called()

    def test_private_case_playbook_and_read_only_status_leave_finding_unchanged(self):
        binding = self.complete()
        self.assertEqual(binding.state, "linked")
        self.assertEqual(len(self.fake.writes), 5)
        self.assertIs(self.fake.writes[0][1]["is_private"], True)
        self.assertEqual(self.fake.writes[0][1]["ticket_id"], str(binding.pk))
        self.assertEqual(binding.remote_id, 7)
        self.assertEqual(binding.case_url, "https://cases.example.invalid/case/7")
        self.assertEqual(binding.summary["status"], "Review")
        self.assertEqual(len(binding.summary["tasks"]), 4)
        self.assertNotIn("Do not import arbitrary notes", str(binding.summary))
        self.fake.case["completed"] = True
        self.fake.case["status_id"] = ["malformed external value"]
        for task in self.fake.tasks:
            task["completed"] = True
            task["status_id"] = {}
        flowintel.refresh(binding.pk)
        binding.refresh_from_db()
        self.assertTrue(binding.summary["completed"])
        self.assertEqual(binding.summary["status"], "Unknown")
        self.assertTrue(all(task["status"] == "Unknown" for task in binding.summary["tasks"]))
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, "new")
        self.assertEqual(self.finding.analyst_applicability, "unassessed")
        self.assertEqual(len(self.fake.writes), 5)

    def test_repeat_preview_approval_and_worker_cannot_duplicate_case(self):
        binding = self.complete()
        self.assertEqual(self.preview().pk, binding.pk)
        with self.assertRaises(ValidationError):
            flowintel.approve(self.analyst, binding.pk)
        flowintel.process(binding.pk)
        self.assertEqual(len(self.fake.writes), 5)

    def test_changed_evidence_asset_assessment_or_context_blocks_approval(self):
        for obj, field, value in [
            (self.finding.record, "payload", {"changed": True}),
            (self.asset, "name", "changed"),
            (self.finding, "analyst_applicability", "affected"),
            (self.instance, "bearings_url", "https://bearings.example.invalid"),
        ]:
            binding = self.preview()
            old = getattr(obj, field)
            setattr(obj, field, value)
            obj.save()
            with self.assertRaises(ValidationError):
                flowintel.approve(self.analyst, binding.pk)
            setattr(obj, field, old)
            obj.save()
        self.mock.assert_not_called()

    def test_revoked_visibility_after_approval_blocks_worker(self):
        binding = self.approve()
        self.a.operator_visibility = False
        self.a.save()
        flowintel.process(binding.pk)
        binding.refresh_from_db()
        self.assertEqual(binding.state, "blocked")
        self.mock.assert_not_called()
        self.login(self.analyst)
        self.assertEqual(
            self.client.get(reverse("flowintel-case", args=[self.a.slug, binding.pk])).status_code, 404
        )

    def test_recheck_between_committed_claim_and_post(self):
        binding = self.approve()
        real_claim = flowintel.claim

        def revoke(pk):
            result = real_claim(pk)
            self.finding.record.shareable = False
            self.finding.record.save(update_fields=["shareable"])
            return result

        with patch("portal.flowintel.claim", side_effect=revoke):
            flowintel.process(binding.pk)
        self.mock.assert_not_called()
        binding.refresh_from_db()
        self.assertEqual(binding.state, "uncertain")

    def test_disabled_or_deactivated_actor_blocks_outbox(self):
        binding = self.approve()
        self.analyst.is_active = False
        self.analyst.save()
        flowintel.process(binding.pk)
        self.mock.assert_not_called()
        self.analyst.is_active = True
        self.analyst.save()
        self.instance.enabled = False
        self.instance.save()
        with self.assertRaises(PermissionDenied):
            self.preview()

    def test_lost_case_ack_reconciles_using_reads_without_second_post(self):
        binding = self.approve()
        self.fake.lose_case = True
        flowintel.process(binding.pk)
        binding.refresh_from_db()
        self.assertEqual(binding.state, "uncertain")
        self.assertIsNone(binding.remote_id)
        flowintel.process(binding.pk)
        flowintel.reconcile(binding.pk)
        binding.refresh_from_db()
        self.assertEqual(binding.remote_id, 7)
        self.assertEqual(binding.state, "building")
        self.assertEqual(len(self.fake.writes), 1)

    def test_remote_identity_collision_is_retained_as_uncertain_without_retry(self):
        self.finding.record.external_id = "CVE-2024-1234"
        self.finding.record.save(update_fields=["external_id"])
        first = self.complete()
        second_finding = self.record_finding()
        second = flowintel.preview(self.analyst, second_finding, self.instance, None, "Another review")
        flowintel.approve(self.analyst, second.pk)
        count = len(self.fake.writes)
        flowintel.process(second.pk)
        second.refresh_from_db()
        self.assertEqual(second.state, "uncertain")
        self.assertIsNone(second.remote_id)
        self.assertEqual(FlowIntelCase.objects.get(pk=first.pk).remote_id, 7)
        flowintel.process(second.pk)
        self.assertEqual(len(self.fake.writes), count + 1)
        with self.assertRaises(ConnectorError):
            flowintel.reconcile(second.pk)
        self.assertEqual(len(self.fake.writes), count + 1)

    def test_unknown_case_outcome_never_resubmits_when_not_found(self):
        binding = self.approve()
        with patch("portal.flowintel.api", side_effect=ConnectorError("Offline")):
            flowintel.process(binding.pk)
        with self.assertRaises(ConnectorError):
            flowintel.reconcile(binding.pk)
        flowintel.process(binding.pk)
        self.assertEqual(len(self.fake.writes), 0)

    def test_lost_task_ack_reconciles_without_second_task_post(self):
        binding = self.approve()
        flowintel.process(binding.pk)
        self.fake.lose_task = True
        flowintel.process(binding.pk)
        self.assertEqual(len(self.fake.tasks), 1)
        flowintel.reconcile(binding.pk)
        self.assertEqual(binding.tasks.filter(state="linked").count(), 1)
        self.assertEqual(len(self.fake.writes), 2)

    def test_crash_during_active_lease_does_not_allow_immediate_reconciliation(self):
        binding = self.approve()
        self.assertEqual(flowintel.claim(binding.pk), 0)
        with self.assertRaisesMessage(ValidationError, "still in progress"):
            flowintel.reconcile(binding.pk)
        self.mock.assert_not_called()

    def test_privacy_foreign_org_or_ticket_change_rejects_external_status(self):
        binding = self.complete()
        original_summary = binding.summary.copy()
        for field, value in [
            ("is_private", False),
            ("orgs", [{"id": 3}, {"id": 9}]),
            ("owner_org_id", 9),
            ("ticket_id", "foreign"),
            ("uuid", str(uuid.uuid4())),
        ]:
            old = self.fake.case[field]
            self.fake.case[field] = value
            with self.assertRaises(ConnectorError):
                flowintel.refresh(binding.pk)
            binding.refresh_from_db()
            self.assertEqual(binding.summary, original_summary)
            self.fake.case[field] = old

    def test_wrong_task_parent_invalidates_refresh(self):
        binding = self.complete()
        self.fake.tasks[0]["case_id"] = 99
        with self.assertRaises(ConnectorError):
            flowintel.refresh(binding.pk)

    def test_outage_retains_last_known_state_and_escapes_html(self):
        binding = self.complete()
        original = binding.summary.copy()
        with patch("portal.flowintel.api", side_effect=ConnectorError("Offline")):
            with self.assertRaises(ConnectorError):
                flowintel.refresh(binding.pk)
        binding.refresh_from_db()
        self.assertEqual(binding.summary, original)
        binding.summary["status"] = "<script>alert(1)</script>"
        binding.save()
        self.login(self.analyst)
        response = self.client.get(reverse("flowintel-case", args=[self.a.slug, binding.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
        self.login()
        self.assertEqual(
            self.client.get(reverse("flowintel-case", args=[self.a.slug, binding.pk])).status_code, 404
        )

    def test_instance_binding_and_credential_reference_are_immutable_after_preview(self):
        self.preview()
        for field, value in [
            ("base_url", "https://other.example.invalid"),
            ("token_env_var", "FLOWINTEL_OTHER_TOKEN"),
            ("service_org_id", 9),
        ]:
            obj = FlowIntelInstance.objects.get(pk=self.instance.pk)
            setattr(obj, field, value)
            with self.assertRaises(ValidationError):
                obj.full_clean()

    def test_disabling_bundled_profile_pauses_queued_work_without_claiming_a_write(self):
        self.instance.name = "bundled-flowintel"
        self.instance.save()
        binding = self.approve()
        with patch.dict(os.environ, {"BEARINGS_DEV_STACK": "1", "BEARINGS_FLOWINTEL": "0"}):
            call_command("process_flowintel", all=True, stdout=io.StringIO())
            self.assertFalse(self.instance.available)
        binding.refresh_from_db()
        self.assertEqual(binding.state, "queued")
        self.assertIsNone(binding.attempted_at)
        self.mock.assert_not_called()

    def test_connector_only_allows_fixed_read_routes_and_bound_credentials(self):
        for method, route in [
            ("GET", "task/1/complete"),
            ("GET", "case/1/remove_org/3"),
            ("POST", "case/1/edit"),
            ("GET", "../admin"),
        ]:
            with self.assertRaises(ConnectorError):
                connector.api(self.instance, method, route)
        with (
            patch.dict(os.environ, {"FLOWINTEL_ALPHA_TOKEN": "synthetic-token"}),
            patch("portal.connectors.flowintel.approved_base", return_value=self.instance.base_url),
            patch("portal.connectors.flowintel.request_json", return_value=[]) as request,
        ):
            for route in ["case/list_status", "case/all", "case/completed"]:
                self.assertEqual(connector.api(self.instance, "GET", route), [])
            self.assertEqual(request.call_args.kwargs["headers"]["X-API-KEY"], "synthetic-token")
            self.assertTrue(request.call_args.kwargs["allow_list"])
        self.instance.enabled = False
        with self.assertRaises(ConnectorError):
            connector.api(self.instance, "GET", "case/1")

    def test_worker_command_drives_only_approved_jobs(self):
        draft = self.preview()
        call_command("process_flowintel", all=True, stdout=io.StringIO())
        self.mock.assert_not_called()
        flowintel.approve(self.analyst, draft.pk)
        for _ in range(6):
            call_command("process_flowintel", all=True, stdout=io.StringIO())
        self.assertEqual(len(self.fake.writes), 5)
        draft.refresh_from_db()
        self.assertIsNotNone(draft.last_success)

    def test_deadline_reason_and_source_text_validation(self):
        for deadline, reason in [(timezone.localdate() - timedelta(days=1), "Old"), (None, "")]:
            with self.assertRaises(ValidationError):
                flowintel.preview(self.analyst, self.finding, self.instance, deadline, reason)
        self.asset.name = "<script>bad()</script>```"
        self.asset.save()
        binding = self.preview()
        self.assertNotIn("<script>", binding.description)
        self.assertIn("&lt;script&gt;", binding.description)

    def test_http_export_requires_csrf_and_foreign_slug_is_hidden(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.analyst)
        response = client.post(reverse("flowintel-new", args=[self.a.slug, self.finding.pk]), {})
        self.assertEqual(response.status_code, 403)
        self.login(self.analyst)
        self.assertEqual(
            self.client.get(reverse("flowintel-new", args=[self.b.slug, self.finding.pk])).status_code, 404
        )
        binding = self.preview()
        self.login(self.platform)
        self.assertEqual(
            self.client.post(reverse("flowintel-approve", args=[self.a.slug, binding.pk])).status_code, 403
        )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL concurrent FlowIntel outbox claims")
class FlowIntelConcurrencyTests(TransactionTestCase):
    def test_two_workers_make_only_one_case_post(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        from .access import ANALYST_GROUP
        from .models import Organization, InventorySource, Asset, Product, Installation, SourceRecord, Finding

        actor = get_user_model().objects.create_user("flowintel-worker")
        actor.groups.add(Group.objects.create(name=ANALYST_GROUP))
        org = Organization.objects.create(
            name="Synthetic", slug="flowintel-concurrent", operator_visibility=True
        )
        source = InventorySource.objects.create(organization=org, mode="development")
        asset = Asset.objects.create(organization=org, source=source, name="Synthetic", kind="server")
        product = Product.objects.create(organization=org, name="Synthetic")
        install = Installation.objects.create(asset=asset, product=product)
        record = SourceRecord.objects.create(
            organization=org,
            source="fixture://test",
            external_id="CVE-2021-44228",
            payload={},
            shareable=True,
        )
        finding = Finding.objects.create(
            organization=org, installation=install, record=record, explanation="Unknown"
        )
        instance = FlowIntelInstance.objects.create(
            name="Concurrent",
            base_url="https://flowintel.example.invalid",
            token_env_var="FLOWINTEL_TEST_TOKEN",
            service_org_id=3,
        )
        binding = flowintel.preview(actor, finding, instance, None, "Test concurrent claim")
        flowintel.approve(actor, binding.pk)
        entered, release = Event(), Event()
        fake = FakeAPI(instance)

        def api(*args, **kwargs):
            if args[1] == "POST":
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Test release timeout")
            return fake(*args, **kwargs)

        def run():
            close_old_connections()
            try:
                flowintel.process(binding.pk)
            finally:
                connections.close_all()

        with patch("portal.flowintel.api", side_effect=api), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run)
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(run)
                second.result(timeout=5)
            finally:
                release.set()
            first.result(timeout=10)
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(FlowIntelCase.objects.get(pk=binding.pk).remote_id, 7)
