"""Private profile authoring/export. Never executes a profile or distributes it to agents."""

import hashlib
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from .access import audit, require
from .agents import administrator
from .client_downloads import open_artifact
from .views import organization

SCHEMA = "bearings.application-probes.v1"


class ProfileForm(forms.Form):
    profile_id = forms.RegexField(
        r"^[a-z0-9][a-z0-9._-]{0,63}$", max_length=64, initial="misp-main", label="Stable profile ID"
    )
    method = forms.ChoiceField(
        choices=[
            ("misp-version-json", "MISP VERSION.json"),
            ("json-fields", "JSON fields"),
            ("file-regex", "Text file + regex"),
            ("git-tag", "Git release tags + tracked status"),
        ]
    )
    name = forms.CharField(max_length=128, required=False, initial="MISP", label="Software name")
    identifier = forms.CharField(max_length=255, required=False, label="Declared product CPE or package URL")
    path = forms.CharField(
        max_length=1024, initial="/var/www/MISP/VERSION.json", label="Local path on the monitored host"
    )
    json_fields = forms.CharField(
        max_length=1000,
        required=False,
        label="JSON field paths, comma separated",
        help_text="For example version, or major, minor, hotfix. Nested fields use release.version.",
    )
    version_pattern = forms.CharField(
        max_length=512,
        required=False,
        label="Version regex (Go/RE2, exactly one capture)",
        initial=r"^v?([0-9]+\.[0-9]+\.[0-9]+)$",
    )
    explanation = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea,
        label="Explanation for the PR proposal (optional)",
        help_text="Describe what this software is and why the selected metadata yields its version. No observed host data is included automatically.",
    )
    reference = forms.URLField(
        max_length=500,
        required=False,
        label="Public documentation reference (optional)",
        help_text="Used only in an upstream contribution template; no URL is fetched.",
    )

    def clean_path(self):
        value = self.cleaned_data["path"]
        if (
            not value.startswith("/")
            or value.startswith("//")
            or str(PurePosixPath(value)) != value
            or ".." in PurePosixPath(value).parts
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise forms.ValidationError(
                "Use a normalized absolute local file/repository path; this editor never reads that path."
            )
        return value

    def clean_reference(self):
        value = self.cleaned_data["reference"]
        if value:
            url = urlsplit(value)
            if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
                raise forms.ValidationError(
                    "Use an HTTPS public documentation URL without credentials or query parameters."
                )
        return value

    def clean(self):
        data = super().clean()
        if data.get("method") != "misp-version-json":
            if not data.get("name"):
                self.add_error("name", "Enter the software name.")
            if not data.get("version_pattern"):
                self.add_error("version_pattern", "Enter exactly one captured release version.")
            if data.get("method") == "json-fields" and not data.get("json_fields"):
                self.add_error("json_fields", "Choose the scalar JSON field paths.")
        return data

    def profile(self):
        data = self.cleaned_data
        profile = {"id": data["profile_id"], "method": data["method"], "path": data["path"]}
        if data["method"] != "misp-version-json":
            profile.update(name=data["name"], version_pattern=data["version_pattern"])
            if data.get("identifier"):
                profile["identifier"] = data["identifier"]
            if data["method"] == "json-fields":
                profile["fields"] = [part.strip() for part in data["json_fields"].split(",")]
        return profile


class ProfileValidationError(ValueError):
    field = "version_pattern"


def native_validate(config):
    """Use the published client parser, with no app collection/state/network calls."""
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if not architecture:
        raise ValueError("No native profile validator is available for this server architecture.")
    try:
        with (
            open_artifact("bearings-linux-" + architecture) as binary,
            open_artifact("SHA256SUMS") as manifest,
        ):
            info = os.fstat(binary.fileno())
            if info.st_mode & 0o6000:
                raise ValueError("Validator permissions require operator review.")
            expected = {
                line.split()[1]: line.split()[0]
                for line in manifest.read().decode("ascii").splitlines()
                if len(line.split()) == 2
            }
            if hashlib.file_digest(binary, "sha256").hexdigest() != expected.get(
                "bearings-linux-" + architecture
            ):
                raise ValueError("Published validator checksum does not match the reviewed artifacts.")
            with tempfile.TemporaryDirectory(prefix="bearings-profile-") as temporary:
                path = Path(temporary) / "profiles.json"
                path.write_text(json.dumps(config))
                path.chmod(0o600)
                result = subprocess.run(
                    [f"/proc/self/fd/{binary.fileno()}", "validate-applications", "--config", str(path)],
                    pass_fds=(binary.fileno(),),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=5,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                )
            if result.returncode:
                detail = result.stderr.decode("utf-8", errors="replace")[:1024]
                if "Go/RE2 version expression" in detail:
                    raise ProfileValidationError(
                        "Go/RE2 rejected this version regex. Lookaround and backreferences are unsupported; use one captured release version."
                    )
                if "exactly one version capture" in detail:
                    raise ProfileValidationError(
                        "The version regex must have exactly one capture group containing the release version."
                    )
                raise ValueError(
                    "The native client rejected this profile. Check canonical paths, product identity, JSON fields and a Go/RE2 regex with exactly one capture. The operator must publish a current validator after a server upgrade."
                )
            value = json.loads(result.stdout)
            if value.get("schema") != SCHEMA or value.get("profiles") != len(config["applications"]):
                raise ValueError("Unexpected native validation result.")
    except (Http404, OSError, subprocess.TimeoutExpired, UnicodeError, json.JSONDecodeError):
        raise ValueError(
            "Publish the reviewed Linux client artifacts before validating profiles. No application was probed."
        ) from None


def upstream_document(profile, reference=""):
    """Export a public template, not an actual host configuration/observation."""
    profile = dict(profile)
    method = profile["method"]
    profile["id"] = "misp-main" if method == "misp-version-json" else "example-application"
    profile["path"] = {
        "misp-version-json": "/var/www/MISP/VERSION.json",
        "json-fields": "/opt/example-application/version.json",
        "file-regex": "/opt/example-application/VERSION",
        "git-tag": "/opt/example-application",
    }[method]
    return {
        "schema": "bearings.application-profile.v1",
        "title": "MISP release manifest"
        if method == "misp-version-json"
        else profile["name"] + " version profile",
        "license": "AGPL-3.0-or-later",
        "references": [reference] if reference else [],
        "profile": profile,
    }


@login_required
@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def editor(request, slug):
    org = organization(request, slug)
    require(administrator(request.user, org))
    if request.method == "POST" and int(request.META.get("CONTENT_LENGTH") or "0") > 65536:
        return HttpResponse("Profile editor input exceeds the supported size.", status=400)
    if request.method == "POST" and request.POST.get("action", "preview") not in {
        "preview",
        "download",
        "upstream",
    }:
        return HttpResponse("Unsupported profile action.", status=400)
    form = ProfileForm(request.POST if request.method == "POST" else None)
    preview = None
    if request.method == "POST" and form.is_valid():
        config = {"schema": SCHEMA, "applications": [form.profile()]}
        try:
            native_validate(config)
        except ValueError as error:
            form.add_error(getattr(error, "field", None), str(error))
        else:
            preview = json.dumps(config, indent=2) + "\n"
            action = request.POST.get("action", "preview")
            audit(
                request.user,
                org,
                "agent.profile_authored",
                method=form.cleaned_data["method"],
                operation=action,
            )
            if action == "download":
                response = HttpResponse(preview, content_type="application/json")
                response["Content-Disposition"] = 'attachment; filename="bearings-application-probes.json"'
                response["Cache-Control"] = "private, no-store"
                response["Referrer-Policy"] = "no-referrer"
                return response
            if action == "upstream":
                document = upstream_document(form.profile(), form.cleaned_data.get("reference", ""))
                explanation = form.cleaned_data.get("explanation", "")
                archive = proposal_archive(document, explanation)
                response = HttpResponse(archive, content_type="application/zip")
                response["Content-Disposition"] = 'attachment; filename="bearings-profile-pr-proposal.zip"'
                response["Cache-Control"] = "private, no-store"
                response["Referrer-Policy"] = "no-referrer"
                return response
    response = render(
        request,
        "portal/application_profiles.html",
        {"org": org, "form": form, "preview": preview},
    )
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def proposal_archive(document, explanation=""):
    profile = document["profile"]
    software = "MISP" if profile["method"] == "misp-version-json" else profile["name"]
    methods = {
        "misp-version-json": "Reads MISP's major/minor/hotfix release file without executing PHP.",
        "json-fields": "Reads selected scalar JSON fields and normalizes exactly one version with Go/RE2.",
        "file-regex": "Reads a bounded local release file and extracts exactly one captured version with Go/RE2.",
        "git-tag": "Reads tags pointing at HEAD, the commit and tracked working-tree status; dirty or ambiguous releases are withheld.",
    }
    document = {**document, "description": explanation or methods[profile["method"]]}
    runtime = {"schema": SCHEMA, "applications": [profile]}
    text = (
        f"# Add an application version profile for {software}\n\n"
        f"## Software and purpose\n\n{software}\n\n{document['description']}\n\n"
        f"Method: {profile['method']}\n\nDeclared product identity: {profile.get('identifier', 'MISP canonical CPE' if profile['method'] == 'misp-version-json' else 'Not specified; supply an appropriate public CPE or package URL')}\n\n"
        "## Proposed change\n\nAdd the included profile recipe under clients/linux/profiles/ in Bearings. "
        "Adapt the example installation path locally. Stable profile IDs identify observations; existing manual versions require explicit ownership before updates.\n\n"
        "## Validation\n\n```sh\nbearings-linux validate-applications --config client-config.example.json\n```\n\n"
        "Validate local readability and version extraction on a disposable installation before deployment. The validator only checks syntax and does not run the profile. "
        "A release file/tag is not proof of a running deployment, application ownership or CVE applicability. Git checks cover tracked changes only.\n\n"
        "## Reference documentation\n\n"
        + ("\n".join(document["references"]) or "Add public software/version-format documentation.")
        + "\n\n"
        "## Contribution review\n\nReview software names, identifiers, regexes, explanation and references before publishing. "
        "Host paths and profile IDs were replaced with examples; no collected versions, fingerprints, device identifiers or credentials were copied. "
        "Submit through your normal Git branch/fork and pull-request workflow. Bearings has created no commit or PR. "
        "The template declares AGPL-3.0-or-later; confirm the rights to contribute it under that license.\n"
    )
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("profile.json", json.dumps(document, indent=2) + "\n")
        archive.writestr("client-config.example.json", json.dumps(runtime, indent=2) + "\n")
        archive.writestr("PR_PROPOSAL.md", text)
    return stream.getvalue()
