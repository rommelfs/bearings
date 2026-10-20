from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from . import issues, tests
from .models import AssetIssue, IssueHistory, IssueRevision, Asset, Installation, Product
from .services import persist_lookup, transition_finding


class AssetIssueTests(tests.Fixture):
    def create(self, actor=None, **overrides):
        fields = {
            "asset": self.asset,
            "kind": "support",
            "title": "Support contract expires",
            "source_label": "Synthetic contract",
            "evidence_text": "Support expires on the documented date.",
            "event_date": timezone.localdate() + timedelta(days=10),
            "consequence": "Security fixes may no longer be covered.",
            "fact_scope": "entitlement",
            "contract_reference": "SYNTHETIC-SUPPORT-1",
        }
        fields.update(overrides)
        return issues.save_issue(
            actor or self.admin, AssetIssue(organization=self.a), fields, "Synthetic evidence review"
        )

    def test_lifecycle_fact_source_scope_dates_and_immutable_history(self):
        issue = self.create()
        self.assertEqual(issue.timing, "soon")
        self.assertEqual(issue.fact_scope, "entitlement")
        first = issue.revisions.get()
        issue = issues.save_issue(
            self.admin,
            issue,
            {"status": "under_review", "owner_team": "Infrastructure", "priority": "high"},
            "Assigned for review",
        )
        first.refresh_from_db()
        self.assertEqual(first.snapshot["status"], "new")
        self.assertEqual(issue.history.count(), 2)
        self.assertEqual(issue.revisions.count(), 2)
        self.assertEqual(issue.status, "under_review")
        self.assertEqual(issue.asset.lifecycle, "active")

    def test_company_reader_cannot_mutate_but_can_read_scoped_issues(self):
        issue = self.create()
        self.login(self.reader)
        self.assertContains(self.client.get(reverse("issues")), issue.title)
        self.assertNotContains(self.client.get(reverse("issues")), "+ Record issue")
        response = self.client.get(self.url("issue-edit", pk=issue.pk))
        self.assertEqual(response.status_code, 403)
        with self.assertRaises(PermissionDenied):
            issues.save_issue(self.reader, issue, {"status": "resolved"}, "Not permitted")

    def test_cross_organization_targets_and_repointing_denied(self):
        foreign = Asset.objects.create(organization=self.b, source=self.sb, name="Foreign", kind="server")
        with self.assertRaises(ValidationError):
            self.create(asset=foreign)
        issue = self.create()
        with self.assertRaises(ValidationError):
            issues.save_issue(self.admin, issue, {"kind": "warranty"}, "Retarget issue")
        self.assertEqual(AssetIssue.objects.get(pk=issue.pk).kind, "support")
        with self.assertRaises(ValidationError):
            self.create(
                installation=Installation.objects.create(
                    asset=foreign, product=Product.objects.create(organization=self.b, name="Foreign")
                )
            )

    def test_hidden_operator_evidence_does_not_leak_counts_history_or_api(self):
        public = self.create(title="Public")
        hidden = self.create(self.analyst, title="<script>restricted</script>", operator_only=True)
        self.login()
        board = self.client.get(reverse("issues"))
        self.assertContains(board, "Public")
        self.assertNotContains(board, "restricted")
        self.assertEqual(board.context["counts"]["total"], 1)
        for name in ["issue", "issue-edit", "issue-evidence"]:
            self.assertEqual(self.client.get(self.url(name, pk=hidden.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url("api-issues")).json()["count"], 1)
        self.login(self.analyst)
        self.assertContains(
            self.client.get(self.url("issue", pk=hidden.pk)), "&lt;script&gt;restricted&lt;/script&gt;"
        )
        self.a.operator_visibility = False
        self.a.save()
        self.assertEqual(self.client.get(self.url("issue", pk=hidden.pk)).status_code, 404)
        self.assertEqual(issues.visible_issues(self.admin).get().pk, public.pk)

    def test_operator_visibility_and_company_cannot_release_operator_only(self):
        issue = self.create(self.analyst, operator_only=True)
        with self.assertRaises(PermissionDenied):
            issues.save_issue(self.admin, issue, {"operator_only": False}, "Cannot release")
        self.a.operator_visibility = False
        self.a.save()
        with self.assertRaises(PermissionDenied):
            self.create(self.analyst)

    def test_cve_link_keeps_original_history_restrictions_and_workflow_authority(self):
        finding = persist_lookup(self.admin, self.installation, "fixture://issue-test", "CVE-2021-44228", {})
        issue = AssetIssue.objects.get(finding=finding)
        self.assertEqual(issue.kind, "vulnerability")
        self.assertEqual(issues.ensure_vulnerability_issue(finding).pk, issue.pk)
        transition_finding(self.admin, finding, "resolved", "Synthetic remediation verified", "not_affected")
        issue.refresh_from_db()
        self.assertEqual(issue.current_status, "resolved")
        self.assertEqual(issue.timing, "closed")
        with self.assertRaises(ValidationError):
            issues.save_issue(self.admin, issue, {"status": "confirmed"}, "Must use original review")
        self.login()
        response = self.client.get(self.url("issue", pk=issue.pk))
        self.assertContains(response, "domain=vulnerabilities&amp;severity=&amp;cve=CVE-2021-44228")
        from .notifications import NotificationForm

        self.assertTrue(
            NotificationForm(
                self.admin,
                {
                    "mode": "company",
                    "organization": self.a.pk,
                    "domain": "vulnerabilities",
                    "sort": "severity",
                    "cve": "CVE-2021-44228",
                    "subject_template": "Review",
                    "body_template": "{{ findings }}",
                },
            ).is_valid()
        )
        finding.record.shareable = False
        finding.record.save()
        self.assertFalse(issues.visible_issues(self.admin).filter(pk=issue.pk).exists())
        self.assertTrue(issues.visible_issues(self.analyst).filter(pk=issue.pk).exists())

    def test_dates_unknown_future_observation_and_closed_deadlines(self):
        issue = self.create(event_date=None)
        self.assertEqual(issue.timing, "unknown")
        issue = issues.save_issue(
            self.admin,
            issue,
            {"event_date": timezone.localdate() - timedelta(days=3)},
            "Synthetic expiry verified",
        )
        self.assertEqual(issue.timing, "overdue")
        issue = issues.save_issue(
            self.admin,
            issue,
            {"action_due": timezone.localdate() + timedelta(days=8)},
            "Action plan approved",
        )
        self.assertEqual(issue.timing, "soon")
        issue = issues.save_issue(self.admin, issue, {"status": "accepted_risk"}, "Accepted with evidence")
        self.assertEqual(issue.timing, "closed")
        with self.assertRaises(ValidationError):
            self.create(observed_at=timezone.now() + timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.create(valid_from=timezone.localdate(), valid_until=timezone.localdate() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.create(source_url="javascript:alert(1)")

    def test_create_edit_evidence_and_csrf_in_real_views(self):
        self.login()
        fields = {
            "asset": str(self.asset.pk),
            "kind": "eol",
            "title": "Synthetic firmware EOL",
            "status": "new",
            "priority": "high",
            "fact_scope": "asset",
            "source_label": "Vendor bulletin",
            "observed_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "fact_status": "unverified",
            "evidence_text": "<img src=x onerror=alert(1)>",
            "reason": "Initial manual evidence",
        }
        result = self.client.post(self.url("issue-new"), fields)
        self.assertEqual(result.status_code, 302, getattr(result, "context", None))
        issue = AssetIssue.objects.get()
        self.assertContains(self.client.get(result.url), "&lt;img src=x onerror=alert(1)&gt;")
        evidence = self.client.get(self.url("issue-evidence", pk=issue.pk)).json()
        self.assertEqual(evidence["snapshot"]["evidence_text"], fields["evidence_text"])
        self.assertEqual(evidence["digest"], issue.revisions.get().digest)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        self.assertEqual(strict.post(self.url("issue-edit", pk=issue.pk), fields).status_code, 403)
        self.assertEqual(self.client.get(self.url("issue", org=self.b, pk=issue.pk)).status_code, 404)

    def test_filters_global_counts_pagination_priority_and_asset_search(self):
        AssetIssue.objects.bulk_create(
            [
                AssetIssue(
                    organization=self.a,
                    asset=self.asset,
                    title=f"Issue {n}",
                    kind="license",
                    source_label="Synthetic",
                    evidence_text="Synthetic",
                    priority="low",
                )
                for n in range(26)
            ]
        )
        high = self.create(priority="critical", title="Must appear first")
        self.login()
        response = self.client.get(reverse("issues"))
        self.assertEqual(response.context["page"][0].pk, high.pk)
        self.assertEqual(response.context["counts"]["total"], 27)
        self.assertEqual(response.context["counts"]["unknown"], 26)
        self.assertEqual(
            self.client.get(reverse("issues"), {"kind": "license"}).context["page"].paginator.count, 26
        )
        self.assertEqual(
            self.client.get(reverse("issues"), {"timing": "soon"}).context["page"].paginator.count, 1
        )
        self.assertEqual(
            self.client.get(reverse("issues"), {"q": self.asset.name}).context["page"].paginator.count, 27
        )

    def test_service_rollback_keeps_history_and_evidence_consistent(self):
        issue = self.create()
        with patch("portal.issues.audit", side_effect=RuntimeError("Synthetic DB failure")):
            with self.assertRaises(RuntimeError):
                issues.save_issue(self.admin, issue, {"status": "resolved"}, "Rollback")
        issue.refresh_from_db()
        self.assertEqual(issue.status, "new")
        self.assertEqual(IssueHistory.objects.filter(issue=issue).count(), 1)
        self.assertEqual(IssueRevision.objects.filter(issue=issue).count(), 1)

    def test_bulk_lifecycle_messages_revalidate_evidence_and_policy(self):
        from .models import Contact
        from .notifications import preview_batch, approve_local, authorized_delivery
        from tempfile import TemporaryDirectory
        from django.test import override_settings

        contact = Contact.objects.create(
            organization=self.a,
            name="Synthetic contract owner",
            role="Contract owner",
            email="contract@example.invalid",
            notification_enabled=True,
            reachable_at=timezone.now(),
            reviewed_at=timezone.now(),
            next_review=timezone.localdate() + timedelta(days=60),
        )
        issue = self.create(shareable=True)
        filters = {
            "domain": "asset_issues",
            "organization": str(self.a.pk),
            "kind": "support",
            "sort": "severity",
        }
        batch = preview_batch(
            self.admin,
            "company",
            filters,
            "{{ item_count }} issues · {{ organization }}",
            "Hello {{ contact_name }}\n{{ items }}",
        )
        delivery = batch.deliveries.get()
        self.assertIn("Synthetic contract", delivery.body)
        self.assertIn("Support expiry", delivery.body)
        self.assertEqual(list(delivery.issues.all()), [issue])
        self.assertEqual(delivery.findings.count(), 0)
        with TemporaryDirectory() as path, override_settings(EMAIL_FILE_PATH=path):
            approve_local(self.admin, batch.pk, [delivery.pk])
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "filed")
        issue.shareable = False
        issue.save()
        self.assertFalse(authorized_delivery(self.admin, delivery))
        self.login()
        response = self.client.get(reverse("notifications"))
        self.assertEqual(response.context["inbox_page"].paginator.count, 0)
        self.assertNotContains(response, "Synthetic contract owner")
        self.assertTrue(contact.notification_enabled)

    def test_lifecycle_notification_views_templates_and_stale_preview(self):
        from .models import Contact
        from .notifications import preview_batch, approve_local

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
        issue = self.create(shareable=True)
        self.login()
        response = self.client.get(
            reverse("notifications"),
            {"domain": "asset_issues", "organization": str(self.a.pk), "kind": "support"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, issue.title)
        self.assertNotContains(response, "registered software at")
        filters = {"domain": "asset_issues", "organization": str(self.a.pk), "sort": "severity"}
        batch = preview_batch(self.admin, "company", filters, "{{ item_count }} issues", "{{ items }}")
        delivery = batch.deliveries.get()
        issues.save_issue(
            self.admin,
            issue,
            {"event_date": timezone.localdate() + timedelta(days=100)},
            "Renewed coverage needs new preview",
        )
        with self.assertRaises(ValidationError):
            approve_local(self.admin, batch.pk, [delivery.pk])
        self.assertEqual(batch.deliveries.get().status, "draft")

    def test_subscriptions_prepare_changed_drafts_once_without_sending(self):
        from .models import Contact, NotificationReceipt, NotificationSubscription
        from .subscriptions import prepare

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
        issue = self.create(shareable=True)
        row = NotificationSubscription.objects.create(
            creator=self.admin,
            name="Support changes",
            mode="company",
            organization=self.a,
            filters={"organization": self.a.pk, "domain": "asset_issues", "sort": "severity"},
            subject_template="{{ item_count }} issues",
            body_template="{{ items }}",
        )
        with patch("portal.notifications.EmailBackend") as mail:
            first = prepare(row.pk)
            repeated = prepare(row.pk)
            self.assertEqual(first.pk, repeated.pk)
            issues.save_issue(self.admin, issue, {"owner_team": "New owner"}, "Responsibility updated")
            changed = prepare(row.pk)
            self.assertNotEqual(first.pk, changed.pk)
            first.refresh_from_db()
            self.assertEqual(first.status, "superseded")
            self.assertEqual(changed.status, "draft")
            mail.assert_not_called()
        self.assertEqual(NotificationReceipt.objects.count(), 0)
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(PermissionDenied):
            prepare(row.pk)

    def test_smtp_is_opt_in_non_development_tls_and_pins_sender_configuration(self):
        from .models import Contact, NotificationReceipt
        from .notifications import preview_batch, approve_local
        from django.test import override_settings

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
        self.create(shareable=True)
        filters = {"organization": self.a.pk, "domain": "asset_issues", "sort": "severity"}
        local = preview_batch(self.admin, "company", filters, "{{ item_count }} issues", "{{ items }}")
        with override_settings(NOTIFICATION_TRANSPORT="smtp", DEBUG=True):
            with self.assertRaises(ValidationError):
                preview_batch(self.admin, "company", filters, "{{ item_count }} issues", "{{ items }}")
        with override_settings(
            NOTIFICATION_TRANSPORT="smtp",
            DEBUG=False,
            EMAIL_HOST="smtp.example.com",
            EMAIL_PORT=587,
            EMAIL_USE_TLS=True,
            EMAIL_USE_SSL=False,
            DEFAULT_FROM_EMAIL="security@example.com",
        ):
            batch = preview_batch(self.admin, "company", filters, "{{ item_count }} issues", "{{ items }}")
            delivery = batch.deliveries.get()
            self.assertNotEqual(local.deliveries.get().fingerprint, delivery.fingerprint)
            with override_settings(DEFAULT_FROM_EMAIL="changed@example.com"):
                with self.assertRaises(ValidationError):
                    approve_local(self.admin, batch.pk, [delivery.pk])
            self.assertEqual(NotificationReceipt.objects.count(), 0)
            with patch("portal.notifications.SMTPBackend") as backend:
                backend.return_value.__enter__.return_value.send_messages.return_value = 1
                approve_local(self.admin, batch.pk, [delivery.pk])
                self.assertEqual(backend.call_count, 1)
                email = backend.return_value.__enter__.return_value.send_messages.call_args.args[0][0]
                self.assertEqual(email.to, ["owner@example.invalid"])
            delivery.refresh_from_db()
            self.assertEqual(delivery.status, "accepted")
            self.assertEqual(batch.transport, "smtp")

    def test_guarded_seed_is_repeatable_and_preserves_review_decisions(self):
        from django.core.management import call_command
        from django.test import override_settings

        with (
            override_settings(DEBUG=True),
            patch(
                "portal.management.commands.seed_asset_issues.ExchangeCommand.source", return_value=self.sa
            ),
        ):
            call_command("seed_asset_issues", actor=self.admin.username)
            issue = AssetIssue.objects.filter(kind="support").get()
            issues.save_issue(self.admin, issue, {"status": "resolved"}, "Preserve resolved example")
            call_command("seed_asset_issues", actor=self.admin.username)
            self.assertEqual(AssetIssue.objects.count(), 4)
            issue.refresh_from_db()
            self.assertEqual(issue.status, "resolved")

    def test_mosp_mapping_pins_issue_and_catalog_evidence_and_retains_withdrawal(self):
        from .models import MOSPSource, MOSPRisk, MOSPRiskRevision
        import uuid

        source = MOSPSource.objects.create(name="Synthetic catalog")
        risk = MOSPRisk.objects.create(
            source=source,
            uuid=uuid.uuid4(),
            external_id=1,
            description="Synthetic",
            payload={},
            content_hash="a" * 64,
        )
        revision = MOSPRiskRevision.objects.create(
            risk=risk, content_hash="a" * 64, risk_hash="a" * 64, payload={"synthetic": True}
        )
        risk.current_revision = revision
        risk.save()
        issue = self.create()
        link = issues.link_risk(
            self.admin, issue, risk, "Unavailable support can delay treatment of this scenario"
        )
        first = link.issue_revision_id
        issues.save_issue(self.admin, issue, {"owner_team": "Changed"}, "Assign owner")
        link.refresh_from_db()
        self.assertEqual(link.issue_revision_id, first)
        self.assertEqual(link.risk_revision_id, revision.pk)
        issues.withdraw_risk(self.admin, link, "Scenario no longer justified")
        link.refresh_from_db()
        self.assertIsNotNone(link.withdrawn_at)
        self.assertTrue(issue.revisions.filter(pk=first).exists())

    def test_exposure_seed_reports_skipped_and_real_windows_and_current_visibility(self):
        import io
        from django.core.management import call_command
        from django.test import override_settings
        from .models import PlumSnapshot, InfrastructureClaim

        with (
            override_settings(DEBUG=True),
            patch(
                "portal.management.commands.seed_asset_issues.ExchangeCommand.source", return_value=self.sa
            ),
        ):
            output = io.StringIO()
            call_command("seed_asset_issues", actor=self.admin.username, stdout=output)
            self.assertIn("Exposure example SKIPPED", output.getvalue())
            self.assertEqual(PlumSnapshot.objects.count(), 0)
            self.asset.upstream_data = {"primary_ip4": "192.0.2.25/24"}
            self.asset.save()
            output = io.StringIO()
            call_command("seed_asset_issues", actor=self.admin.username, stdout=output)
            self.assertIn("Historical Exposure: 2 snapshots retained, 2 currently visible", output.getvalue())
            self.assertIn("192.0.2.25", output.getvalue())
            self.assertEqual(PlumSnapshot.objects.count(), 2)
            claim = InfrastructureClaim.objects.get(organization=self.a, kind="ip", value="192.0.2.25")
            claim.status = "declared"
            claim.save()
            output = io.StringIO()
            call_command("seed_asset_issues", actor=self.admin.username, stdout=output)
            self.assertIn("2 snapshots retained, 0 currently visible", output.getvalue())
            claim.refresh_from_db()
            self.assertEqual(claim.status, "declared")
