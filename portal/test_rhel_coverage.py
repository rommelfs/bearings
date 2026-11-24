"""Inventory support must not imply a nonexistent RHEL 10 OVAL evaluation."""

from unittest.mock import patch
from django.test import override_settings
from .tests import Fixture
from .test_overview_cleanup import OverviewCleanupTests as Helpers
from .models import DistroFeed
from . import distro_cves, distro_sources
from .connectors.http import ConnectorError


class RhelCoverageTests(Fixture):
    package = Helpers.package
    reporter = Helpers.reporter

    def test_rhel_8_and_9_remain_supported_but_10_cannot_select_an_oval_feed(self):
        for release in ("8.10", "9.7"):
            self.assertEqual(distro_sources.key_for({"id": "rhel", "version": release}), "rhel:" + release[0])
        for release in ("10", "10.3"):
            self.assertIsNone(distro_sources.key_for({"id": "rhel", "version": release}))
        self.assertNotIn("rhel:10", distro_sources.supported_keys())
        with self.assertRaises(ConnectorError):
            distro_sources.url_for("rhel:10")

    @override_settings(DISTRO_CVE_ENABLED=True)
    def test_old_pending_receipt_is_corrected_without_requesting_the_404_feed(self):
        device, _ = self.reporter(state="pending")
        device.os = {"id": "rhel", "version": "10.3"}
        device.distro_summary = {"state": "pending", "feed": "rhel:10"}
        device.save()
        feed = DistroFeed.objects.create(key="rhel:10", error="Previous feed retrieval failed")
        with patch("portal.distro_sources.download") as download:
            self.assertEqual(distro_cves.run(), 1)
            download.assert_not_called()
        device.refresh_from_db()
        self.assertEqual(device.distro_summary["state"], "unsupported")
        self.assertIn("CSAF/VEX", device.distro_summary["message"])
        self.assertFalse(device.distro_requested)
        feed.refresh_from_db()
        self.assertEqual(feed.error, "Previous feed retrieval failed")
        self.login(self.reader)
        response = self.client.get(self.url("asset", pk=self.asset.pk))
        self.assertContains(response, "Red Hat publishes no RHEL 10 OVAL feed")
        self.assertContains(response, "This distribution/release is not evaluated automatically")
        self.assertNotContains(response, "vendor cache refresh pending")
        self.assertEqual(device.components.count(), 1)
