import argparse
import errno
import io
import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
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


class StarterPrerequisiteTests(TestCase):
    def test_missing_docker_fails_before_creating_local_state(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(dev, "LOCAL", Path(directory) / "not-created"),
            patch("sys.argv", ["dev.py", "up"]),
            patch("shutil.which", return_value=None),
            patch.object(dev, "run") as run,
        ):
            with self.assertRaisesRegex(SystemExit, "Docker command not found"):
                dev.main()
            self.assertFalse(dev.LOCAL.exists())
            run.assert_not_called()

    def test_unavailable_compose_and_engine_have_actionable_errors(self):
        cases = [
            ([dev.subprocess.CalledProcessError(1, "docker")], "Compose is unavailable"),
            ([None, dev.subprocess.CalledProcessError(1, "docker")], "Engine is unreachable"),
            ([None, dev.subprocess.TimeoutExpired("docker", 15)], "Engine is unreachable"),
        ]
        for effects, message in cases:
            with self.subTest(message=message), patch("shutil.which", return_value="/bin/docker"):
                with patch.object(dev, "run", side_effect=effects):
                    with self.assertRaisesRegex(SystemExit, message):
                        dev.check_docker()


class ExchangePlacementHelperTests(TestCase):
    def test_external_mode_is_refused_before_any_command(self):
        with patch.object(dev, "run") as run:
            with self.assertRaisesMessage(SystemExit, "bundled"):
                dev.exchange_example(["docker", "compose"], "external")
            run.assert_not_called()

    def test_inventory_only_checks_identity_then_places_and_imports_without_keys_or_public_lookup(self):
        marker = str(uuid.uuid4())
        result = argparse.Namespace(stdout=marker)
        with patch.object(dev, "run", return_value=result) as run:
            dev.exchange_example(["docker", "compose"], "bundled", inventory_only=True)
        self.assertEqual(run.call_count, 3)
        self.assertIn("lab_sources", run.call_args_list[0].args[0][-1])
        self.assertIn(marker, run.call_args_list[1].kwargs["input"])
        self.assertIn("/opt/netbox/netbox/manage.py", run.call_args_list[1].args[0])
        self.assertEqual(run.call_args_list[2].args[0][-2:], ["sync_netbox", "--all"])
        self.assertFalse(any("seed_exchange_example" in c.args[0] for c in run.call_args_list))
        with patch.object(dev, "run", return_value=argparse.Namespace(stdout="invalid")) as run:
            with self.assertRaisesMessage(SystemExit, "No confirmed"):
                dev.exchange_example(["docker", "compose"], "bundled", inventory_only=True)
            self.assertEqual(run.call_count, 1)


class FlowIntelStarterTests(TestCase):
    def test_flowintel_compose_is_explicit_and_keeps_netbox_overlay(self):
        plain = dev.compose("bundled", "bearings-test")
        combined = dev.compose("bundled", "bearings-test", True)
        self.assertNotIn(str(dev.ROOT / "compose.flowintel.yaml"), plain)
        self.assertIn(str(dev.ROOT / "compose.netbox.yaml"), combined)
        self.assertEqual(combined[-1], str(dev.ROOT / "compose.flowintel.yaml"))

    def test_old_state_defaults_to_disabled_without_changing_saved_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            text = json.dumps({"mode": "bundled", "project": "retained"})
            path.write_text(text)
            with patch.object(dev, "STATE", path):
                self.assertFalse(dev.active()["flowintel"])
            self.assertEqual(path.read_text(), text)

    def test_cached_upstream_source_with_local_changes_is_not_overwritten(self):
        from scripts import flowintel_source

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".local/dev-stack/flowintel-source"
            (source / ".git").mkdir(parents=True)
            with (
                patch.object(flowintel_source, "ROOT", root),
                patch.object(
                    flowintel_source.subprocess, "run", return_value=argparse.Namespace(stdout=" M README.md")
                ) as run,
            ):
                with self.assertRaisesMessage(SystemExit, "local changes"):
                    flowintel_source.prepare_source()
                self.assertEqual(run.call_count, 1)
                self.assertNotIn("checkout", run.call_args.args[0])


class FlowIntelRuntimeDirectoryTests(SimpleTestCase):
    def test_cross_device_move_preserves_image_tree_and_runtime_data_on_repeat(self):
        from docker.flowintel.start import link_runtime_directory

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, target = root / "logs", root / "runtime"
            path.mkdir()
            (path / "nested").mkdir()
            (path / "nested/image.log").write_text("image contents")
            (path / "alias").symlink_to("nested/image.log")
            target.mkdir()
            (target / "retained.log").write_text("existing runtime contents")
            with patch("os.rename", side_effect=OSError(errno.EXDEV, "Invalid cross-device link")):
                link_runtime_directory(path, target)
            self.assertTrue(path.is_symlink())
            self.assertEqual(path.resolve(), target)
            backup = root / "logs.image-original"
            self.assertEqual((backup / "nested/image.log").read_text(), "image contents")
            self.assertTrue((backup / "alias").is_symlink())
            link_runtime_directory(path, target)
            self.assertEqual((path / "retained.log").read_text(), "existing runtime contents")
            self.assertEqual((backup / "nested/image.log").read_text(), "image contents")

    def test_existing_backup_is_preserved_without_merging_or_removing_source(self):
        from docker.flowintel.start import link_runtime_directory

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, target, backup = root / "uploads", root / "runtime", root / "uploads.image-original"
            for item in [path, target, backup]:
                item.mkdir()
            (path / "original").write_text("source")
            (backup / "retained").write_text("backup")
            with self.assertRaises(RuntimeError):
                link_runtime_directory(path, target)
            self.assertEqual((path / "original").read_text(), "source")
            self.assertEqual((backup / "retained").read_text(), "backup")

    def test_unexpected_runtime_link_is_preserved(self):
        from docker.flowintel.start import link_runtime_directory

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, target, other = root / "history", root / "runtime", root / "other"
            target.mkdir()
            other.mkdir()
            path.symlink_to(other)
            with self.assertRaises(RuntimeError):
                link_runtime_directory(path, target)
            self.assertEqual(path.resolve(), other)


class SSOStarterTests(SimpleTestCase):
    def test_optional_sso_compose_retains_both_other_profiles_and_refuses_external(self):
        plain = dev.compose("bundled", "bearings-test", True)
        combined = dev.compose("bundled", "bearings-test", True, True)
        self.assertNotIn(str(dev.ROOT / "compose.sso.yaml"), plain)
        self.assertIn(str(dev.ROOT / "compose.netbox.yaml"), combined)
        self.assertIn(str(dev.ROOT / "compose.flowintel.yaml"), combined)
        self.assertIn(str(dev.ROOT / "compose.sso.yaml"), combined)
        self.assertEqual(combined[-1], str(dev.ROOT / "compose.flowintel-sso.yaml"))
        with self.assertRaises(SystemExit):
            dev.compose("external", "bearings-test", False, True)

    def test_retained_identity_configuration_refuses_silent_port_repointing(self):
        from docker.sso.initialize import initialize

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "secrets").mkdir()
            (root / "secrets/demo_password").write_text("synthetic-password")

            def write(path, content, **kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

            def secret(path, **kwargs):
                if not path.exists():
                    write(path, str(uuid.uuid4()))
                return path.read_text().strip()

            ports = {"sso": 9444, "bearings": 8000, "netbox": 8443}
            initialize(root, write, secret, ports)
            client = json.loads((root / "secrets/oidc-bearings-client.json").read_text())
            self.assertEqual(
                client["client"]["redirectUris"],
                [
                    "https://localhost:9441/oauth/complete/oidc/",
                    "https://127.0.0.1:9441/oauth/complete/oidc/",
                ],
            )
            self.assertEqual(
                client["legacy_redirects"],
                ["http://localhost:8000/oauth/complete/oidc/", "http://127.0.0.1:8000/oauth/complete/oidc/"],
            )
            saved = (root / "secrets/oidc_client_secret").read_text()
            identity = (root / "secrets/oidc-lab.json").read_text()
            initialize(root, write, secret, ports)
            self.assertEqual((root / "secrets/oidc_client_secret").read_text(), saved)
            self.assertEqual((root / "secrets/oidc-lab.json").read_text(), identity)
            self.assertNotEqual((root / "netbox-secrets/oidc_client_secret").read_text(), saved)
            with self.assertRaises(ValueError):
                initialize(root, write, secret, {**ports, "sso": 9555})
