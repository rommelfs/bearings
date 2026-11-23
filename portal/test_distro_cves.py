"""Vendor criteria, native backports, scoped automatic publication and retained failures."""

from django.urls import reverse
from django.test import TransactionTestCase
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
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
    Product,
    Installation,
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

    def test_package_card_shows_vendor_rules_and_scoped_reviews_without_manual_setup(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        component = self.device.components.get(name="nginx")
        self.login()
        response = self.client.get(reverse("discovery"))
        self.assertContains(response, "1 indexed vendor definitions")
        self.assertContains(response, "Vendor lookup: nginx")
        self.assertContains(response, "Software identity:")
        self.assertContains(response, "Recognized by vendor definitions")
        self.assertContains(response, "Ready — supported vendor advisories are checked automatically")
        self.assertContains(response, "Server-wide coverage:")
        self.assertNotContains(
            response, reverse("discovery-configure", args=[self.a.slug, component.installation.product_id])
        )
        url = reverse("intelligence", args=[self.a.slug]) + "?installation=" + str(component.installation_id)
        self.assertContains(self.client.get(url), "CVE-2099-99999")
        self.assertEqual(
            self.client.get(
                reverse("intelligence", args=[self.b.slug])
                + "?installation="
                + str(component.installation_id)
            ).status_code,
            404,
        )

    def test_inventory_distinguishes_automatic_matching_reviews_and_optional_manual_lookup(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        component = self.device.components.get(name="nginx")
        self.login()
        for url in [
            reverse("asset", args=[self.a.slug, component.installation.asset_id]),
        ]:
            response = self.client.get(url)
            self.assertContains(response, "Ready — supported vendor advisories are checked automatically")
            self.assertContains(response, "1 recorded CVE review")
            self.assertNotContains(response, 'placeholder="CVE-2021-44228"')
            self.assertNotContains(response, "Retrieve for review")
            self.assertNotContains(response, "Configure automatic CVE discovery")
            self.assertNotContains(
                response,
                reverse("discovery-configure", args=[self.a.slug, component.installation.product_id]),
            )
        url = reverse("asset", args=[self.a.slug, component.installation.asset_id])
        response = self.client.get(url)
        self.assertContains(response, "Investigate a known CVE (optional)")
        self.assertContains(response, "does not confirm that this software is affected")
        self.login(self.reader)
        response = self.client.get(url)
        self.assertContains(response, "Automatic CVE matching:")
        self.assertNotContains(response, "Fetch CVE details for manual review")
        self.assertEqual(
            self.client.post(
                reverse("lookup-vulnerability", args=[self.a.slug, component.installation_id]),
                {"identifier": "CVE-2099-99999"},
            ).status_code,
            403,
        )
        response = self.client.get(
            reverse("discovery"), {"organization": self.a.slug, "product": component.installation.product_id}
        )
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(
            self.client.get(
                reverse("discovery"),
                {"organization": self.b.slug, "product": component.installation.product_id},
            ).status_code,
            404,
        )
        SourceRecord.objects.filter(finding__installation_id=component.installation_id).update(
            shareable=False
        )
        response = self.client.get(url)
        displayed = next(i for i in response.context["software_page"] if i.pk == component.installation_id)
        self.assertEqual(displayed.visible_review_count, 0)
        self.login(self.platform)
        response = self.client.get(url)
        displayed = next(i for i in response.context["software_page"] if i.pk == component.installation_id)
        self.assertEqual(displayed.visible_review_count, 1)
        for invalid in ["0", "-1", "x", "9" * 19, "9" * 40]:
            self.assertEqual(self.client.get(reverse("discovery"), {"product": invalid}).status_code, 404)

    def test_unchanged_feed_is_recompiled_after_compiler_upgrade(self):
        feed = self.load()
        old = feed.generation
        DistroFeed.objects.filter(pk=feed.pk).update(summary={"compiler_version": 0})
        self.assertEqual(distro_cves.feed_state(DistroFeed.objects.get(pk=feed.pk)), "pending")

        @contextmanager
        def same_download(_):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "feed.xml"
                p.write_text(XML)
                yield p, hashlib.sha256(XML.encode()).hexdigest()

        with patch("portal.distro_sources.download", side_effect=same_download):
            distro_cves.run()
        feed.refresh_from_db()
        self.assertNotEqual(feed.generation, old)
        self.assertEqual(feed.summary["compiler_version"], distro_oval.COMPILER_VERSION)

    def test_canonical_singleton_inventory_guards_support_at_least_one(self):
        xml = XML.replace(
            "xmlns:l=", 'xmlns:i="http://oval.mitre.org/XMLSchema/oval-definitions-5#independent" xmlns:l='
        )
        xml = xml.replace(
            "<definitions>",
            '<definitions><definition id="inventory" class="inventory"><criteria><criterion test_ref="family"/><criterion test_ref="os"/></criteria></definition>',
        )
        xml = xml.replace(
            '<criteria operator="AND">',
            '<criteria operator="AND"><extend_definition definition_ref="inventory"/>',
        )
        xml = xml.replace(
            "</tests>",
            '<i:family_test id="family" check="at least one"><i:object object_ref="family-object"/><i:state state_ref="family-state"/></i:family_test><i:textfilecontent54_test id="os" check="at least one"><i:object object_ref="os-object"/><i:state state_ref="os-state"/></i:textfilecontent54_test></tests>',
        )
        xml = xml.replace(
            "</objects>",
            r'<i:family_object id="family-object"/><i:textfilecontent54_object id="os-object"><i:filepath>/etc/lsb-release</i:filepath><i:pattern operation="pattern match">^[\s\S]*DISTRIB_CODENAME=([a-z]+)$</i:pattern><i:instance>1</i:instance></i:textfilecontent54_object></objects>',
        )
        xml = xml.replace(
            "</states>",
            '<i:family_state id="family-state"><i:family>unix</i:family></i:family_state><i:textfilecontent54_state id="os-state"><i:subexpression operation="equals">noble</i:subexpression></i:textfilecontent54_state></states>',
        )
        self.enroll()
        self.send()
        agents.process_pending()
        self.load(xml)
        self.assertEqual(distro_cves.evaluate_device(self.device.pk)["potential"], 1)
        # An unrecognized file expression must not become a trusted OS fact.
        self.load(xml.replace("DISTRIB_CODENAME", "ARBITRARY_FIELD"))
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertEqual(result["potential"], 0)
        self.assertEqual(result["uncertain"], 1)

    def test_discovery_queries_stay_bounded_across_package_cards(self):
        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        self.login()
        original = self.device.components.get(name="nginx")
        with CaptureQueriesContext(connection) as initial:
            self.assertEqual(self.client.get(reverse("discovery")).status_code, 200)
        for i in range(12):
            p = Product.objects.create(
                organization=self.a,
                name=f"Synthetic package {i}",
                identifier=f"pkg:deb/ubuntu/synthetic-{i}?arch=amd64",
            )
            installation = Installation.objects.create(asset=self.device.asset, product=p, version="1")
            AgentComponent.objects.create(
                device=self.device,
                key=f"dpkg:synthetic-{i}:amd64",
                name=f"synthetic-{i}",
                manager="dpkg",
                architecture="amd64",
                version="1",
                observed_at=timezone.now(),
                last_report_id=original.last_report_id,
                installation=installation,
                package_identity=original.package_identity,
            )
        with CaptureQueriesContext(connection) as larger:
            response = self.client.get(reverse("discovery"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Normalized package identity recorded")
        self.assertContains(response, "Monitoring vendor feed; no indexed advisory for this identity yet")
        self.assertLessEqual(len(larger), len(initial) + 2)

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
        self.assertEqual(distro_cves.evaluate_device(self.device.pk)["uncertain"], 1)
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
