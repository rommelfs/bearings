"""Vendor criteria, native backports, scoped automatic publication and retained failures."""

from django.test import TransactionTestCase
from django.db import connection, connections
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from threading import Event
import hashlib
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.utils import timezone
from .tests import Fixture
from . import test_agents as legacy
from . import agents, distro_cves, distro_oval
from .models import (
    AgentDevice,
    AgentComponent,
    DistroFeed,
    DistroAdvisory,
    DistroMatchRevision,
    Finding,
    SourceRecord,
)

XML = """<oval_definitions xmlns="http://oval.mitre.org/XMLSchema/oval-definitions-5" xmlns:l="http://oval.mitre.org/XMLSchema/oval-definitions-5#linux">
<definitions><definition id="oval:synthetic:def:1" class="vulnerability"><metadata><title>SYNTHETIC nginx update</title><reference source="CVE" ref_id="CVE-2099-99999"/><description>Synthetic vendor fixture, not operational intelligence</description><advisory><severity>High</severity></advisory></metadata><criteria operator="AND"><criterion test_ref="t1"/></criteria></definition></definitions>
<tests><l:dpkginfo_test id="t1" check="at least one" check_existence="at_least_one_exists"><l:object object_ref="o1"/><l:state state_ref="s1"/></l:dpkginfo_test></tests>
<objects><l:dpkginfo_object id="o1"><l:name>nginx</l:name></l:dpkginfo_object></objects>
<states><l:dpkginfo_state id="s1"><l:evr datatype="debian_evr_string" operation="less than">1:1.24.0-2ubuntu7.6</l:evr></l:dpkginfo_state></states></oval_definitions>"""


class DistroTests(Fixture):
    legacy_manual_projection = False
    setUp = legacy.AgentTests.setUp
    post = legacy.AgentTests.post
    enroll = legacy.AgentTests.enroll
    data = legacy.AgentTests.data
    send = legacy.AgentTests.send
    relax = legacy.AgentTests.relax

    def load(self, xml=XML, key="ubuntu:24.04"):
        feed, _ = DistroFeed.objects.get_or_create(key=key)
        DistroFeed.objects.filter(pk=feed.pk).update(last_attempt=None, last_success=None)

        @contextmanager
        def download(_):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "fixture.xml"
                p.write_text(xml)
                yield p, hashlib.sha256(xml.encode()).hexdigest()

        with patch("portal.distro_sources.download", side_effect=download):
            self.assertTrue(distro_cves.refresh(feed.pk), DistroFeed.objects.get(pk=feed.pk).error)
        feed.refresh_from_db()
        return feed

    def test_automatic_backport_match_then_fixed_keeps_human_workflow_and_history(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        summary = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(summary["potential"], 1)
        finding = Finding.objects.get()
        self.assertEqual(finding.applicability, "potential")
        self.assertEqual(finding.analyst_applicability, "unassessed")
        self.assertEqual(finding.record.source_severity, "high")
        self.assertTrue(finding.asset_issue)
        finding.analyst_applicability = "affected"
        finding.status = "confirmed"
        finding.save()
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(Finding.objects.count(), 1)
        self.assertEqual(DistroMatchRevision.objects.count(), 1)
        self.relax()
        self.send(self.data(sequence=2, version="1:1.24.0-2ubuntu7.6"))
        agents.process_pending()
        distro_cves.evaluate_device(self.device.pk)
        finding.refresh_from_db()
        self.assertEqual(finding.applicability, "not_affected")
        self.assertEqual(finding.analyst_applicability, "affected")
        self.assertEqual(finding.status, "confirmed")
        self.assertEqual(finding.distro_match.result, "not_affected")
        self.assertEqual(DistroMatchRevision.objects.count(), 2)
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.version, "")
        self.login()
        response = self.client.get("/organizations/alpha/intelligence/")
        self.assertContains(response, "Automatic distribution CVE check")

    def test_no_initial_finding_for_fixed_version(self):
        self.enroll()
        self.send(self.data(version="1:1.24.0-2ubuntu7.9"))
        agents.process_pending()
        self.load()
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(result["potential"], 0)
        self.assertFalse(Finding.objects.exists())

    def test_refresh_failure_does_not_wipe_generation_or_findings(self):
        self.enroll()
        self.send()
        agents.process_pending()
        feed = self.load()
        distro_cves.evaluate_device(self.device.pk)
        generation = feed.generation
        DistroFeed.objects.filter(pk=feed.pk).update(
            last_attempt=None, last_success=timezone.now() - timedelta(hours=7)
        )

        @contextmanager
        def bad(_):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "bad.xml"
                p.write_text(XML[:-40])
                yield p, "broken"

        with patch("portal.distro_sources.download", side_effect=bad):
            self.assertFalse(distro_cves.refresh(feed.pk))
        feed.refresh_from_db()
        self.assertEqual(feed.generation, generation)
        self.assertTrue(feed.error)
        self.assertEqual(Finding.objects.count(), 1)
        self.assertEqual(DistroAdvisory.objects.count(), 1)

    def test_disabled_revoked_stale_foreign_data_and_unsupported_distro(self):
        self.enroll()
        self.send()
        agents.process_pending()
        feed = self.load()
        AgentDevice.objects.filter(pk=self.device.pk).update(enabled=False)
        self.assertIsNone(distro_cves.evaluate_device(self.device.pk))
        self.assertFalse(Finding.objects.exists())
        AgentDevice.objects.filter(pk=self.device.pk).update(enabled=True, os={"id": "rocky", "version": "9"})
        self.assertEqual(distro_cves.evaluate_device(self.device.pk)["state"], "unsupported")
        self.assertFalse(Finding.objects.exists())
        self.assertEqual(SourceRecord.objects.filter(organization=self.b).count(), 0)
        feed.enabled = False
        feed.save()

    def test_debian_requires_exact_source_mapping_and_source_version(self):
        self.enroll()
        data = self.data(version="1:1.24.0-2ubuntu7.5+b1")
        data["os"].update(id="debian", version="12")
        self.send(data)
        agents.process_pending()
        self.load(key="debian:12")
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(result["missing_source_metadata"], 1)
        self.assertFalse(Finding.objects.exists())
        self.relax()
        data = self.data(sequence=2)
        data["os"].update(id="debian", version="12")
        data["components"][0]["source"] = {"name": "nginx", "version": "1:1.24.0-2ubuntu7.5"}
        self.assertEqual(self.send(data).status_code, 202)
        agents.process_pending()
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(result["potential"], 1)
        self.assertEqual(AgentComponent.objects.get().package_source["name"], "nginx")

    def test_no_namespace_or_actor_policy_grants_from_source(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        self.login(self.reader)
        self.assertEqual(self.client.get("/organizations/alpha/intelligence/").status_code, 200)
        self.assertEqual(self.client.get("/organizations/beta/intelligence/").status_code, 404)
        self.login(self.admin)
        self.assertContains(
            self.client.get("/discovery/?organization=alpha"), "Automatic distribution CVE discovery"
        )

    def test_unknown_signature_or_stream_guards_never_become_true(self):
        leaf = {
            "package": ["nginx"],
            "manager": "rpm",
            "source": False,
            "states": [[{"field": "evr", "text": "1:2.0-1.el9", "operation": "less than"}]],
            "check": "at least one",
            "state_operator": "AND",
            "existence": "at_least_one_exists",
        }
        facts = {("rpm", False, "nginx"): [{"id": 1, "version": "1:1.0-1.el9", "architecture": "x86_64"}]}
        rule = {"operator": "AND", "children": [leaf, {"unknown": "signature/stream not reported"}]}
        result, ids = distro_oval.evaluate(rule, facts, True, {"id": "rhel", "version": "9"})
        self.assertIsNone(result)
        self.assertEqual(ids, {1})
        facts[("rpm", False, "nginx")][0]["version"] = "1:2.0-1.el9"
        result, ids = distro_oval.evaluate(rule, facts, True, {})
        self.assertFalse(result)
        self.assertEqual(ids, set())

    def test_native_version_semantics(self):
        for manager, a, b, want in [
            ("dpkg", "1:1.0-1ubuntu2.3", "1:1.0-1ubuntu2.2", 1),
            ("dpkg", "1.0~rc1", "1.0", -1),
            ("dpkg", "2:0.1", "1:9.9", 1),
            ("dpkg", "1.0+deb12u2", "1.0+deb12u1", 1),
            ("rpm", "0:1.0^git1-1", "0:1.0-1", 1),
            ("rpm", "0:1.0~rc1-1", "0:1.0-1", -1),
            ("rpm", "1:1.0-1.el9_5.2", "1:1.0-1.el9_5.1", 1),
        ]:
            self.assertEqual(distro_oval.compare(manager, a, b), want)

    def test_xml_entities_and_unresolved_test_references_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.xml"
            p.write_text('<!DOCTYPE x [<!ENTITY boom "bad">]>' + XML)
            with self.assertRaises(Exception):
                list(distro_oval.compile_feed(p, "ubuntu", "24.04"))
        self.enroll()
        self.send()
        agents.process_pending()
        value, ids = distro_oval.evaluate({"unknown": "unresolved"}, {}, True, {})
        self.assertIsNone(value)
        self.assertFalse(ids)

    def test_cache_generation_change_does_not_reopen_unchanged_evidence(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        count = DistroMatchRevision.objects.count()
        # Force another complete download with identical definition semantics and a changed unrelated byte.
        self.load(XML + "\n")
        distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(DistroMatchRevision.objects.count(), count)

    def test_unsupported_predicate_does_not_produce_false_unaffected(self):
        self.assertIsNone(
            distro_oval.condition(
                "", {"field": "signature_key", "text": "abcd", "operation": "equals"}, "rpm"
            )
        )
        self.assertIsNone(
            distro_oval.condition("", {"field": "version", "text": "9", "operation": "equals"}, "rpm")
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "duplicate.xml"
            p.write_text(XML.replace("</tests>", '<l:dpkginfo_test id="t1"/></tests>'))
            with self.assertRaises(Exception):
                list(distro_oval.compile_feed(p, "ubuntu", "24.04"))

    def test_existence_only_and_unsupported_state_operator(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load(XML.replace('<l:state state_ref="s1"/>', ""))
        self.assertEqual(distro_cves.evaluate_device(self.device.pk)["potential"], 1)
        self.load(XML.replace('<l:dpkginfo_state id="s1">', '<l:dpkginfo_state id="s1" operator="OR">'))
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(result["potential"], 0)
        self.assertEqual(result["uncertain"], 1)


@skipUnless(connection.vendor == "postgresql", "Separate connection lease validation requires PostgreSQL")
class FeedLeaseTests(TransactionTestCase):
    def test_second_worker_does_not_download_while_first_worker_has_lease(self):
        feed = DistroFeed.objects.create(key="ubuntu:24.04")
        entered = Event()
        release = Event()

        @contextmanager
        def download(_):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Synthetic lease test timed out")
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "feed.xml"
                p.write_text(XML)
                yield p, hashlib.sha256(XML.encode()).hexdigest()

        def first():
            try:
                return distro_cves.refresh(feed.pk)
            finally:
                connections.close_all()

        with patch("portal.distro_sources.download", side_effect=download) as request:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(first)
                try:
                    self.assertTrue(entered.wait(5))
                    self.assertFalse(distro_cves.refresh(feed.pk))
                finally:
                    release.set()
                self.assertTrue(future.result(timeout=15))
            self.assertEqual(request.call_count, 1)
        feed.refresh_from_db()
        self.assertIsNone(feed.lease_id)
