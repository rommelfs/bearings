"""Public downloads expose only complete approved artifacts; enrollment codes remain scoped/private."""

import base64
import hashlib
import json
from io import StringIO
from pathlib import Path
import tempfile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from .tests import Fixture
from .models import AgentEnrollment


class ClientDownloadTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = override_settings(LINUX_CLIENT_DOWNLOAD_DIR=str(self.root))
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        (self.root / "install.py").write_bytes(b"# synthetic installer\n")
        digest = hashlib.sha256((self.root / "install.py").read_bytes()).hexdigest()
        (self.root / "SHA256SUMS").write_text(digest + "  install.py\n")

    def test_anonymous_verified_artifact_and_unknown_or_mismatched_refusal(self):
        response = self.client.get("/downloads/linux/install.py")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"# synthetic installer\n")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.client.get("/downloads/linux/config.json").status_code, 404)
        (self.root / "install.py").write_bytes(b"changed")
        self.assertEqual(self.client.get("/downloads/linux/install.py").status_code, 404)

    def test_disabled_symlink_and_writable_artifacts_are_not_published(self):
        path = self.root / "install.py"
        path.chmod(0o666)
        self.assertEqual(self.client.get("/downloads/linux/install.py").status_code, 404)
        path.unlink()
        path.symlink_to(self.root / "SHA256SUMS")
        self.assertEqual(self.client.get("/downloads/linux/install.py").status_code, 404)
        with override_settings(LINUX_CLIENT_DOWNLOAD_DIR=""):
            self.assertEqual(self.client.get("/downloads/linux/SHA256SUMS").status_code, 404)
        self.assertContains(self.client.get("/downloads/linux/"), "not published a complete client build")


@override_settings(PUBLIC_BASE_URL="https://testserver")
class EnrollmentCodeTests(Fixture):
    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        self.public = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()

    def test_browser_creates_private_key_bound_copy_code_without_file_transfer(self):
        self.login()
        response = self.client.post(
            "/organizations/alpha/agents/",
            {
                "action": "enroll",
                "asset": str(self.asset.pk),
                "public_key": self.public,
                "acknowledged": "on",
                "delivery": "code",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("Content-Disposition", response)
        code = response.context["code"].split(".", 1)[1]
        payload = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)))
        self.assertEqual(payload["public_key"], self.public)
        self.assertEqual(payload["asset_id"], str(self.asset.pk))
        self.assertEqual(payload["url"], "https://testserver")
        grant = AgentEnrollment.objects.get()
        self.assertNotEqual(grant.token_hash, payload["grant"])
        self.assertContains(response, "enroll --code")

    def test_rollout_issuer_reuses_role_and_company_checks(self):
        output = StringIO()
        call_command(
            "issue_agent_enrollment",
            organization=self.a.slug,
            actor=self.admin.username,
            public_key=self.public,
            asset=str(self.asset.pk),
            stdout=output,
        )
        self.assertTrue(output.getvalue().startswith("bearings-enroll-v1."))
        count = AgentEnrollment.objects.count()
        with self.assertRaises(CommandError):
            call_command(
                "issue_agent_enrollment",
                organization=self.b.slug,
                actor=self.admin.username,
                public_key=self.public,
                asset=str(self.other.pk),
                stdout=StringIO(),
            )
        self.assertEqual(AgentEnrollment.objects.count(), count)
        with self.assertRaises(CommandError):
            call_command(
                "issue_agent_enrollment",
                organization=self.a.slug,
                actor=self.analyst.username,
                public_key=self.public,
                asset=str(self.asset.pk),
                stdout=StringIO(),
            )
        self.assertEqual(AgentEnrollment.objects.count(), count)


@override_settings(PUBLIC_BASE_URL="https://testserver")
class DownloadRolloutTests(Fixture):
    path = "/downloads/linux/"

    def create(self, organization="alpha", client=None):
        return (client or self.client).post(
            self.path,
            {
                "organization": organization,
                "action": "create",
                "name": "Download rollout",
                "new_asset_kind": "server",
                "max_devices": 2,
                "hours": 24,
                "acknowledged": "on",
            },
        )

    def test_public_page_contains_login_but_no_private_rollouts(self):
        self.assertContains(self.client.get(self.path), "Sign in to create a rollout key")
        self.assertEqual(self.create().status_code, 403)

    def test_admin_creates_once_and_reload_does_not_recover_secret(self):
        from .models import AgentFleet

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.path), "Create limited rollout key")
        response = self.create()
        self.assertEqual(response.status_code, 200)
        token = response.context["fleet_token"]
        self.assertTrue(token)
        self.assertContains(response, token)
        self.assertIn("no-store", response["Cache-Control"])
        fleet = AgentFleet.objects.get()
        self.assertEqual(fleet.organization_id, self.a.pk)
        self.assertNotEqual(fleet.token_hash, token.split(".", 1)[1])
        self.assertNotContains(self.client.get(self.path), token)
        response = self.client.post(
            self.path, {"action": "revoke", "organization": "alpha", "fleet": fleet.pk}
        )
        self.assertRedirects(response, self.path + "?organization=alpha")
        fleet.refresh_from_db()
        self.assertFalse(fleet.enabled)

    def test_foreign_company_reader_editor_and_analyst_cannot_create(self):
        from .models import AgentFleet

        for user in (self.admin, self.reader, self.editor, self.analyst):
            self.client.force_login(user)
            self.assertEqual(self.create("beta").status_code, 403)
            if user != self.admin:
                self.assertNotContains(self.client.get(self.path), "Create limited rollout key")
                self.assertEqual(self.create().status_code, 403)
        self.assertFalse(AgentFleet.objects.exists())

    def test_platform_must_select_and_csrf_is_required(self):
        from django.test import Client

        self.client.force_login(self.platform)
        self.assertContains(self.client.get(self.path), "Show rollout controls")
        self.assertNotContains(self.client.get(self.path), "Create limited rollout key")
        self.assertContains(self.client.get(self.path + "?organization=beta"), "Create limited rollout key")
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        self.assertEqual(self.create(client=strict).status_code, 403)
