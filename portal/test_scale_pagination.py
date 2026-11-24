"""Prevent whole-inventory hydration and unbounded organization UI/permission work."""

from django.db import connection
from django.db.models.signals import post_init
from django.test.utils import CaptureQueriesContext
from .tests import Fixture
from .models import Asset, Organization, InventorySource, AuditEvent


class ScalePaginationTests(Fixture):
    def setUp(self):
        self.record_finding()
        self.login(self.analyst)
        orgs = Organization.objects.bulk_create(
            [
                Organization(name=f"ScaleExtra{i:03d}", slug=f"extra{i:03d}", operator_visibility=True)
                for i in range(120)
            ]
        )
        sources = InventorySource.objects.bulk_create(
            [InventorySource(organization=o, mode="manual") for o in orgs]
        )
        Asset.objects.bulk_create(
            [
                Asset(organization=o, source=s, name=f"server-{i}", kind="server")
                for o, s in zip(orgs, sources)
                for i in range(30)
            ]
        )

    def test_review_hydrates_only_displayed_assets_and_paginates_company_cards(self):
        initialized = []

        def track(sender, instance, **kwargs):
            initialized.append(instance.pk)

        post_init.connect(track, sender=Asset)
        try:
            with CaptureQueriesContext(connection) as queries:
                r = self.client.get("/reviews/")
        finally:
            post_init.disconnect(track, sender=Asset)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["orgs"]), 24)
        self.assertEqual(r.context["org_page"].paginator.count, 121)
        self.assertLessEqual(len(initialized), 25)
        self.assertLessEqual(len(queries), 45)
        self.assertTrue(
            AuditEvent.objects.filter(actor=self.analyst, action="operator.review_queue").exists()
        )
        second = self.client.get("/reviews/?org_page=2")
        self.assertFalse({o.pk for o in r.context["orgs"]} & {o.pk for o in second.context["orgs"]})

    def test_issue_company_options_are_bounded_searchable_and_scoped(self):
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get("/issues/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["orgs"]), 50)
        self.assertLessEqual(len(queries), 35)
        self.assertNotContains(r, "Beta")
        selected = self.client.get("/issues/?company_q=ScaleExtra099")
        self.assertEqual([o.slug for o in selected.context["orgs"]], ["extra099"])
        self.assertEqual(self.client.get("/issues/?organization=beta").status_code, 404)
