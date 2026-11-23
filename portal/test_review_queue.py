"""A patched distribution package must not inflate the actionable review queue."""

import copy
import json
import uuid
from unittest import skipUnless
from pathlib import Path
from datetime import timedelta
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext
from . import agents, distro_cves, distro_oval
from .models import DistroFeed, DistroMatch, Finding
from .review_queue import classified
from .test_distro_cves import DistroTests
from .test_package_verdicts import save_browser_evidence


class QueueTests(DistroTests):
    def prepare(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        self.login()
        return Finding.objects.get()

    def bucket(self):
        return classified(Finding.objects.all()).values_list("queue_bucket", flat=True).get()

    def test_current_affected_fixed_and_human_conflict_remain_distinct(self):
        finding = self.prepare()
        self.assertEqual(self.bucket(), "action")
        response = self.client.get("/reviews/")
        self.assertEqual(response.context["review_total"], 1)
        self.assertContains(response, "Affected package version")
        save_browser_evidence("queue-affected", response)
        self.relax()
        self.send(self.data(sequence=2, version="1:1.24.0-2ubuntu7.9"))
        agents.process_pending()
        self.assertEqual(self.bucket(), "pending")
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(self.bucket(), "cleared")
        response = self.client.get("/reviews/")
        self.assertEqual(response.context["review_total"], 0)
        self.assertNotContains(response, 'id="review-' + str(finding.pk) + '"')
        response = self.client.get("/reviews/?state=cleared")
        self.assertEqual(response.context["review_total"], 1)
        self.assertContains(response, "includes the vendor fix")
        save_browser_evidence("queue-fixed", response)
        finding.refresh_from_db()
        self.assertEqual((finding.status, finding.analyst_applicability), ("new", "unassessed"))
        finding.analyst_applicability = "affected"
        finding.save()
        self.assertEqual(self.bucket(), "action")
        self.assertContains(self.client.get("/reviews/"), "saved analyst assessment says affected")

    def test_currentness_matches_model_for_all_relevant_inputs(self):
        finding = self.prepare()
        match = finding.distro_match
        mutations = [
            {"snapshot": {**match.snapshot, "evaluator_version": 1}},
            {"snapshot": {**match.snapshot, "package": {}}},
            {"snapshot": {**match.snapshot, "source_package": {"name": "other"}}},
            {"snapshot": {**match.snapshot, "version": "other"}},
            {"snapshot": {**match.snapshot, "inventory_sequence": 999}},
            {"snapshot": {**match.snapshot, "os": {}}},
            {"snapshot": {**match.snapshot, "rule_sha256": "old"}},
            {"snapshot": {**match.snapshot, "feed": "debian:12"}},
            {"snapshot": {**match.snapshot, "package_check": {}}},
        ]
        original = match.snapshot
        for fields in mutations:
            with self.subTest(fields=fields):
                DistroMatch.objects.filter(pk=match.pk).update(**fields)
                loaded = DistroMatch.objects.get(pk=match.pk)
                self.assertTrue(loaded.inputs_changed)
                self.assertEqual(self.bucket(), "pending")
        DistroMatch.objects.filter(pk=match.pk).update(snapshot=original)
        self.assertEqual(self.bucket(), "action")
        feed = match.advisory.feed
        DistroFeed.objects.filter(pk=feed.pk).update(last_success=timezone.now() - timedelta(hours=13))
        self.assertEqual(self.bucket(), "pending")
        self.assertTrue(DistroMatch.objects.get(pk=match.pk).inputs_changed)

    def test_generated_queue_facts_preserve_evidence_and_follow_raw_snapshot_updates(self):
        from django.db import DatabaseError, transaction

        self.prepare()
        match = DistroMatch.objects.get()
        snapshot = copy.deepcopy(match.snapshot)
        snapshot["synthetic_retained_evidence"] = "Synthetic evidence context. " * 2000
        snapshot["package"]["synthetic_optional_null"] = None
        match.component.package_identity = snapshot["package"]
        match.component.save(update_fields=["package_identity"])
        DistroMatch.objects.filter(pk=match.pk).update(snapshot=snapshot)
        match.refresh_from_db()
        self.assertEqual(match.snapshot, snapshot)
        self.assertEqual(match.queue_proof["package"], snapshot["package"])
        self.assertLess(len(json.dumps(match.queue_proof)), len(json.dumps(snapshot)) // 5)
        self.assertFalse(match.inputs_changed)
        self.assertEqual(self.bucket(), "action")
        # QuerySet.update bypasses application save hooks. The stored expression
        # must still invalidate the queue immediately, with no refresh worker.
        changed = {**snapshot, "version": "synthetic changed version"}
        DistroMatch.objects.filter(pk=match.pk).update(snapshot=changed)
        match.refresh_from_db()
        self.assertEqual(match.queue_proof["version"], changed["version"])
        self.assertTrue(match.inputs_changed)
        self.assertEqual(self.bucket(), "pending")
        match.snapshot = snapshot
        DistroMatch.objects.bulk_update([match], ["snapshot"])
        self.assertEqual(self.bucket(), "action")
        # Neither a stale application cache nor a caller can assign the derived
        # column independently of the authoritative retained snapshot.
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE portal_distromatch SET queue_proof = %s WHERE id = %s", ["{}", match.pk]
                )

    @skipUnless(connection.vendor == "postgresql", "Stored-column upgrade acceptance uses PostgreSQL")
    def test_migration_projects_existing_evidence_without_republishing_it(self):
        from django.db.migrations.executor import MigrationExecutor
        from .models import DistroMatchRevision

        finding = self.prepare()
        match = DistroMatch.objects.get()
        snapshot, revisions = match.snapshot, DistroMatchRevision.objects.count()
        original_status = finding.status
        # TestCase holds fixture inserts in a transaction; resolve their deferred
        # FK events before DDL, as a real upgrade starts after committed writes.
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([("portal", "0071_ubuntu_status_queue_index")])
        finally:
            MigrationExecutor(connection).migrate([("portal", "0072_generated_distribution_queue_proof")])
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        match.refresh_from_db()
        finding.refresh_from_db()
        self.assertEqual(match.snapshot, snapshot)
        self.assertEqual(match.queue_proof["version"], snapshot["version"])
        self.assertEqual(DistroMatchRevision.objects.count(), revisions)
        self.assertEqual(finding.status, original_status)
        self.assertEqual(self.bucket(), "action")

    def test_projection_preserves_boolean_type_instead_of_matching_numeric_version_text(self):
        self.prepare()
        match = DistroMatch.objects.get()
        match.component.version = "1"
        match.component.save(update_fields=["version"])
        snapshot = {**match.snapshot, "version": True}
        DistroMatch.objects.filter(pk=match.pk).update(snapshot=snapshot)
        match.refresh_from_db()
        self.assertIs(match.queue_proof["version"], True)
        self.assertTrue(match.inputs_changed)
        self.assertEqual(self.bucket(), "pending")

    def test_stale_disabled_missing_and_expired_inputs_cannot_be_actionable_proof(self):
        self.prepare()
        match = DistroMatch.objects.get()
        device = match.component.device
        changes = [
            (device, "enabled", False),
            (device, "expires_at", timezone.now() - timedelta(seconds=1)),
            (device, "os", {"id": "debian", "version": "12"}),
            (device, "applied_sequence", device.applied_sequence + 1),
            (match.component, "observed_at", timezone.now() - timedelta(hours=13)),
            (match.component, "missing_since", timezone.now()),
            (match.advisory.feed, "enabled", False),
            (match.advisory.feed, "summary", {"compiler_version": 1}),
            (match.advisory, "content_hash", "changed"),
        ]
        for obj, field, value in changes:
            original = getattr(obj, field)
            with self.subTest(field=field):
                type(obj).objects.filter(pk=obj.pk).update(**{field: value})
                self.assertTrue(DistroMatch.objects.get(pk=match.pk).inputs_changed)
                self.assertEqual(self.bucket(), "pending")
                type(obj).objects.filter(pk=obj.pk).update(**{field: original})
                self.assertEqual(self.bucket(), "action")

    def test_presence_only_is_vendor_clarification_not_an_affected_version(self):
        self.prepare()
        match = DistroMatch.objects.get()
        match.snapshot["package_check"]["verdict"] = "unresolved"
        match.snapshot["package_check"]["comparisons"] = []
        match.snapshot["package_check"]["reason"] = "Vendor supplies no version boundary."
        match.save()
        self.assertEqual(self.bucket(), "unresolved")
        response = self.client.get("/reviews/?state=unresolved")
        self.assertEqual(response.context["review_total"], 1)
        self.assertContains(response, "Vendor supplies no version boundary.")
        save_browser_evidence("queue-unresolved", response)
        self.assertEqual(self.client.get("/reviews/").context["review_total"], 0)
        self.assertEqual(self.client.get("/reviews/?state=all").context["review_total"], 1)

    def test_actual_needrestart_fixed_boundary_is_excluded_from_action_counts(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/oval/ubuntu-noble-CVE-2026-124757.json").read_text()
        )
        feed = DistroFeed.objects.create(
            key="ubuntu:24.04",
            generation=uuid.uuid4(),
            last_success=timezone.now(),
            summary={"compiler_version": distro_oval.COMPILER_VERSION},
        )
        distro_cves.store_batch(feed, feed.generation, [fixture["definition"]])
        self.enroll()
        data = self.data(version="3.6-7ubuntu4.5")
        data["components"][0].update(name="needrestart", key="dpkg:needrestart:amd64")
        self.send(data)
        agents.process_pending()
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(self.bucket(), "action")
        self.relax()
        data["sequence"] = 2
        data["report_id"] = str(uuid.uuid4())
        data["components"][0]["version"] = "3.6-7ubuntu4.6"
        self.send(data)
        agents.process_pending()
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(self.bucket(), "cleared")
        finding = Finding.objects.get()
        proof = finding.distro_match.snapshot["package_check"]
        self.assertEqual(proof["verdict"], "fixed")
        self.assertEqual(proof["comparisons"][0]["installed_version"], "3.6-7ubuntu4.6")
        self.assertFalse(proof["comparisons"][0]["matches"])
        self.login()
        response = self.client.get("/reviews/")
        self.assertEqual(response.context["review_total"], 0)
        self.assertEqual(response.context["severity_counts"][1]["count"], 0)
        response = self.client.get("/reviews/?state=cleared")
        self.assertContains(response, "CVE-2026-124757")
        self.assertContains(response, 'class="review-cue severity-none"')
        self.assertContains(response, "View result & history")
        self.assertContains(response, "includes the vendor fix")
        save_browser_evidence("queue-needrestart-fixed", response)

    def test_status_counts_precede_pagination_and_restricted_records_are_hidden(self):
        finding = self.prepare()
        for i in range(30):
            extra = copy.copy(finding)
            extra.pk = None
            extra.rule = f"synthetic-queue-{i}"
            extra.save()
            match = copy.copy(finding.distro_match)
            match.pk = None
            match.finding = extra
            match.snapshot = copy.deepcopy(match.snapshot)
            match.snapshot["package_check"]["verdict"] = "unresolved"
            match.save()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/reviews/?state=unresolved")
        # Includes constant session/policy checks and bounded-list PostgreSQL guards.
        self.assertLessEqual(len(queries), 42)
        self.assertEqual(response.context["review_total"], 30)
        self.assertEqual(len(response.context["review_page"]), 25)
        self.assertEqual(self.client.get("/reviews/").context["review_total"], 1)
        with CaptureQueriesContext(connection) as short_queries:
            second = self.client.get("/reviews/?state=unresolved&review_page=2")
        self.assertEqual(len(second.context["review_page"]), 5)
        self.assertLessEqual(len(queries), len(short_queries) + 1)
        finding.record.shareable = False
        finding.record.save(update_fields=["shareable"])
        self.login(self.reader)
        response = self.client.get("/reviews/?state=all")
        self.assertEqual(response.context["review_total"], 0)
        self.assertTrue(all(state["count"] == 0 for state in response.context["queue_states"]))
