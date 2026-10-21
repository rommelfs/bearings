"""RTIR coordination authorization, immutable parent identity and uncertain write recovery."""

import copy
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from . import issues, rt, tests
from .connectors.http import ConnectorError
from .models import AssetIssue, RTInstance, RTTicket


class NativeRTIR:
    def __init__(self):
        self.records = {}
        self.writes = []
        self.lose_ack = False

    def __call__(self, instance, method, path, *, payload=None, params=None):
        if method == "POST":
            identity = len(self.records) + 1
            self.writes.append(copy.deepcopy(payload))
            self.records[identity] = {
                "id": identity,
                "Subject": payload["Subject"],
                "Queue": {
                    "id": payload["Queue"],
                    "Lifecycle": "incidents"
                    if payload["Queue"] == instance.incident_queue_id
                    else "investigations",
                },
                "Status": "open",
                "EffectiveId": {"id": identity, "type": "ticket"},
                "_hyperlinks": [
                    {
                        "id": parent,
                        "type": "ticket",
                        "ref": "parent",
                        "_url": "https://untrusted.invalid/never-follow",
                    }
                    for parent in payload.get("MemberOf", [])
                ],
            }
            if self.lose_ack:
                raise ConnectorError("Synthetic lost acknowledgment")
            return {"id": identity, "type": "ticket"}
        if path.startswith("queue/"):
            identity = int(path.split("/")[1])
            return {
                "id": identity,
                "Lifecycle": "incidents" if identity == instance.incident_queue_id else "investigations",
                "Disabled": False,
            }
        if path == "tickets":
            matches = [
                {"id": pk, "type": "ticket"}
                for pk, data in self.records.items()
                if data["Subject"] in params["query"]
            ]
            return {"items": matches, "total": len(matches)}
        return copy.deepcopy(self.records[int(path.split("/")[1])])


class RTIRTests(tests.Fixture):
    def setUp(self):
        self.b.operator_visibility = True
        self.b.save()
        self.instance = RTInstance.objects.create(
            name="CIRCL RTIR",
            product="rtir",
            base_url="https://rt.example.invalid",
            token_env_var="RT_RTIR_TOKEN",
            queue_id=12,
            incident_queue_id=11,
            enabled=True,
            private_queue_confirmed=True,
        )
        self.first = self.issue(self.asset)
        self.second = self.issue(self.other)
        self.fake = NativeRTIR()
        self.api = patch("portal.rt.api", side_effect=self.fake).start()
        self.addCleanup(patch.stopall)

    def issue(self, asset):
        return issues.save_issue(
            self.platform,
            AssetIssue(organization=asset.organization),
            {
                "asset": asset,
                "kind": "support",
                "title": "Synthetic support review",
                "source_label": "Synthetic",
                "evidence_text": "Synthetic only",
                "shareable": True,
            },
            "Seed synthetic evidence",
        )

    def link(self, issue=None, incident=None):
        row = rt.preview(
            self.analyst, issue or self.first, self.instance, "Explicit analyst escalation", incident=incident
        )
        rt.approve(self.analyst, row.pk)
        rt.process(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.state, "linked")
        return row

    def test_native_incident_with_multiple_investigations_and_no_assessment_change(self):
        incident = self.link()
        first = self.link(incident=incident)
        second = self.link(self.second, incident)
        self.assertEqual([row["Queue"] for row in self.fake.writes], [11, 12, 12])
        self.assertEqual(self.fake.writes[1]["MemberOf"], [incident.remote_id])
        self.assertEqual(incident.investigations.count(), 2)
        self.assertEqual(second.incident_id, incident.pk)
        self.fake.records[first.remote_id]["Status"] = "resolved"
        rt.refresh(first.pk, self.analyst)
        self.first.refresh_from_db()
        self.assertEqual(self.first.status, "new")
        self.assertTrue(self.first.active)
        self.assertIn("/RTIR/Display.html?id=", first.ticket_url)

    def test_company_users_cannot_create_read_or_select_incident(self):
        incident = self.link()
        with self.assertRaises(PermissionDenied):
            rt.preview(self.admin, self.first, self.instance, "Unauthorized")
        self.login()
        self.assertEqual(self.client.get(reverse("rtir")).status_code, 403)
        self.assertEqual(self.client.get(self.url("rt-ticket", pk=incident.pk)).status_code, 404)
        self.assertNotContains(self.client.get(self.url("rt-new", pk=self.first.pk)), incident.subject)

    def test_withdrawn_company_hides_whole_aggregate_and_blocks_worker(self):
        incident = self.link()
        child = rt.preview(self.analyst, self.second, self.instance, "Second company", incident)
        rt.approve(self.analyst, child.pk)
        self.b.operator_visibility = False
        self.b.save()
        self.assertFalse(rt.can_read_ticket(self.analyst, rt.load(incident.pk)))
        self.assertEqual(rt.visible_incidents(self.analyst), [])
        rt.process(child.pk)
        child.refresh_from_db()
        self.assertEqual(child.state, "blocked")
        self.assertEqual(len(self.fake.writes), 1)
        self.login(self.analyst)
        self.assertEqual(self.client.get(self.url("rt-ticket", pk=incident.pk)).status_code, 404)
        self.assertNotContains(self.client.get(self.url("issue", pk=self.first.pk)), self.instance.name)

    def test_changed_parent_link_retains_last_known_status(self):
        incident = self.link()
        child = self.link(incident=incident)
        before = child.summary
        self.fake.records[child.remote_id]["_hyperlinks"] = [{"id": 999, "type": "ticket", "ref": "parent"}]
        with self.assertRaises(ConnectorError):
            rt.refresh(child.pk, self.analyst)
        child.refresh_from_db()
        self.assertEqual(child.summary, before)
        self.assertTrue(child.error)

    def test_lost_ack_reconciles_native_parent_using_reads_only(self):
        incident = self.link()
        child = rt.preview(self.analyst, self.second, self.instance, "Investigate", incident)
        rt.approve(self.analyst, child.pk)
        self.fake.lose_ack = True
        rt.process(child.pk)
        child.refresh_from_db()
        self.assertEqual(child.state, "uncertain")
        self.assertIsNone(child.remote_id)
        self.api.reset_mock()
        rt.reconcile(child.pk, self.analyst)
        self.assertTrue(all(call.args[1] == "GET" for call in self.api.call_args_list))
        child.refresh_from_db()
        self.assertEqual(child.state, "linked")
        self.assertEqual(len(self.fake.writes), 2)

    def test_parent_cannot_be_unlinked_repointed_or_cross_connection(self):
        incident = self.link()
        child = self.link(incident=incident)
        another = self.link(self.second)
        with self.assertRaises(ValidationError):
            rt.preview(self.analyst, self.first, self.instance, "Move Investigation", another)
        instance = copy.copy(self.instance)
        instance.pk = None
        instance.name = "Other RTIR"
        instance.save()
        with self.assertRaises(PermissionDenied):
            rt.preview(self.analyst, self.first, instance, "Wrong source", incident)
        child.refresh_from_db()
        self.assertEqual(child.incident_id, incident.pk)
        self.instance.incident_queue_id = 98
        with self.assertRaises(ValidationError):
            self.instance.full_clean()

    def test_invalid_rtir_connection_requires_private_distinct_native_queues(self):
        self.instance.organization = self.a
        with self.assertRaises(ValidationError):
            self.instance.full_clean()
        self.instance.organization = None
        self.instance.incident_queue_id = self.instance.queue_id
        with self.assertRaises(ValidationError):
            self.instance.full_clean()

    def test_analyst_ui_shows_scoped_investigations_and_safe_links(self):
        incident = self.link()
        self.link(self.second, incident)
        self.login(self.analyst)
        page = self.client.get(self.url("rt-ticket", pk=incident.pk))
        self.assertContains(page, "Investigations by company and asset")
        self.assertContains(page, self.other.name)
        self.assertContains(self.client.get(reverse("rtir")), incident.subject)
        self.assertEqual(RTTicket.objects.filter(role="incident").count(), 1)

    def test_wrong_destination_lifecycle_blocks_creation_before_any_post(self):
        row = rt.preview(self.analyst, self.first, self.instance, "Explicit escalation")
        rt.approve(self.analyst, row.pk)
        original = self.fake

        def changed(instance, method, path, **kwargs):
            data = original(instance, method, path, **kwargs)
            if path.startswith("queue/"):
                data["Lifecycle"] = "default"
            return data

        with patch("portal.rt.api", side_effect=changed):
            rt.process(row.pk)
        self.assertEqual(self.fake.writes, [])
        row.refresh_from_db()
        self.assertEqual(row.state, "blocked")
        self.assertIsNone(row.attempted_at)
        retried = rt.preview(self.analyst, self.first, self.instance, "Reviewed corrected native queue")
        rt.approve(self.analyst, retried.pk)
        rt.process(retried.pk)
        retried.refresh_from_db()
        self.assertEqual(retried.state, "linked")
        self.assertEqual(len(self.fake.writes), 1)
