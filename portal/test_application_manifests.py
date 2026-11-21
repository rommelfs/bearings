"""Signed manifest observations update only owned versions; packages keep their coverage."""

import copy
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .tests import Fixture
from . import test_agents as legacy
from . import agents
from .agent_protocol import report_data
from .manifest_inventory import MISP_CPE
from .models import AgentComponent, AgentReport, Product, Installation, ProductWatch
from .netbox_export import snapshot


def application(version="2.5.52", path="/var/www/MISP/VERSION.json"):
    return {
        "key": "manifest:misp-main:all",
        "manager": "manifest",
        "name": "MISP",
        "version": version,
        "architecture": "all",
        "manifest": {"method": "misp-version-json", "path": path, "sha256": "a" * 64},
    }


class ManifestTests(Fixture):
    legacy_manual_projection = False
    setUp = legacy.AgentTests.setUp
    post = legacy.AgentTests.post
    enroll = legacy.AgentTests.enroll
    data = legacy.AgentTests.data
    send = legacy.AgentTests.send
    relax = legacy.AgentTests.relax

    def report(self, sequence=1, app=None):
        data = self.data(sequence=sequence)
        data["applications"] = [app or application()]
        response = self.send(data)
        self.assertEqual(response.status_code, 202, response.content)
        agents.process_pending()
        return data

    def test_automatic_misp_projection_version_update_watch_and_netbox_evidence(self):
        self.enroll()
        self.report()
        component = AgentComponent.objects.get(manager="manifest")
        self.assertTrue(component.automatic_installation)
        self.assertEqual(component.installation.product.identifier, MISP_CPE)
        self.assertEqual(component.installation.version, "2.5.52")
        self.assertEqual(AgentReport.objects.get().component_count, 2)
        watch = ProductWatch.objects.get(product=component.installation.product)
        watch.enabled = False
        watch.requested = False
        watch.save()
        self.relax()
        self.report(sequence=2, app=application("2.5.53"))
        component.refresh_from_db()
        self.assertEqual(component.installation.version, "2.5.53")
        watch.refresh_from_db()
        self.assertFalse(watch.enabled)
        self.assertTrue(watch.requested)
        self.device.refresh_from_db()
        exported = snapshot(self.device)
        row = next(row for row in exported["software"] if row["manager"] == "manifest")
        self.assertEqual(row["manifest"]["method"], "misp-version-json")
        self.assertEqual(row["manifest"]["path"], "/var/www/MISP/VERSION.json")
        self.assertFalse(self.installation.version)
        self.login()
        response = self.client.get(self.url("agent-center") + f"?device={self.device.pk}")
        self.assertContains(response, "Application version evidence:")
        self.assertContains(response, "running deployment not attested")

    def test_manual_misp_is_not_taken_over_and_explicit_binding_updates_future_versions(self):
        self.enroll()
        product = Product.objects.create(organization=self.a, name="MISP", identifier=MISP_CPE)
        existing = Installation.objects.create(asset=self.asset, product=product, version="2.5.1")
        self.report()
        component = AgentComponent.objects.get(manager="manifest")
        existing.refresh_from_db()
        self.assertEqual(existing.version, "2.5.1")
        self.assertIsNone(component.installation_id)
        self.assertEqual(Installation.objects.filter(asset=self.asset, product=product).count(), 1)
        with self.assertRaises(ValidationError):
            agents.bind(self.admin, self.a, component.pk, self.installation.pk)
        bound = agents.bind(self.admin, self.a, component.pk, existing.pk)
        self.assertEqual(bound.version, "2.5.52")
        self.relax()
        self.report(sequence=2, app=application("2.5.53"))
        existing.refresh_from_db()
        self.assertEqual(existing.version, "2.5.53")

    def test_package_only_report_does_not_refresh_or_remove_missing_manifest(self):
        self.enroll()
        self.report()
        component = AgentComponent.objects.get(manager="manifest")
        old = timezone.now() - timedelta(hours=13)
        AgentComponent.objects.filter(pk=component.pk).update(observed_at=old)
        self.relax()
        self.send(self.data(sequence=2))
        agents.process_pending()
        component.refresh_from_db()
        self.assertEqual(component.observed_at, old)
        self.assertTrue(component.stale)
        self.assertIsNone(component.missing_since)
        self.assertEqual(component.installation.version, "2.5.52")
        self.assertEqual(AgentComponent.objects.filter(manager="dpkg", missing_since__isnull=True).count(), 1)

    def test_strict_wire_limits_methods_paths_duplicates_and_no_foreign_data_adoption(self):
        base = self.data()
        base["applications"] = [application()]
        report_data(base)
        variants = []
        for field, value in [
            ("method", "shell"),
            ("path", "/etc/shadow"),
            ("path", "/var/www/MISP/../VERSION.json"),
            ("sha256", "raw secret"),
        ]:
            row = copy.deepcopy(base)
            row["applications"][0]["manifest"][field] = value
            variants.append(row)
        row = copy.deepcopy(base)
        row["applications"] *= 17
        variants.append(row)
        row = copy.deepcopy(base)
        row["applications"] *= 2
        variants.append(row)
        row = copy.deepcopy(base)
        row["scope"] = "selected-packages"
        row["complete"] = False
        variants.append(row)
        row = copy.deepcopy(base)
        row["applications"][0]["version"] = "2.5.1;id"
        variants.append(row)
        row = copy.deepcopy(base)
        row["applications"][0]["manifest"]["method"] = []
        variants.append(row)
        for row in variants:
            with self.assertRaises(ValueError):
                report_data(row)
        foreign = Product.objects.create(organization=self.b, name="MISP", identifier=MISP_CPE)
        Installation.objects.create(asset=self.other, product=foreign, version="2.4.0")
        self.enroll()
        self.report()
        self.assertEqual(
            AgentComponent.objects.get(manager="manifest").installation.product.organization_id, self.a.pk
        )
        self.assertEqual(Installation.objects.get(asset=self.other).version, "2.4.0")

    def test_changed_application_identity_is_rejected_without_rewriting_bound_version(self):
        self.enroll()
        self.report()
        self.relax()
        self.report(sequence=2, app=application("9.9.9", "/opt/other/VERSION.json"))
        self.assertEqual(AgentReport.objects.order_by("sequence").last().status, "rejected")
        self.assertEqual(AgentComponent.objects.get(manager="manifest").installation.version, "2.5.52")

    def test_generic_json_regex_and_git_methods_keep_explicit_identity_and_owned_versions(self):
        self.enroll()
        for sequence, method in enumerate(["json-fields", "file-regex", "git-tag"], 1):
            if sequence > 1:
                self.relax()
            app = application()
            app.update(
                key=f"manifest:generic-{sequence}:all", name=f"Example App {sequence}", version="1.2.3"
            )
            app["manifest"].update(
                method=method,
                path="/opt/example" if method == "git-tag" else f"/opt/example/release-{sequence}.json",
                identifier="cpe:2.3:a:example:product:*:*:*:*:*:*:*:*",
                profile_sha256="b" * 64,
            )
            if method == "git-tag":
                app["manifest"].update(commit="a" * 40, dirty=False)
            self.report(sequence=sequence, app=app)
            c = AgentComponent.objects.get(key=app["key"])
            self.assertEqual(c.installation.version, "1.2.3")
            self.assertEqual(c.installation.product.identifier, app["manifest"]["identifier"])
            self.assertEqual(c.manifest["profile_sha256"], "b" * 64)
            self.assertTrue(ProductWatch.objects.get(product=c.installation.product).enabled)
        data = self.data(sequence=4)
        data["applications"] = [copy.deepcopy(app)]
        data["applications"][0]["manifest"]["dirty"] = True
        with self.assertRaises(ValueError):
            report_data(data)
        data["applications"][0]["manifest"].update(dirty=False, identifier="https://private-host.invalid")
        with self.assertRaises(ValueError):
            report_data(data)
