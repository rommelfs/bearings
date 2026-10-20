from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from django.db import connection, close_old_connections, connections
from django.test import TransactionTestCase
import copy
import os
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from . import tests, issues, rt
from .connectors.http import ConnectorError
from .connectors import rt as connector
from .models import AssetIssue, RTInstance


class FakeRT:
    def __init__(self):
        self.ticket = None
        self.writes = []
        self.lose_ack = False

    def __call__(self, instance, method, path, *, payload=None, params=None):
        if method == "POST":
            self.writes.append(copy.deepcopy(payload))
            self.ticket = {
                "id": "7",
                "Subject": payload["Subject"],
                "Queue": {"id": str(instance.queue_id)},
                "Status": "new",
                "Owner": {"id": "0", "Name": "Nobody"},
                "Due": payload.get("Due", ""),
                "EffectiveId": "7",
            }
            if self.lose_ack:
                raise ConnectorError("Synthetic lost acknowledgment")
            return {"id": "7", "type": "ticket", "_url": "https://untrusted.invalid/not-followed"}
        if path == "tickets":
            return {
                "items": [{"id": "7", "type": "ticket"}] if self.ticket else [],
                "total": None,
                "count": 1 if self.ticket else 0,
            }
        if path == "ticket/7":
            return copy.deepcopy(self.ticket)
        raise AssertionError(path)


class RTTests(tests.Fixture):
    def setUp(self):
        self.issue = issues.save_issue(
            self.admin,
            AssetIssue(organization=self.a),
            {
                "asset": self.asset,
                "kind": "support",
                "title": "SYNTHETIC support expiry",
                "source_label": "Synthetic contract",
                "evidence_text": "A synthetic expiry assertion",
                "shareable": True,
            },
            "Initial synthetic evidence",
        )
        self.instance = RTInstance.objects.create(
            name="Alpha response",
            organization=self.a,
            base_url="https://rt.example.invalid",
            token_env_var="RT_ALPHA_TOKEN",
            queue_id=3,
            enabled=True,
            private_queue_confirmed=True,
        )
        self.fake = FakeRT()
        self.api = patch("portal.rt.api", side_effect=self.fake).start()
        self.addCleanup(patch.stopall)

    def preview(self):
        return rt.preview(self.admin, self.issue, self.instance, "Coordinate remediation")

    def linked(self):
        row = self.preview()
        rt.approve(self.admin, row.pk)
        rt.process(row.pk)
        return rt.load(row.pk)

    def test_exact_preview_approval_and_source_bound_creation(self):
        row = self.preview()
        self.api.assert_not_called()
        self.assertIn(str(row.pk), row.subject)
        self.assertIn(self.asset.name, row.content)
        rt.approve(self.admin, row.pk)
        rt.process(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.state, "linked")
        self.assertEqual(row.remote_id, 7)
        self.assertEqual(len(self.fake.writes), 1)
        self.assertEqual(self.fake.writes[0]["Queue"], 3)
        self.assertNotIn("Requestor", self.fake.writes[0])
        self.assertEqual(row.ticket_url, "https://rt.example.invalid/Ticket/Display.html?id=7")
        self.assertEqual(row.summary["owner"], "Nobody")

    def test_no_auto_export_reader_restricted_foreign_or_unattested_queue(self):
        for actor in [self.reader]:
            with self.assertRaises(PermissionDenied):
                rt.preview(actor, self.issue, self.instance, "Not authorized")
        self.instance.organization = self.b
        self.instance.save()
        with self.assertRaises(PermissionDenied):
            self.preview()
        self.instance.organization = self.a
        self.instance.private_queue_confirmed = False
        self.instance.save()
        with self.assertRaises(PermissionDenied):
            self.preview()
        self.instance.private_queue_confirmed = True
        self.instance.save()
        self.issue.shareable = False
        self.issue.save()
        with self.assertRaises(PermissionDenied):
            self.preview()
        self.api.assert_not_called()

    def test_circl_queue_is_hidden_from_company_users(self):
        self.instance.organization = None
        self.instance.save()
        with self.assertRaises(PermissionDenied):
            self.preview()
        row = rt.preview(self.analyst, self.issue, self.instance, "CIRCL coordination")
        self.login()
        self.assertEqual(self.client.get(self.url("rt-ticket", pk=row.pk)).status_code, 404)
        self.a.operator_visibility = False
        self.a.save()
        self.assertFalse(rt.can_read(self.analyst, self.issue, self.instance))

    def test_repeated_preview_worker_and_approval_do_not_duplicate(self):
        row = self.linked()
        self.assertEqual(self.preview().pk, row.pk)
        rt.process(row.pk)
        with self.assertRaises(ValidationError):
            rt.approve(self.admin, row.pk)
        self.assertEqual(len(self.fake.writes), 1)

    def test_changed_evidence_revoked_access_and_disabled_connection_block_before_io(self):
        row = self.preview()
        rt.approve(self.admin, row.pk)
        issues.save_issue(self.admin, self.issue, {"evidence_text": "Changed facts"}, "New evidence")
        rt.process(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.state, "blocked")
        self.assertIsNone(row.attempted_at)
        self.api.assert_not_called()
        row = self.preview()
        rt.approve(self.admin, row.pk)
        self.instance.enabled = False
        self.instance.save()
        rt.process(row.pk)
        self.api.assert_not_called()

    def test_lost_ack_recovered_by_reads_without_retrying_ticket_post(self):
        row = self.preview()
        rt.approve(self.admin, row.pk)
        self.fake.lose_ack = True
        rt.process(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.state, "uncertain")
        self.assertIsNone(row.remote_id)
        rt.process(row.pk)
        rt.reconcile(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.state, "linked")
        self.assertEqual(row.remote_id, 7)
        self.assertEqual(len(self.fake.writes), 1)

    def test_missing_ack_and_no_matching_ticket_never_resubmits(self):
        row = self.preview()
        rt.approve(self.admin, row.pk)
        with patch("portal.rt.api", side_effect=ConnectorError("Offline")):
            rt.process(row.pk)
        with self.assertRaises(ConnectorError):
            rt.reconcile(row.pk)
        rt.process(row.pk)
        self.assertEqual(self.fake.writes, [])

    def test_private_queue_identity_subject_and_merge_changes_preserve_status(self):
        row = self.linked()
        initial = row.summary
        for field, bad in [
            ("Queue", {"id": "99"}),
            ("Subject", "Changed correlation"),
            ("EffectiveId", "99"),
        ]:
            original = self.fake.ticket[field]
            self.fake.ticket[field] = bad
            with self.assertRaises(ConnectorError):
                rt.refresh(row.pk)
            row.refresh_from_db()
            self.assertEqual(row.summary, initial)
            self.fake.ticket[field] = original
        self.fake.ticket["Status"] = "resolved"
        rt.refresh(row.pk)
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, "new")

    def test_instance_identity_cannot_be_repointed_after_preview(self):
        self.preview()
        for field, value in [
            ("queue_id", 99),
            ("base_url", "https://other.example.invalid"),
            ("token_env_var", "RT_OTHER_TOKEN"),
        ]:
            original = getattr(self.instance, field)
            setattr(self.instance, field, value)
            with self.assertRaises(ValidationError):
                self.instance.full_clean()
            setattr(self.instance, field, original)

    def test_connector_fixed_routes_bound_token_and_ignores_response_links(self):
        for method, path in [
            ("GET", "../admin"),
            ("PUT", "ticket/7"),
            ("POST", "ticket/7/correspond"),
            ("GET", "https://untrusted.invalid"),
        ]:
            with self.assertRaises(ConnectorError):
                connector.api(self.instance, method, path)
        with (
            patch.dict(os.environ, {"RT_ALPHA_TOKEN": "synthetic-test-token"}),
            patch("portal.connectors.rt.approved_base", return_value=self.instance.base_url),
            patch("portal.connectors.rt.request_json", return_value={}) as request,
        ):
            connector.api(self.instance, "GET", "ticket/7")
            self.assertEqual(
                request.call_args.kwargs["headers"]["Authorization"], "token synthetic-test-token"
            )
            self.assertEqual(request.call_args.args[1], "https://rt.example.invalid/REST/2.0/ticket/7")

    def test_creator_approval_post_only_and_html_escaping(self):
        row = self.preview()
        self.login(self.editor)
        self.assertEqual(
            self.client.post(self.url("rt-action", pk=row.pk), {"action": "approve"}).status_code, 403
        )
        self.login()
        self.assertEqual(self.client.get(self.url("rt-action", pk=row.pk)).status_code, 405)
        row.content = "<script>synthetic</script>"
        row.save()
        self.assertContains(
            self.client.get(self.url("rt-ticket", pk=row.pk)), "&lt;script&gt;synthetic&lt;/script&gt;"
        )
        self.assertEqual(self.client.get(self.url("rt-ticket", org=self.b, pk=row.pk)).status_code, 404)

    def test_worker_processes_only_approved_jobs(self):
        row = self.preview()
        call_command("process_rt_tickets", all=True)
        self.api.assert_not_called()
        rt.approve(self.admin, row.pk)
        call_command("process_rt_tickets", all=True)
        self.assertEqual(len(self.fake.writes), 1)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL concurrent RT outbox claims")
class RTConcurrencyTests(TransactionTestCase):
    def test_two_workers_make_only_one_ticket_post(self):
        from django.contrib.auth import get_user_model
        from .models import Organization, InventorySource, Asset, Membership, RTTicket

        actor = get_user_model().objects.create_user("rt-worker")
        org = Organization.objects.create(name="Synthetic", slug="rt-concurrent")
        Membership.objects.create(user=actor, organization=org, role="admin")
        source = InventorySource.objects.create(organization=org, mode="development")
        asset = Asset.objects.create(organization=org, source=source, name="Synthetic", kind="server")
        issue = issues.save_issue(
            actor,
            AssetIssue(organization=org),
            {
                "asset": asset,
                "kind": "support",
                "title": "Synthetic expiry",
                "source_label": "Synthetic",
                "evidence_text": "Synthetic",
                "shareable": True,
            },
            "Synthetic concurrency exercise",
        )
        instance = RTInstance.objects.create(
            name="Concurrent",
            organization=org,
            base_url="https://rt.example.invalid",
            token_env_var="RT_TEST_TOKEN",
            queue_id=3,
            enabled=True,
            private_queue_confirmed=True,
        )
        row = rt.preview(actor, issue, instance, "Test concurrent claim")
        rt.approve(actor, row.pk)
        entered, release = Event(), Event()
        fake = FakeRT()

        def api(*args, **kwargs):
            if args[1] == "POST":
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Test release timeout")
            return fake(*args, **kwargs)

        def run():
            close_old_connections()
            try:
                rt.process(row.pk)
            finally:
                connections.close_all()

        with patch("portal.rt.api", side_effect=api), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run)
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(run)
                second.result(timeout=5)
            finally:
                release.set()
            first.result(timeout=10)
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(RTTicket.objects.get(pk=row.pk).remote_id, 7)
