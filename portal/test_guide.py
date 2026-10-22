from unittest.mock import patch
from django.urls import reverse
from django.test import override_settings
from django.core.management import call_command, CommandError
from . import tests
from .models import NetBoxInstance, RiskLink, DemoObject
from .asset_context import asset_context
from .demo_showcase import seed


class GuidedCaseTests(tests.Fixture):
    def setUp(self):
        self.finding = self.record_finding()
        self.path = self.url("case-guide", pk=self.finding.pk)
        self.login()

    def test_every_step_has_context_and_does_not_make_decisions(self):
        for step in ("asset", "evidence", "risk", "action", "followup"):
            response = self.client.get(self.path, {"step": step})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, self.asset.name)
            self.assertContains(response, 'aria-current="step"')
        self.assertFalse(RiskLink.objects.exists())
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, "new")
        self.assertEqual(self.client.get(self.path, {"step": "invalid"}).status_code, 404)

    def test_case_picker_and_peer_cases_respect_evidence_visibility(self):
        response = self.client.get(reverse("getting-started"), {"q": "Example"})
        self.assertContains(response, self.asset.name)
        self.assertNotContains(response, self.other.name)
        self.assertEqual(self.client.get(self.url("case-guide", self.b, pk=self.finding.pk)).status_code, 404)
        self.finding.record.shareable = False
        self.finding.record.save()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertNotContains(self.client.get(reverse("getting-started")), self.asset.name)

    def test_assessment_returns_to_guided_case_and_reader_cannot_edit(self):
        response = self.client.post(
            self.url("finding-review", pk=self.finding.pk) + "?return=guide",
            {
                "status": "under_review",
                "assessment": "potential",
                "reason": "Check package backports and prerequisites",
            },
        )
        self.assertRedirects(response, self.path + "?step=risk")
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.analyst_applicability, "potential")
        self.login(self.reader)
        self.assertNotContains(self.client.get(self.path, {"step": "evidence"}), "Record my assessment")
        self.assertEqual(
            self.client.post(self.url("finding-review", pk=self.finding.pk), {}).status_code, 403
        )

    @override_settings(
        CANVAS_ORIGIN="https://testserver", CANVAS_FRAME_ORIGINS=["https://netbox.example.invalid"]
    )
    def test_netbox_reference_canvas_uses_current_asset_identity_and_exact_instance(self):
        instance = NetBoxInstance.objects.create(
            name="Named lab",
            base_url="https://netbox.example.invalid",
            browser_url="https://netbox.example.invalid",
            token_env_var="SECRET_KEY",
        )
        self.sa.instance = instance
        self.sa.save()
        self.asset.upstream_data = {
            "rack": {"id": 7, "name": "Rack seven"},
            "primary_ip4": "192.0.2.3/24",
            "primary_ip4_id": 11,
        }
        self.asset.save()
        path = self.url("source-reference", pk=self.asset.pk, reference="rack")
        response = self.client.get(path, {"url": "https://evil.invalid"}, secure=True)
        self.assertContains(response, 'src="https://netbox.example.invalid/dcim/racks/7/"')
        self.assertNotContains(response, "evil.invalid")
        self.assertNotContains(response, "SECRET_KEY")
        guided = self.client.get(path, {"case": self.finding.pk}, secure=True)
        self.assertContains(guided, "Return to the Bearings case")
        self.assertContains(guided, self.path)
        self.assertEqual(self.client.get(path, {"case": 999999}, secure=True).status_code, 404)

        self.assertEqual(
            response["Content-Security-Policy"].split(";")[0], "frame-src https://netbox.example.invalid"
        )
        self.assertContains(response, "Return to the Bearings asset")
        self.assertEqual(
            self.client.get(
                self.url("source-reference", self.b, pk=self.asset.pk, reference="rack"), secure=True
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                self.url("source-reference", pk=self.asset.pk, reference="rack-99"), secure=True
            ).status_code,
            404,
        )
        self.assertNotIn("workspace_url", asset_context(self.asset)["rack"])
        self.assertEqual(asset_context(self.asset, workspace=True)["rack"]["workspace_url"], path)
        instance.enabled = False
        instance.save()
        self.assertEqual(self.client.get(path, secure=True).status_code, 404)


@override_settings(DEBUG=True)
class PHPExampleTests(tests.Fixture):
    def test_seed_retains_real_cve_evidence_assumptions_and_removal_provenance(self):
        from .management.commands.seed_php_example import CVES
        from .models import Finding

        dataset, _ = seed(self.platform, companies=2, assets_per_company=6)

        def lookup(cve):
            return "https://vulnerability.circl.lu", {
                "cveMetadata": {"cveId": cve, "state": "PUBLISHED"},
                "containers": {
                    "cna": {
                        "affected": [
                            {
                                "vendor": "PHP Group",
                                "product": "PHP",
                                "versions": [
                                    {
                                        "status": "affected",
                                        "version": "8.4.*",
                                        "lessThan": "8.4.27",
                                        "versionType": "semver",
                                    }
                                ],
                            }
                        ]
                    }
                },
            }

        from .connectors.http import ConnectorError

        before = dataset.entries.count()
        with patch(
            "portal.management.commands.seed_php_example.lookup",
            side_effect=[lookup(CVES[0]), ConnectorError("offline")],
        ):
            with self.assertRaises(CommandError):
                call_command("seed_php_example", actor=self.platform.username)
        self.assertEqual(dataset.entries.count(), before)
        with patch("portal.management.commands.seed_php_example.lookup", side_effect=lookup):
            call_command("seed_php_example", actor=self.platform.username)
            rows = Finding.objects.filter(record__external_id__in=CVES)
            self.assertEqual(rows.count(), 2)
            finding = rows.first()
            self.assertIn("SYNTHETIC", finding.explanation)
            self.assertEqual(finding.applicability, "unknown")
            self.assertTrue(
                DemoObject.objects.filter(
                    dataset=dataset, model_label="portal.finding", object_pk=str(finding.pk)
                ).exists()
            )
            finding.analyst_applicability = "not_affected"
            finding.save()
            count = dataset.entries.count()
            call_command("seed_php_example", actor=self.platform.username)
            finding.refresh_from_db()
            self.assertEqual(finding.analyst_applicability, "not_affected")
            self.assertEqual(dataset.entries.count(), count)
        from .demo_data import removal_plan, purge

        plan, _ = removal_plan(dataset)
        self.assertEqual(plan["blockers"], [])
        purge(self.platform, dataset.key, plan["fingerprint"])
        with self.assertRaises(CommandError):
            call_command("seed_php_example", actor=self.platform.username)
