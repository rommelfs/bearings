"""Opt-in actual vendor XML regression; local synthetic inventories and an isolated test DB only."""

import os
import uuid
from pathlib import Path
from unittest import skipUnless
from django.utils import timezone
from .tests import Fixture
from . import test_agents as legacy
from . import agents, distro_oval, distro_cves
from .models import DistroFeed, Finding


@skipUnless(
    os.environ.get("BEARINGS_OVAL_LIVE_DIR"),
    "Set BEARINGS_OVAL_LIVE_DIR to reviewed public vendor XML downloads",
)
class ActualVendorTests(Fixture):
    legacy_manual_projection = False
    setUp = legacy.AgentTests.setUp
    post = legacy.AgentTests.post
    enroll = legacy.AgentTests.enroll
    data = legacy.AgentTests.data
    send = legacy.AgentTests.send
    relax = legacy.AgentTests.relax

    def exercise(self, distro, release, name, manager, binary):
        path = Path(os.environ["BEARINGS_OVAL_LIVE_DIR"]) / ("bearings-" + distro + "-oval.xml")
        self.assertTrue(path.is_file())

        def thresholds(n):
            out = []
            if name in n.get("package", []):
                out += [
                    s["text"]
                    for g in n["states"]
                    for s in g
                    if s.get("field") == "evr" and s.get("operation") == "less than"
                ]
            for child in n.get("children", []):
                out += thresholds(child)
            return out

        row = None
        for value in distro_oval.compile_feed(path, distro, release):
            if (manager, name) in value["packages"] and thresholds(value["criteria"]):
                row = value
                break
        self.assertIsNotNone(row, "Actual feed has no supported named package threshold")
        feed = DistroFeed.objects.create(
            key=distro + ":" + release,
            generation=uuid.uuid4(),
            last_success=timezone.now(),
            content_hash="synthetic-subset-of-reviewed-vendor-download",
        )
        distro_cves.store_batch(feed, feed.generation, [row])
        self.enroll()
        data = self.data(version="0:0")
        data["os"].update(id=distro, version=release)
        c = data["components"][0]
        c.update(
            manager=manager,
            name=binary,
            key=manager + ":" + binary + ":amd64",
            architecture="amd64" if manager == "dpkg" else "x86_64",
        )
        c["key"] = manager + ":" + binary + ":" + c["architecture"]
        if distro == "debian":
            c["source"] = {"name": name, "version": "0:0"}
        self.assertEqual(self.send(data).status_code, 202)
        agents.process_pending()
        result = distro_cves.evaluate_device(self.device.pk)
        self.assertGreater(result["potential"] + result["uncertain"], 0)
        self.assertTrue(Finding.objects.exists())
        self.assertTrue(all(f.record.external_id.startswith("CVE-") for f in Finding.objects.all()))
        self.assertEqual(Finding.objects.filter(organization=self.b).count(), 0)

    def test_actual_canonical_binary_rule(self):
        self.exercise("ubuntu", "24.04", "openssl", "dpkg", "openssl")

    def test_actual_debian_source_rule(self):
        self.exercise("debian", "12", "openssl", "dpkg", "libssl3")

    def test_actual_redhat_rule_keeps_unreported_conditions_uncertain(self):
        self.exercise("rhel", "9", "vim-common", "rpm", "vim-common")
        self.assertFalse(Finding.objects.filter(analyst_applicability="affected").exists())
