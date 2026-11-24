"""List ordering is scoped, applied before pagination and retains navigation context."""

from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from django.core.management import CommandError
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from .table_sort import TableSort
from .test_review_focus import FocusTests
from .models import Asset, SourceRecord
from docker.dev import entrypoint


class SortLinkTests(SimpleTestCase):
    def test_toggle_retains_filters_and_resets_page(self):
        request = RequestFactory().get("/", {"focus": "matched", "page": "2", "sort": "priority"})
        sorting = TableSort(
            request, [("priority", "Priority", "rank", True), ("name", "Name", "name", False)]
        )
        self.assertFalse(sorting.order.descending)
        params = parse_qs(urlsplit(sorting.headers[0]["url"]).query)
        self.assertEqual(params, {"focus": ["matched"], "sort": ["priority"], "direction": ["asc"]})
        self.assertEqual(sorting.headers[0]["aria_sort"], "descending")
        for params in ({"sort": "password"}, {"direction": "invalid"}):
            with self.assertRaises(ValueError):
                TableSort(RequestFactory().get("/", params), [("priority", "Priority", "rank", True)])


class WorkerLaneTests(SimpleTestCase):
    def run_once(self, mode, error=None):
        with (
            patch.object(entrypoint, "environment"),
            patch("django.setup"),
            patch.object(entrypoint.sys, "argv", ["entrypoint", mode]),
            patch.object(entrypoint, "Path"),
            patch.object(entrypoint.time, "sleep", side_effect=StopIteration),
            patch("django.core.management.call_command", side_effect=error) as commands,
        ):
            with self.assertRaises(StopIteration):
                entrypoint.main()
        return [call.args[0] for call in commands.call_args_list]

    def test_inventory_jobs_do_not_wait_for_external_catalog_reads(self):
        calls = self.run_once("worker")
        self.assertEqual(calls[0], "process_jobs")
        self.assertIn("process_agent_reports", calls)
        self.assertFalse(any(name.startswith("sync_") for name in calls))

    def test_failed_source_refresh_does_not_stop_remaining_sources(self):
        calls = self.run_once("source-worker", CommandError("Synthetic source outage"))
        self.assertEqual(calls, ["sync_netbox", "sync_mosp", "sync_vulnerabilities", "sync_misp"])


class MachineSortTests(FocusTests):
    def test_priority_before_pagination_and_other_columns_toggle(self):
        self.cached()
        self.prepare()
        current = self.device.asset
        Asset.objects.filter(pk=current.pk).update(name="ZZZ affected")
        for index in range(27):
            Asset.objects.create(organization=self.a, source=self.sa, kind="server", name=f"AAA {index:02}")
        SourceRecord.objects.update(source_severity="critical")
        self.login(self.reader)
        url = reverse("organization-machines", args=[self.a.slug])
        response = self.client.get(url)
        rows = list(response.context["page"])
        self.assertEqual(rows[0].pk, current.pk)
        self.assertEqual(rows[0].priority_label, "Critical")
        self.assertContains(response, 'aria-sort="descending"')
        self.assertEqual(len(rows), 25)
        ascending = self.client.get(url, {"sort": "machine", "direction": "asc"})
        self.assertEqual(ascending.context["page"][0].name, "AAA 00")
        descending = self.client.get(url, {"sort": "machine", "direction": "desc", "focus": "all"})
        self.assertEqual(descending.context["page"][0].pk, current.pk)
        params = parse_qs(urlsplit(descending.context["next_url"]).query)
        self.assertEqual(params["sort"], ["machine"])
        self.assertEqual(params["direction"], ["desc"])
        self.assertEqual(params["focus"], ["all"])
        for key in ("company", "evaluation", "priority", "evidence"):
            for direction in ("asc", "desc"):
                self.assertEqual(self.client.get(url, {"sort": key, "direction": direction}).status_code, 200)
        self.assertEqual(self.client.get(url, {"sort": "invalid"}).status_code, 400)
        # A retained match without current evaluation must not rank as current priority.
        from django.utils import timezone
        from datetime import timedelta

        self.device.expires_at = timezone.now() - timedelta(days=1)
        self.device.save(update_fields=["expires_at"])
        stale = self.client.get(url, {"focus": "missing"})
        self.assertTrue(all(machine.source_priority is None for machine in stale.context["page"]))

    def test_case_and_record_sort_allowlists(self):
        self.cached()
        self.prepare()
        self.login(self.reader)
        url = reverse("organization-cases", args=[self.a.slug])
        for key in ("priority", "company", "software", "platform", "manager", "machines", "identifiers"):
            response = self.client.get(url, {"sort": key, "direction": "asc"})
            self.assertEqual(response.status_code, 200)
        for key in ("record", "asset", "installation", "priority", "assessment", "decision"):
            response = self.client.get(
                url, {"view": "records", "assessment": "all", "sort": key, "direction": "desc"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page"].paginator.count, 1)
