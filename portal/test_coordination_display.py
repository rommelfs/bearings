"""National follow-up explains concrete installations without widening evidence scope."""

from django.test.utils import CaptureQueriesContext
from django.test import override_settings
from django.db import connection
from django.urls import reverse
from .tests import Fixture
from .models import Finding, Installation, Product, SourceRecord


class CoordinationDisplayTests(Fixture):
    def setUp(self):
        self.login(self.analyst)

    def panel(self):
        return self.client.get(reverse("circl-panel", args=["problems"]))

    def test_single_unconfirmed_review_is_a_technical_check_not_coordination(self):
        finding = self.record_finding()
        self.installation.version = "2.5.51"
        self.installation.save()
        response = self.panel()
        self.assertEqual(response.context["coordination_cases"], [])
        self.assertEqual(len(response.context["technical_cases"]), 1)
        self.assertContains(response, "installed 2.5.51")
        self.assertContains(response, "Next step:")
        self.assertContains(response, "not established here")
        self.assertContains(response, f"?finding={finding.pk}#finding-{finding.pk}")
        self.assertNotContains(response, "Vulnerabilities needing coordination")

    def test_cross_company_requires_saved_affected_assessment_and_current_visibility(self):
        first = self.record_finding(shareable=False)
        first.analyst_applicability = "affected"
        first.save()
        self.b.operator_visibility = True
        self.b.save()
        record = SourceRecord.objects.create(
            organization=self.b,
            source="fixture://coordination",
            external_id=first.record.external_id,
            payload={},
            shareable=False,
        )
        other = Finding.objects.create(
            organization=self.b,
            installation=Installation.objects.create(
                asset=self.other,
                product=Product.objects.create(organization=self.b, name="Private other software"),
            ),
            record=record,
            explanation="fixture",
        )
        response = self.panel()
        self.assertEqual(len(response.context["coordination_cases"]), 1)
        self.assertContains(response, self.other.name)
        self.assertEqual(response.context["coordination_cases"][0]["affected"], 1)
        self.b.operator_visibility = False
        self.b.save()
        response = self.panel()
        self.assertEqual(response.context["coordination_cases"], [])
        self.assertNotContains(response, self.other.name)
        self.assertNotContains(response, f"?finding={other.pk}#finding-{other.pk}")
        first.status = "resolved"
        first.save()
        self.assertEqual(self.panel().context["technical_cases"], [])

    def test_examples_are_bounded_escaped_and_do_not_query_per_installation(self):
        first = self.record_finding()
        product = Product.objects.create(organization=self.a, name='<img src=x onerror="alert(1)">')
        first.installation.product = product
        first.installation.save()
        with CaptureQueriesContext(connection) as small:
            self.panel()
        for i in range(25):
            installation = Installation.objects.create(asset=self.asset, product=product, version=str(i))
            Finding.objects.create(
                organization=self.a,
                installation=installation,
                record=first.record,
                explanation="fixture",
            )
        with CaptureQueriesContext(connection) as large:
            response = self.panel()
        self.assertEqual(len(response.context["technical_cases"][0]["examples"]), 2)
        self.assertEqual(response.context["technical_cases"][0]["reviews"], 26)
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertLessEqual(len(large), len(small) + 1)

    @override_settings(NATIONAL_SNAPSHOT_THRESHOLD=0)
    def test_prepared_examples_exclude_companies_pending_refresh(self):
        from .national_snapshots import refresh_pending
        from .models import NationalState

        if connection.vendor != "postgresql":
            self.skipTest("Prepared national state requires PostgreSQL")
        first = self.record_finding()
        self.b.operator_visibility = True
        self.b.save()
        record = SourceRecord.objects.create(
            organization=self.b,
            source="fixture://pending",
            external_id=first.record.external_id,
            payload={},
            shareable=True,
        )
        installation = Installation.objects.create(
            asset=self.other, product=Product.objects.create(organization=self.b, name="Pending product")
        )
        Finding.objects.create(
            organization=self.b, installation=installation, record=record, explanation="fixture"
        )
        refresh_pending(limit=100)
        NationalState.objects.filter(organization=self.b).update(dirty=True)
        response = self.panel()
        row = response.context["technical_cases"][0]
        self.assertEqual(row["companies"], 1)
        self.assertEqual(len(row["examples"]), 1)
        self.assertContains(response, "pending refresh")
        self.assertNotContains(response, "Pending product")


class PackageCoordinationTests(Fixture):
    from .test_distro_cves import DistroTests as _Distro

    legacy_manual_projection = False
    setUp = _Distro.setUp
    post = _Distro.post
    enroll = _Distro.enroll
    data = _Distro.data
    send = _Distro.send
    relax = _Distro.relax
    load = _Distro.load

    def test_real_package_evaluation_fixed_and_changed_inputs_have_distinct_next_steps(self):
        from . import agents, distro_cves
        from .models import AgentComponent

        self.enroll()
        self.send()
        agents.process_pending()
        self.load()
        distro_cves.evaluate_device(self.device.pk)
        self.login(self.analyst)
        url = reverse("circl-panel", args=["problems"])
        response = self.client.get(url)
        self.assertContains(response, "Affected package version")
        self.assertContains(response, "Check vendor fix and repository availability")
        component = AgentComponent.objects.get(name="nginx")
        component.version = "1:1.24.0-2ubuntu7.6"
        component.save()
        component.installation.version = component.version
        component.installation.save()
        distro_cves.evaluate_device(self.device.pk)
        response = self.client.get(url)
        self.assertContains(response, "Installed package version includes the vendor fix")
        self.assertContains(response, "Reconcile the retained review")
        self.assertNotContains(response, "Check vendor fix and repository availability")
        self.device.os = {"id": "ubuntu", "version": "22.04"}
        self.device.save()
        response = self.client.get(url)
        self.assertContains(response, "Awaiting current package evaluation")
        self.assertNotContains(response, "Installed package version includes the vendor fix")
