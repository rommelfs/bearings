"""Authoring/export uses a parser-only native validator and never deploys profiles."""

import hashlib
import json
import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from zipfile import ZipFile
from django.test import Client, override_settings
from .tests import Fixture
from .models import AgentComponent, AgentReport
from .application_profile_views import native_validate


def values(**extra):
    return {
        "profile_id": "customer-prod-misp",
        "method": "misp-version-json",
        "name": "MISP",
        "path": "/srv/customer-prod/MISP/VERSION.json",
        "explanation": "Read the public MISP release manifest; do not execute PHP.",
        "reference": "https://github.com/MISP/MISP/blob/2.5/VERSION.json",
        **extra,
    }


class EditorTests(Fixture):
    def setUp(self):
        self.login()
        self.endpoint = self.url("application-profiles")

    def test_admin_only_scoped_csrf_guards_precede_native_execution(self):
        self.login(self.reader)
        with patch("portal.application_profile_views.native_validate") as run:
            self.assertEqual(self.client.get(self.endpoint).status_code, 403)
            self.assertEqual(self.client.post(self.endpoint, values()).status_code, 403)
            self.assertEqual(self.client.get(self.url("application-profiles", self.b)).status_code, 404)
            csrf = Client(enforce_csrf_checks=True)
            csrf.force_login(self.admin)
            self.assertEqual(csrf.post(self.endpoint, values()).status_code, 403)
            run.assert_not_called()

    def test_private_config_download_is_structured_and_does_not_create_observations(self):
        with patch("portal.application_profile_views.native_validate") as run:
            response = self.client.post(self.endpoint, values(action="download"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        config = json.loads(response.content)
        self.assertEqual(config["applications"][0]["path"], "/srv/customer-prod/MISP/VERSION.json")
        self.assertEqual(config["applications"][0]["id"], "customer-prod-misp")
        run.assert_called_once_with(config)
        self.assertFalse(AgentComponent.objects.exists())
        self.assertFalse(AgentReport.objects.exists())
        self.assertIn("no-store", response["Cache-Control"])
        directory = os.environ.get("BEARINGS_PROFILE_EDITOR_UI_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "config.json").write_bytes(response.content)

    def test_pr_proposal_contains_recipe_software_and_explanation_with_example_paths(self):
        with patch("portal.application_profile_views.native_validate"):
            response = self.client.post(self.endpoint, values(action="upstream"))
        self.assertEqual(response["Content-Type"], "application/zip")
        directory = os.environ.get("BEARINGS_PROFILE_EDITOR_UI_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "proposal.zip").write_bytes(response.content)
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(
                set(archive.namelist()), {"profile.json", "client-config.example.json", "PR_PROPOSAL.md"}
            )
            document = json.loads(archive.read("profile.json"))
            proposal = archive.read("PR_PROPOSAL.md").decode()
            combined = "\n".join(archive.read(name).decode() for name in archive.namelist())
        self.assertNotIn("customer-prod", combined)
        self.assertNotIn("/srv/", combined)
        self.assertEqual(document["profile"]["path"], "/var/www/MISP/VERSION.json")
        self.assertIn("MISP", proposal)
        self.assertIn("do not execute PHP", proposal)
        self.assertIn("Bearings has created no commit or PR", proposal)
        self.assertIn("validate-applications", proposal)

    def test_invalid_structure_and_unavailable_native_parser_do_not_export_unvalidated_profiles(self):
        with patch("portal.application_profile_views.native_validate") as run:
            for extra in [
                {"path": "../private"},
                {"method": "shell"},
                {"method": "json-fields", "name": "App", "json_fields": ""},
                {"reference": "https://user:password@example.invalid/x"},
            ]:
                response = self.client.post(self.endpoint, values(action="download", **extra))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("attachment", response.get("Content-Disposition", ""))
            run.assert_not_called()
        with patch(
            "portal.application_profile_views.native_validate", side_effect=ValueError("Parser unavailable")
        ):
            response = self.client.post(self.endpoint, values(action="upstream"))
        self.assertContains(response, "Parser unavailable")
        self.assertNotEqual(response["Content-Type"], "application/zip")

    def test_json_fields_preview_and_no_github_configuration_upload(self):
        with patch("portal.application_profile_views.native_validate") as run:
            response = self.client.post(
                self.endpoint,
                values(
                    method="json-fields",
                    profile_id="example",
                    name="Example",
                    path="/opt/example/release.json",
                    json_fields="release.major, release.minor, release.patch",
                    version_pattern=r"^([0-9]+\.[0-9]+\.[0-9]+)$",
                ),
            )
        self.assertContains(response, "Validated client configuration")
        self.assertEqual(
            run.call_args.args[0]["applications"][0]["fields"],
            ["release.major", "release.minor", "release.patch"],
        )
        self.assertNotContains(response, "github.com/rommelfs/bearings/new")
        self.assertContains(response, "Nothing is sent to GitHub")
        directory = os.environ.get("BEARINGS_PROFILE_EDITOR_UI_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "editor.html").write_bytes(response.content)


@skipUnless(os.environ.get("BEARINGS_PROFILE_VALIDATOR"), "Native artifact acceptance is opt-in")
class NativeValidatorTests(Fixture):
    def test_actual_re2_validation_checks_syntax_without_accessing_application_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = "bearings-linux-amd64"
            shutil.copyfile(os.environ["BEARINGS_PROFILE_VALIDATOR"], root / name)
            (root / name).chmod(0o755)
            digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
            (root / "SHA256SUMS").write_text(digest + "  " + name + "\n")
            (root / "SHA256SUMS").chmod(0o644)
            config = {
                "schema": "bearings.application-probes.v1",
                "applications": [
                    {
                        "id": "not-run",
                        "method": "git-tag",
                        "name": "Not Run",
                        "path": "/nonexistent/application/repository",
                        "version_pattern": r"^v([0-9.]+)$",
                    }
                ],
            }
            with (
                override_settings(LINUX_CLIENT_DOWNLOAD_DIR=root),
                patch("platform.machine", return_value="x86_64"),
            ):
                native_validate(config)
                config["applications"][0]["version_pattern"] = "(?=a)(.*)"
                with self.assertRaisesMessage(ValueError, "rejected"):
                    native_validate(config)
                (root / "SHA256SUMS").write_text("0" * 64 + "  " + name + "\n")
                with self.assertRaisesMessage(ValueError, "checksum"):
                    native_validate(config)
