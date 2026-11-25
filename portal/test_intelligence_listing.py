from django.urls import reverse

from .models import Asset, Installation, Product, SourceRecord
from .services import persist_lookup
from .tests import Fixture


class IntelligenceListingTests(Fixture):
    def publish(self, installation, cve, score=None, ubuntu=None, *, source=None):
        metrics = [{"cvssV3_1": {"version": "3.1", "baseScore": score}}] if score is not None else []
        payload = {"containers": {"cna": {"title": cve, "metrics": metrics}}}
        if ubuntu:
            payload["bearings_distro"] = {
                "schema": "bearings.distro-oval.v1",
                "feed": "ubuntu:24.04",
                "severity": ubuntu,
            }
        return persist_lookup(self.admin, installation, source or "fixture://catalog", cve, payload)

    def test_grouping_counts_and_drill_down_stay_scoped(self):
        host = Asset.objects.create(organization=self.a, source=self.sa, name="second host", kind="server")
        second = Installation.objects.create(asset=host, product=self.product)
        product = Product.objects.create(organization=self.a, name="second product")
        third = Installation.objects.create(asset=self.asset, product=product)
        cve = "CVE-2099-12345"
        self.publish(self.installation, cve, 9.8)
        self.publish(second, cve, 9.8)
        self.publish(third, cve, 9.8)
        self.publish(self.installation, cve.lower(), 8.0, source="fixture://secondary")
        hidden = self.publish(second, "CVE-2099-12346", 10, source="fixture://restricted")
        SourceRecord.objects.filter(pk=hidden.record_id).update(shareable=False)
        self.login(self.reader)
        url = reverse("intelligence", args=[self.a.slug])

        machine = self.client.get(url, {"view": "machine", "cvss_min": "8"})
        row = next(item for item in machine.context["page"] if item["name"] == self.asset.name)
        self.assertEqual((row["cves"], row["related_count"], row["max_cvss"]), (1, 2, 9.8))
        cards = self.client.get(url + row["url"])
        self.assertEqual(cards.context["page"].paginator.count, 1)
        self.assertContains(cards, "view=machine&amp;cvss_min=8")
        software = self.client.get(url, {"view": "software"})
        row = next(item for item in software.context["page"] if item["name"] == self.product.name)
        self.assertEqual((row["cves"], row["related_count"], row["max_cvss"]), (1, 2, 9.8))

    def test_filters_distinguish_cvss_ubuntu_priority_and_unknowns(self):
        url = reverse("intelligence", args=[self.a.slug])
        ubuntu = "https://security-metadata.canonical.com/oval/com.ubuntu.noble.cve.oval.xml.bz2"
        high = self.publish(self.installation, "CVE-2099-32340", 8.0, "high", source=ubuntu)
        self.publish(self.installation, "CVE-2099-32341", 9.9, "medium", source=ubuntu)
        self.publish(self.installation, "CVE-2099-32342", 9.9, "critical")
        self.publish(self.installation, "CVE-2099-32343", ubuntu="critical", source=ubuntu)
        self.publish(self.installation, "CVE-2099-32344", 1.2, "critical", source=ubuntu)
        self.login()
        criteria = {"cvss_min": "8.0", "ubuntu_above": "medium"}
        for mode in ("cve", "machine", "software"):
            response = self.client.get(url, {**criteria, "view": mode})
            self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(url, criteria).context["page"][0].pk, high.pk)
        self.assertEqual(
            self.client.get(url, {**criteria, "workflow": "resolved"}).context["page"].paginator.count, 0
        )
        self.assertEqual(self.client.get(url, {"cvss_min": "11"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"ubuntu_above": "unknown"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"view": "unknown"}).status_code, 400)

        self.publish(self.installation, high.record.external_id, 7.9, "high", source=ubuntu)
        high.record.refresh_from_db()
        self.assertEqual(high.record.source_cvss, 7.9)
        self.assertEqual(self.client.get(url, criteria).context["page"].paginator.count, 0)
