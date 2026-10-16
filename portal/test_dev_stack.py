import argparse
import io
import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from scripts import dev
from .connectors.http import ConnectorError, validate_base
from .models import Asset, InventoryWrite, Membership, NetBoxInstance, Organization, Product


@override_settings(DEBUG=True)
class StackSetupTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.password = self.root / "password"
        self.password.write_text("synthetic-test-password")
        self.path = self.root / "config.json"
        self.config = {
            "mode": "external",
            "connections": [
                {
                    "name": "external-test",
                    "organization_slug": "external-test",
                    "organization_name": "External test",
                    "base_url": "https://netbox.example.invalid",
                    "token_env_var": "NETBOX_TEST_TOKEN",
                    "auth_scheme": "Bearer",
                    "access_mode": "read_only",
                    "allow_private": False,
                    "tenant_id": 7,
                }
            ],
        }
        env = patch.dict("os.environ", {"BEARINGS_DEV_STACK": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.probe = patch(
            "portal.management.commands.setup_dev_stack.query_inventory",
            return_value={"devices": [], "virtual-machines": []},
        ).start()
        self.addCleanup(patch.stopall)

    def setup(self):
        self.path.write_text(json.dumps(self.config))
        call_command(
            "setup_dev_stack",
            config=str(self.path),
            password_file=str(self.password),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    @override_settings(DEBUG=False)
    def test_initializer_refuses_non_development_environment(self):
        with self.assertRaises(CommandError):
            self.setup()
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_repeatable_setup_preserves_passwords_memberships_and_disabled_policy(self):
        self.setup()
        admin = get_user_model().objects.get(username="platform-admin")
        self.assertTrue(admin.is_superuser and admin.check_password("synthetic-test-password"))
        admin.set_password("locally-changed-password")
        admin.save()
        Product.objects.create(
            organization=Organization.objects.get(slug="example-labs"),
            name="Apache Log4j",
            identifier="different-user-supplied-identity",
        )
        instance = NetBoxInstance.objects.get(name="external-test")
        instance.enabled = False
        instance.save()
        org = Organization.objects.get(slug="external-test")
        membership = Membership.objects.get(organization=org)
        membership.delete()
        self.setup()
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("locally-changed-password"))
        self.assertEqual(NetBoxInstance.objects.count(), 1)
        self.assertFalse(NetBoxInstance.objects.get().enabled)
        self.assertFalse(Membership.objects.filter(organization=org).exists())
        self.assertEqual(InventoryWrite.objects.filter(asset__organization=org).count(), 0)

    def test_external_connection_never_creates_assets_or_write_jobs(self):
        self.setup()
        org = Organization.objects.get(slug="external-test")
        self.assertEqual(org.inventory_source.mode, "external")
        self.assertFalse(org.operator_visibility)
        self.assertFalse(org.inventory_source.can_write)
        self.assertEqual(org.assets.count(), 0)
        self.assertFalse(InventoryWrite.objects.filter(asset__organization=org).exists())

    def test_external_outage_allows_local_portal_setup(self):
        self.probe.side_effect = ConnectorError("Upstream HTTP 403; no data removed")
        self.setup()
        self.assertTrue(Organization.objects.filter(slug="external-test").exists())
        self.assertTrue(get_user_model().objects.filter(username="platform-admin").exists())

    def test_bundled_bootstrap_requires_live_seed_identity_confirmation(self):
        self.config["mode"] = "bundled"
        self.config["connections"][0]["assets"] = [
            {"id": str(uuid.uuid4()), "external_id": "1", "object_type": "dcim.device", "kind": "server"}
        ]
        with self.assertRaises(CommandError):
            self.setup()
        self.assertFalse(Organization.objects.filter(slug="external-test").exists())

    def test_confirmed_seed_projection_retains_platform_metadata_on_repeat(self):
        self.config["mode"] = "bundled"
        key = str(uuid.uuid4())
        self.config["connections"][0]["assets"] = [
            {"id": key, "external_id": "1", "object_type": "dcim.device", "kind": "server"}
        ]
        self.probe.return_value = {
            "devices": [
                {
                    "external_id": "1",
                    "record": {"name": "synthetic-seed", "custom_fields": {"bearings_id": key}},
                }
            ],
            "virtual-machines": [],
        }
        self.setup()
        asset = Asset.objects.get(pk=key)
        asset.responsible_team = "locally reviewed team"
        asset.save()
        self.setup()
        asset.refresh_from_db()
        self.assertEqual(asset.responsible_team, "locally reviewed team")
        self.assertEqual(asset.installations.count(), 1)
        self.assertFalse(InventoryWrite.objects.filter(asset=asset).exists())

    def test_existing_endpoint_is_not_silently_repointed(self):
        self.setup()
        self.config["connections"][0]["base_url"] = "https://replacement.example.invalid"
        with self.assertRaises(CommandError):
            self.setup()
        self.assertEqual(
            NetBoxInstance.objects.get(name="external-test").base_url, "https://netbox.example.invalid"
        )

    def test_smoke_refuses_a_reconfigured_database_connection_before_http(self):
        from docker.dev.smoke import lab_sources

        self.config["mode"] = "bundled"
        item = self.config["connections"][0]
        item["base_url"] = "https://netbox.bearings.test"
        self.setup()
        instance = NetBoxInstance.objects.get(name=item["name"])
        instance.base_url = "https://operator-replacement.example.invalid"
        instance.save()
        with patch("httpx.Client") as client, self.assertRaisesRegex(RuntimeError, "connection changed"):
            lab_sources(self.config)
        client.assert_not_called()


class StarterConfigurationTests(TestCase):
    def arguments(self, url="https://netbox.example.invalid:8443"):
        return argparse.Namespace(
            url=url,
            tenant_id=7,
            dedicated=False,
            token_file=None,
            ca_file=None,
            access_mode="read_only",
            auth_scheme="Bearer",
            allow_private=False,
            site_id=None,
            role_id=None,
            device_type_id=None,
        )

    def test_external_token_stays_private_and_is_not_printed(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(dev, "LOCAL", Path(directory)),
            patch("getpass.getpass", return_value="synthetic-token"),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            dev.configure(self.arguments("HTTPS://NETBOX.Example.Invalid:8443/"))
            token = Path(directory) / "external/token"
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
            config = json.loads((Path(directory) / "external/connection.json").read_text())
            self.assertEqual(config["access_mode"], "read_only")
            self.assertEqual(config["base_url"], "https://netbox.example.invalid:8443")
            self.assertNotIn("synthetic-token", output.getvalue())
            self.assertNotIn("synthetic-token", json.dumps(config))
            self.assertTrue(config["token_env_var"].startswith("NETBOX_EXTERNAL_"))

    def test_external_endpoints_have_distinct_credential_references(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(dev, "LOCAL", Path(directory)),
            patch("getpass.getpass", return_value="synthetic-token"),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            dev.configure(self.arguments())
            first = json.loads((Path(directory) / "external/connection.json").read_text())
            dev.configure(self.arguments("https://second.example.invalid"))
            second = json.loads((Path(directory) / "external/connection.json").read_text())
            self.assertNotEqual(first["token_env_var"], second["token_env_var"])
            self.assertNotEqual(first["name"], second["name"])

    def test_urls_with_credentials_and_invalid_ports_are_rejected(self):
        for url in [
            "http://netbox.example.invalid",
            "https://user:password@netbox.example.invalid",
            "https://netbox.example.invalid:0",
            "https://netbox.example.invalid:65536",
        ]:
            with self.subTest(url=url), self.assertRaises(SystemExit):
                dev.configure(self.arguments(url))
            with self.subTest(connector=url), self.assertRaises(ConnectorError):
                validate_base(url)
        self.assertEqual(validate_base("https://netbox.example.invalid:8443").port, 8443)
