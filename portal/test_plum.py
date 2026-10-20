import copy
from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from . import tests, plum, issues
from .connectors import plum as connector
from .connectors.http import ConnectorError, UpstreamHTTPError
from .models import AssetIssue, InfrastructureClaim, PlumInstance, PlumSnapshot


@override_settings(DEBUG=True)
class PlumTests(tests.Fixture):
    def setUp(self):
        self.source = PlumInstance.objects.create(
            name="SYNTHETIC Plum", base_url="https://plum.example.invalid", fixture=True, enabled=True
        )
        self.source.organizations.add(self.a)
        self.begin = timezone.now() - timedelta(days=20)
        self.end = timezone.now() - timedelta(days=10)
        self.claim = InfrastructureClaim.objects.create(
            organization=self.a,
            kind="network",
            value="192.0.2.0/24",
            status="verified",
            valid_from=self.begin - timedelta(days=1),
        )
        self.asset.upstream_data = {
            "primary_ip4": "192.0.2.25/24",
            "primary_ip4_dns_name": "synthetic.example.invalid",
        }
        self.asset.save()
        self.payload = {
            "result": {
                "ip": "192.0.2.25",
                "start": self.begin.isoformat(),
                "stop": self.end.isoformat(),
                "report_count": 2,
                "ports": [
                    {
                        "port": 443,
                        "protocol": "tcp",
                        "tags": ["co-observed:synthetic"],
                        "first_seen": self.begin.isoformat(),
                        "last_seen": (self.end - timedelta(hours=1)).isoformat(),
                    },
                    {
                        "port": 53,
                        "protocol": "udp",
                        "tags": [],
                        "first_seen": self.begin.isoformat(),
                        "last_seen": self.end.isoformat(),
                    },
                ],
            }
        }

    def ingest(self, payload=None, actor=None):
        return plum.ingest(actor or self.admin, self.a, self.source, payload or self.payload)

    def test_scoped_import_protocols_provenance_dedup_and_no_network_writes(self):
        with patch("portal.plum.infoip") as network:
            row = self.ingest()
            repeated = self.ingest()
            network.assert_not_called()
        self.assertEqual(row.pk, repeated.pk)
        self.assertEqual(row.asset_id, self.asset.pk)
        self.assertEqual(row.ports[1]["protocol"], "udp")
        self.assertEqual(row.report_count, 2)
        self.assertEqual(PlumSnapshot.objects.count(), 1)
        self.assertTrue(row.source_digest)
        self.assertEqual(AssetIssue.objects.count(), 0)

    def test_current_customer_source_grants_scope_and_raw_derived_visibility(self):
        row = self.ingest()
        issue = plum.create_review(self.admin, row, 443, "tcp", "", "Verify intended exposure")
        self.assertTrue(issues.visible_issues(self.admin).filter(pk=issue.pk).exists())
        self.source.organizations.clear()
        self.assertFalse(plum.visible_snapshots(self.admin).exists())
        self.assertFalse(issues.visible_issues(self.admin).filter(pk=issue.pk).exists())
        self.assertTrue(plum.visible_snapshots(self.analyst).exists())
        self.a.operator_visibility = False
        self.a.save()
        self.assertFalse(plum.visible_snapshots(self.analyst).exists())

    def test_scope_revocation_and_changed_assignments_hide_counts_and_evidence(self):
        row = self.ingest()
        self.login()
        self.assertContains(self.client.get(reverse("plum")), "192.0.2.25")
        self.claim.value = "198.51.100.0/24"
        self.claim.save()
        self.assertEqual(self.client.get(reverse("plum")).context["page"].paginator.count, 0)
        self.assertEqual(self.client.get(self.url("plum-evidence", pk=row.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("plum-snapshot", org=self.b, pk=row.pk)).status_code, 404)

    def test_unverified_out_of_time_foreign_ip_and_reader_import_denied(self):
        with self.assertRaises(PermissionDenied):
            self.ingest(actor=self.reader)
        for field, value in [
            ("status", "declared"),
            ("valid_from", self.end),
            ("valid_until", self.end - timedelta(hours=1)),
            ("value", "198.51.100.0/24"),
        ]:
            original = getattr(self.claim, field)
            setattr(self.claim, field, value)
            self.claim.save()
            with self.assertRaises(ValidationError):
                self.ingest()
            setattr(self.claim, field, original)
            self.claim.save()
        self.assertEqual(PlumSnapshot.objects.count(), 0)

    def test_unknown_vs_empty_and_no_inferred_closure(self):
        previous = self.ingest()
        payload = copy.deepcopy(self.payload)
        payload["result"].update(
            start=self.end.isoformat(),
            stop=(self.end + timedelta(days=5)).isoformat(),
            ports=[],
            report_count=0,
        )
        current = self.ingest(payload)
        changes = plum.compare(current, previous)
        self.assertTrue(all(row["change"] == "not_observed" for row in changes))
        self.assertNotIn("closed_reported", str(changes))
        unknown = plum.ingest(
            self.admin,
            self.a,
            self.source,
            None,
            ip="192.0.2.25",
            start=self.end.isoformat(),
            stop=(self.end + timedelta(days=6)).isoformat(),
        )
        self.assertEqual(unknown.state, "not_indexed")
        self.assertEqual(current.state, "indexed")

    def test_first_seen_before_window_withheld_and_unknown_protocol_preserved(self):
        payload = copy.deepcopy(self.payload)
        payload["result"]["ports"][0].update(
            first_seen=(self.begin - timedelta(days=10)).isoformat(), protocol=None
        )
        row = self.ingest(payload)
        self.assertIsNone(row.ports[0]["first_seen"])
        self.assertTrue(row.ports[0]["first_before_window"])
        self.assertIsNone(row.ports[0]["protocol"])
        self.assertEqual(plum.compare(row)[1]["change"], "unknown_protocol")

    def test_new_port_context_and_exposure_review_preserve_prior_decisions(self):
        baseline = self.ingest()
        payload = copy.deepcopy(self.payload)
        payload["result"].update(start=self.end.isoformat(), stop=(self.end + timedelta(days=5)).isoformat())
        for port in payload["result"]["ports"]:
            port["last_seen"] = (self.end + timedelta(days=4)).isoformat()
        payload["result"]["ports"].append(
            {
                "port": 3389,
                "protocol": "tcp",
                "first_seen": self.end.isoformat(),
                "last_seen": (self.end + timedelta(days=4)).isoformat(),
                "tags": ["possible:context"],
            }
        )
        row = self.ingest(payload)
        self.assertEqual(
            [r["port"] for r in plum.compare(row, baseline) if r["change"] == "newly_observed"], [3389]
        )
        issue = plum.create_review(self.admin, row, 3389, "tcp", "", "Unexpected management exposure")
        self.assertEqual(issue.priority, "review")
        self.assertFalse(issue.shareable)
        self.assertEqual(issue.kind, "exposure")
        issue = issues.save_issue(
            self.admin, issue, {"status": "accepted_risk"}, "Approved intentional exposure"
        )
        self.assertEqual(plum.create_review(self.admin, row, 3389, "tcp", "", "Repeat").pk, issue.pk)
        issue.refresh_from_db()
        self.assertEqual(issue.status, "accepted_risk")

    def test_invalid_response_values_roll_back_without_replacing_snapshot(self):
        old = self.ingest()
        for field, bad in [
            ("protocol", []),
            ("port", True),
            ("hostname", []),
            ("last_seen", "not-a-time"),
            ("tags", "unexpected"),
        ]:
            payload = copy.deepcopy(self.payload)
            payload["result"]["ports"][0][field] = bad
            with self.assertRaises(ValidationError):
                self.ingest(payload)
        self.assertEqual(PlumSnapshot.objects.get().pk, old.pk)

    def test_export_preserves_report_hostname_and_explicit_scan_state(self):
        payload = {
            "time_range": {"from_ts": self.begin.timestamp(), "to_ts": self.end.timestamp()},
            "results": {
                "192.0.2.25": [
                    {
                        "uid": "SYNTHETIC-report-1",
                        "first_seen": self.begin.timestamp(),
                        "last_seen": self.end.timestamp(),
                        "document": {
                            "body": {
                                "addr": "192.0.2.25",
                                "hostnames": [{"type": "user", "name": "service.example.invalid"}],
                                "ports": [{"portid": "443", "protocol": "tcp", "state": "closed"}],
                            }
                        },
                    }
                ]
            },
        }
        row = plum.import_export(self.admin, self.a, self.source, payload)[0]
        self.assertEqual(row.ports[0]["hostname"], "service.example.invalid")
        self.assertEqual(plum.compare(row)[0]["change"], "closed_reported")
        self.assertEqual(row.ports[0]["reports"], ["SYNTHETIC-report-1"])

    def test_partial_or_cross_scope_export_is_atomic(self):
        payload = {
            "time_range": {"from_ts": self.begin.timestamp(), "to_ts": self.end.timestamp()},
            "results": {},
        }
        for ip in ["192.0.2.25", "198.51.100.99"]:
            payload["results"][ip] = [
                {
                    "uid": "synthetic-" + ip,
                    "first_seen": self.begin.timestamp(),
                    "last_seen": self.end.timestamp(),
                    "document": {"body": {"addr": ip, "ports": []}},
                }
            ]
        with self.assertRaises(ValidationError):
            plum.import_export(self.admin, self.a, self.source, payload)
        self.assertEqual(PlumSnapshot.objects.count(), 0)
        payload["results"]["192.0.2.25"][0]["warning"] = "document missing"
        with self.assertRaises(ValidationError):
            plum.import_export(self.admin, self.a, self.source, payload)

    def test_unmapped_observation_retained_without_inventing_asset(self):
        payload = copy.deepcopy(self.payload)
        payload["result"]["ip"] = "192.0.2.77"
        row = self.ingest(payload)
        self.assertIsNone(row.asset_id)
        with self.assertRaises(ValidationError):
            plum.create_review(self.admin, row, 443, "tcp", "", "Must map first")
        self.assertEqual(AssetIssue.objects.count(), 0)

    def test_live_connector_is_get_only_and_distinguishes_404_from_auth_failure(self):
        self.source.fixture = False
        self.source.token_env_var = "PLUM_TEST_TOKEN"
        self.source.save()
        with (
            patch.dict("os.environ", {"PLUM_TEST_TOKEN": "synthetic-jwt"}),
            patch("portal.connectors.plum.approved_base", return_value=self.source.base_url),
            patch("portal.connectors.plum.request_json") as network,
        ):
            network.side_effect = UpstreamHTTPError(404)
            self.assertIsNone(connector.infoip(self.source, "8.8.8.8", self.begin, self.end))
            self.assertEqual(network.call_args.args[0], "GET")
            self.assertIn("/api/v1/infoip/8.8.8.8", network.call_args.args[1])
            self.assertEqual(network.call_args.kwargs["headers"]["Authorization"], "Bearer synthetic-jwt")
            network.side_effect = UpstreamHTTPError(403)
            with self.assertRaises(ConnectorError):
                connector.infoip(self.source, "8.8.8.8", self.begin, self.end)
        self.source.fixture = True
        self.source.save()
        with self.assertRaises(ConnectorError):
            connector.infoip(self.source, "8.8.8.8", self.begin, self.end)

    def test_withdrawn_company_source_grant_blocks_operator_outreach_and_tickets(self):
        from . import rt
        from .notifications import preview_batch, approve_local, candidates, authorized_delivery
        from .models import Contact, RTInstance, NotificationReceipt

        row = self.ingest()
        issue = plum.create_review(self.analyst, row, 443, "tcp", "", "Review authorized exposure")
        issue = issues.save_issue(
            self.analyst, issue, {"shareable": True}, "Explicit synthetic review export"
        )
        Contact.objects.create(
            organization=self.a,
            name="Owner",
            role="Owner",
            email="owner@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=60),
        )
        filters = {"organization": self.a.pk, "domain": "asset_issues", "sort": "severity"}
        batch = preview_batch(self.analyst, "circl", filters, "Review", "{{ items }}")
        delivery = batch.deliveries.get()
        instance = RTInstance.objects.create(
            name="Review queue",
            organization=self.a,
            base_url="https://rt.example.invalid",
            token_env_var="RT_TEST_TOKEN",
            queue_id=3,
            enabled=True,
            private_queue_confirmed=True,
        )
        ticket = rt.preview(self.analyst, issue, instance, "Coordinate exposure review")
        self.source.organizations.clear()
        self.assertTrue(issues.visible_issues(self.analyst).filter(pk=issue.pk).exists())
        self.assertFalse(issues.exportable_issues(self.analyst).filter(pk=issue.pk).exists())
        self.assertEqual(candidates(self.analyst, "circl", filters).count(), 0)
        self.assertFalse(authorized_delivery(self.analyst, delivery))
        with patch("portal.notifications.EmailBackend") as mail, patch("portal.rt.api") as api:
            with self.assertRaises(PermissionDenied):
                approve_local(self.analyst, batch.pk, [delivery.pk])
            with self.assertRaises(PermissionDenied):
                rt.approve(self.analyst, ticket.pk)
            mail.assert_not_called()
            api.assert_not_called()
        self.assertEqual(NotificationReceipt.objects.count(), 0)
