"""Synthetic contracts for instance separation, bounded reads, and capability enforcement."""

import io
import uuid
from unittest.mock import patch
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command, CommandError
from django.contrib.auth.models import Permission
from django.utils import timezone
from .tests import Fixture
from .connectors.http import ConnectorError
from .connectors.netbox import query_objects, write_asset
from .forms import AssetForm
from .models import Asset, AuditEvent, InventorySource, InventoryWrite, Membership, NetBoxInstance
from .services import process_write, query_inventory, submit_asset


class MultiInstanceTests(Fixture):
    def setUp(self):
        env = patch.dict(
            "os.environ", {"NETBOX_ALPHA_TOKEN": "synthetic-alpha", "NETBOX_BETA_TOKEN": "synthetic-beta"}
        )
        env.start()
        self.addCleanup(env.stop)
        approved = patch(
            "portal.connectors.netbox.approved_base", side_effect=lambda url, private=False: url.rstrip("/")
        )
        approved.start()
        self.addCleanup(approved.stop)
        self.alpha = NetBoxInstance.objects.create(
            name="Alpha RO", base_url="https://alpha.example.invalid", token_env_var="NETBOX_ALPHA_TOKEN"
        )
        self.beta = NetBoxInstance.objects.create(
            name="Beta RW",
            base_url="https://beta.example.invalid",
            token_env_var="NETBOX_BETA_TOKEN",
            access_mode="read_write",
            auth_scheme="Token",
            site_id=201,
            role_id=202,
            device_type_id=203,
        )
        for source, instance, tenant, mode in [
            (self.sa, self.alpha, 7, "central"),
            (self.sb, self.beta, 9, "external"),
        ]:
            source.mode, source.instance, source.tenant_id = mode, instance, tenant
            source.save()
        self.asset.refresh_from_db()
        self.other.refresh_from_db()

    def row(self, pk=1, tenant=7):
        return {"id": pk, "name": "synthetic confidential name", "tenant": {"id": tenant}}

    def page(self, rows, count=None, next_url=None):
        return {"count": len(rows) if count is None else count, "results": rows, "next": next_url}

    @patch("portal.connectors.netbox.request_json")
    def test_instances_keep_credentials_and_identity_separate(self, request):
        request.side_effect = [self.page([self.row()]), self.page([self.row(tenant=9)])]
        first = query_objects(self.sa)
        second = query_objects(self.sb)
        self.assertEqual(first[0]["external_id"], second[0]["external_id"])
        self.assertNotEqual(first[0]["instance_id"], second[0]["instance_id"])
        self.assertNotEqual(first[0]["source_id"], second[0]["source_id"])
        calls = request.call_args_list
        self.assertEqual(calls[0].args, ("GET", "https://alpha.example.invalid/api/dcim/devices/"))
        self.assertEqual(calls[0].kwargs["headers"]["Authorization"], "Bearer synthetic-alpha")
        self.assertEqual(calls[0].kwargs["params"]["tenant_id"], 7)
        self.assertEqual(calls[1].kwargs["headers"]["Authorization"], "Token synthetic-beta")
        self.assertEqual(calls[1].kwargs["params"]["tenant_id"], 9)
        self.assertTrue(all(c.args[0] == "GET" for c in calls))

    @patch("portal.connectors.netbox.request_json")
    def test_complete_pagination_reconstructs_scoped_requests(self, request):
        request.side_effect = [
            self.page(
                [self.row()],
                2,
                "https://alpha.example.invalid/api/dcim/devices/?tenant_id=7&limit=100&offset=1",
            ),
            self.page([self.row(2)], 2),
        ]
        rows = query_objects(self.sa)
        self.assertEqual(len(rows), 2)
        self.assertEqual(request.call_args.kwargs["params"], {"tenant_id": 7, "limit": 100, "offset": 1})
        self.assertEqual(request.call_args.args[1], "https://alpha.example.invalid/api/dcim/devices/")

    @patch("portal.connectors.netbox.request_json")
    def test_untrusted_continuations_never_receive_credentials(self, request):
        for url in [
            "https://evil.example.invalid/api/dcim/devices/?tenant_id=7&limit=100&offset=1",
            "https://alpha.example.invalid/api/dcim/devices/?tenant_id=9&limit=100&offset=1",
            "https://alpha.example.invalid/api/dcim/devices/?tenant_id=7&limit=100&offset=0",
            "https://alpha.example.invalid/api/ipam/prefixes/?tenant_id=7&limit=100&offset=1",
            "https://[invalid",
        ]:
            with self.subTest(url=url):
                request.reset_mock()
                request.return_value = self.page([self.row()], 2, url)
                with self.assertRaises(ConnectorError):
                    query_objects(self.sa)
                self.assertEqual(request.call_count, 1)

    @patch("portal.connectors.netbox.request_json")
    def test_partial_or_wrong_tenant_pages_fail_closed(self, request):
        for response in [
            self.page([self.row()], 2),
            self.page([self.row(tenant=9)]),
            {"count": 0, "results": []},
            self.page([], 10001),
        ]:
            with self.subTest(response=response):
                request.return_value = response
                with self.assertRaises(ConnectorError):
                    query_objects(self.sa)

    @patch("portal.connectors.netbox.request_json")
    def test_duplicate_page_identities_are_rejected(self, request):
        request.side_effect = [
            self.page(
                [self.row()],
                2,
                "https://alpha.example.invalid/api/dcim/devices/?tenant_id=7&limit=100&offset=1",
            ),
            self.page([self.row()], 2),
        ]
        with self.assertRaises(ConnectorError):
            query_objects(self.sa)

    @patch("portal.connectors.netbox.request_json")
    def test_query_failure_retains_inventory_and_last_success(self, request):
        previous = timezone.now() - timedelta(days=1)
        self.sa.last_read_success = previous
        self.sa.save()
        request.side_effect = ConnectorError("Upstream HTTP 403; no data removed")
        with self.assertRaises(ConnectorError):
            query_inventory(self.sa, ["devices"])
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.last_read_success, previous)
        self.assertIn("403", self.sa.read_error)
        self.assertEqual(self.a.assets.count(), 1)
        self.assertEqual(self.asset.installations.count(), 1)
        request.side_effect = None
        request.return_value = self.page([])
        query_inventory(self.sa, ["devices"])
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.read_error, "")
        self.assertGreater(self.sa.last_read_success, previous)
        self.assertEqual(self.a.assets.count(), 1)  # successful empty query is not deletion/import

    @patch("portal.connectors.netbox.request_json")
    def test_read_only_blocks_connector_service_and_portal_writes(self, request):
        with self.assertRaises(ConnectorError):
            write_asset(self.asset)
        form = AssetForm(
            {"name": "blocked", "kind": "server", "criticality": "normal", "lifecycle": "active"}
        )
        self.assertTrue(form.is_valid())
        with self.assertRaises(PermissionDenied):
            submit_asset(self.admin, self.a, form)
        self.login()
        self.assertEqual(self.client.post(self.url("create-asset"), form.data).status_code, 403)
        self.assertNotContains(self.client.get(self.url("organization")), self.url("create-asset"))
        self.assertContains(
            self.client.get(self.url("organization")), self.url("create-installation", pk=self.asset.pk)
        )
        self.assertFalse(Asset.objects.filter(name="blocked").exists())
        self.assertEqual(InventoryWrite.objects.count(), 0)
        request.assert_not_called()

    def test_read_write_does_not_override_membership(self):
        form = AssetForm(
            {"name": "blocked-reader", "kind": "server", "criticality": "normal", "lifecycle": "active"}
        )
        self.assertTrue(form.is_valid())
        with self.assertRaises(PermissionDenied):
            submit_asset(self.reader, self.b, form)
        Membership.objects.create(user=self.reader, organization=self.b, role="reader")
        self.login(self.reader)
        self.assertEqual(self.client.post(self.url("create-asset", self.b), form.data).status_code, 403)
        self.assertEqual(InventoryWrite.objects.count(), 0)

    @patch("portal.connectors.netbox.request_json")
    def test_queued_write_is_blocked_after_permission_downgrade(self, request):
        job = InventoryWrite.objects.create(asset=self.other)
        NetBoxInstance.objects.filter(pk=self.beta.pk).update(access_mode="read_only")
        process_write(job.pk)
        self.other.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(self.other.state, "failed")
        self.assertIsNone(job.completed_at)
        self.assertTrue(job.error)
        request.assert_not_called()

    @patch("portal.connectors.netbox.request_json")
    def test_connector_checks_current_capability_despite_cached_instance(self, request):
        _ = self.other.source.instance  # populate relation cache before revocation
        NetBoxInstance.objects.filter(pk=self.beta.pk).update(enabled=False)
        with self.assertRaises(ConnectorError):
            write_asset(self.other)
        request.assert_not_called()

    @patch("portal.connectors.netbox.request_json")
    def test_read_write_uses_its_own_defaults_and_key(self, request):
        record = {**self.row(42, 9), "custom_fields": {"bearings_id": str(self.other.pk)}}
        request.side_effect = [self.page([]), record]
        self.assertEqual(write_asset(self.other), ("dcim.device", "42"))
        self.assertEqual(request.call_args.args, ("POST", "https://beta.example.invalid/api/dcim/devices/"))
        body = request.call_args.kwargs["json"]
        self.assertEqual(
            (body["site"], body["role"], body["device_type"], body["tenant"]), (201, 202, 203, 9)
        )
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Token synthetic-beta")

    @patch("portal.connectors.netbox.request_json")
    def test_shared_instance_requires_tenant_filter(self, request):
        self.sa.tenant_id = None
        with self.assertRaises(ConnectorError):
            query_objects(self.sa)
        request.assert_not_called()

    @patch("portal.connectors.netbox.request_json")
    def test_dedicated_instance_all_inventory_needs_explicit_owner(self, request):
        self.alpha.organization = self.a
        self.alpha.save()
        self.sa.tenant_id = None
        request.return_value = self.page([{"id": 1, "tenant": None}])
        self.assertEqual(len(query_objects(self.sa)), 1)
        self.assertNotIn("tenant_id", request.call_args.kwargs["params"])
        self.sa.tenant_id = 0
        with self.assertRaises(ConnectorError):
            query_objects(self.sa)
        self.sb.instance = self.alpha
        with self.assertRaises(ConnectorError):
            query_objects(self.sb)
        self.assertEqual(request.call_count, 1)

    @patch("portal.connectors.netbox.request_json")
    def test_missing_or_invalid_key_reference_never_falls_back_to_another_key(self, request):
        for ref in ["NETBOX_UNSET_TOKEN", "OTHER_TEST_TOKEN"]:
            NetBoxInstance.objects.filter(pk=self.alpha.pk).update(token_env_var=ref)
            with self.assertRaises(ConnectorError):
                query_objects(self.sa)
        request.assert_not_called()

    @patch("portal.connectors.netbox.request_json")
    def test_operator_command_continues_other_sources_after_one_failure(self, request):
        def response(method, url, **kwargs):
            if "alpha." in url:
                raise ConnectorError("Upstream HTTP 403; no data removed")
            return self.page([self.row(tenant=9)])

        request.side_effect = response
        stdout, stderr = io.StringIO(), io.StringIO()
        with self.assertRaises(CommandError):
            call_command("query_netbox", all=True, stdout=stdout, stderr=stderr)
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("synthetic confidential name", stdout.getvalue())
        self.sb.refresh_from_db()
        self.sa.refresh_from_db()
        self.assertIsNotNone(self.sb.last_read_success)
        self.assertIsNone(self.sa.last_read_success)
        self.assertTrue(self.sa.read_error)
        self.assertTrue(AuditEvent.objects.filter(organization=self.b, action="inventory.queried").exists())

    @patch("portal.connectors.netbox.request_json")
    def test_selected_sources_and_object_types_only(self, request):
        request.return_value = self.page([])
        call_command(
            "query_netbox",
            source=[self.sa.pk],
            object_type=["virtual-machines", "ip-addresses", "prefixes"],
            stdout=io.StringIO(),
        )
        self.assertEqual(
            [c.args[1] for c in request.call_args_list],
            [
                "https://alpha.example.invalid/api/virtualization/virtual-machines/",
                "https://alpha.example.invalid/api/ipam/ip-addresses/",
                "https://alpha.example.invalid/api/ipam/prefixes/",
            ],
        )
        self.assertTrue(all(c.args[0] == "GET" for c in request.call_args_list))
        with self.assertRaises(CommandError):
            call_command("query_netbox", source=[uuid.uuid4()], stdout=io.StringIO())
        self.assertEqual(request.call_count, 3)

    def test_instance_endpoint_and_ownership_are_immutable_when_bound(self):
        for field, value in [("base_url", "https://replacement.example.invalid"), ("organization", self.b)]:
            self.alpha.refresh_from_db()
            setattr(self.alpha, field, value)
            with self.assertRaises(ValidationError):
                self.alpha.full_clean()

    def test_operator_capability_change_is_audited(self):
        self.login(self.platform)
        response = self.client.post(
            f"/admin/portal/netboxinstance/{self.alpha.pk}/change/",
            {
                "name": self.alpha.name,
                "base_url": self.alpha.base_url,
                "token_env_var": self.alpha.token_env_var,
                "access_mode": "read_write",
                "auth_scheme": "Bearer",
                "enabled": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(action="operator.configuration_changed", target=str(self.alpha.pk))
        self.assertEqual(event.details["previous_access_mode"], "read_only")
        self.assertEqual(event.details["access_mode"], "read_write")
        self.assertEqual(event.details["previous_enabled"], True)
        self.assertIn("access_mode", event.details["fields"])

    def test_staff_member_cannot_edit_instance_configuration(self):
        self.admin.is_staff = True
        self.admin.save()
        self.admin.user_permissions.add(*Permission.objects.filter(content_type__model="netboxinstance"))
        self.login()
        self.assertEqual(
            self.client.post(
                f"/admin/portal/netboxinstance/{self.alpha.pk}/change/", {"access_mode": "read_write"}
            ).status_code,
            403,
        )

    def test_legacy_unbound_sources_fail_closed_until_operator_configures_instance(self):
        InventorySource.objects.filter(pk=self.sa.pk).update(instance=None)
        self.sa.refresh_from_db()
        self.assertFalse(self.sa.can_write)
        with self.assertRaises(ConnectorError):
            query_objects(self.sa)
        self.sa.instance = self.alpha
        self.sa.full_clean()  # initial explicit binding of a legacy source is allowed
        self.assertEqual(self.a.assets.count(), 1)
