"""Public, fixed-name distribution of operator-built client artifacts; public artifacts and private, organization-scoped rollout controls."""

import hashlib
import os
from pathlib import Path
import stat
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache
from .access import require
from .models import Organization
from . import agent_fleet_views
from .agent_enrollment_codes import trusted_origin

ARTIFACTS = {
    "install.py": 128 * 1024,
    "bearings-linux-amd64": 64 * 1024 * 1024,
    "bearings-linux-arm64": 64 * 1024 * 1024,
    "bearings-linux.service": 16384,
    "SHA256SUMS": 16384,
    "LICENSE": 128 * 1024,
    "README.md": 128 * 1024,
    "SOURCE.txt": 16384,
    "bearings-linux-source.tar.gz": 4 * 1024 * 1024,
}

WINDOWS_PACKAGES = (
    ("x64", "64-bit Intel / AMD Windows", "bearings-windows-x64.zip"),
    ("ARM64", "Windows on ARM", "bearings-windows-arm64.zip"),
    ("x86", "32-bit Windows", "bearings-windows-x86.zip"),
)
WINDOWS_ARTIFACTS = {
    **{filename: 32 * 1024 * 1024 for _, _, filename in WINDOWS_PACKAGES},
    "bearings-windows-source.zip": 32 * 1024 * 1024,
    "SHA256SUMS": 16384,
}


def open_artifact(name):
    return _open(name, settings.LINUX_CLIENT_DOWNLOAD_DIR, ARTIFACTS)


def _open(name, directory, files):
    if name not in files or not directory or not Path(directory).is_absolute():
        raise Http404
    path = Path(directory) / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        raise Http404 from None
    file = os.fdopen(fd, "rb")
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= files[name] or info.st_mode & 0o022:
        file.close()
        raise Http404
    return file


def _complete_release(opener, files):
    try:
        for name in files:
            with opener(name):
                pass
    except Http404:
        return False
    return True


def _rollout_organizations(request):
    organizations = Organization.objects.filter(merged_into__isnull=True)
    if not request.user.is_authenticated or not request.user.is_active:
        organizations = organizations.none()
    elif not request.user.is_superuser:
        organizations = organizations.filter(membership__user=request.user, membership__role="admin")
    return organizations.order_by("name", "pk")


def rollout_navigation(request, company):
    """Only link to controls within the same scope as the administration view."""
    if not request.user.is_authenticated or not request.user.is_active:
        return {}
    organizations = _rollout_organizations(request)
    if company:
        organizations = organizations.filter(pk=company.pk)
    return {
        "client_rollout_allowed": request.user.is_superuser or organizations.exists(),
        "client_rollout_slug": company.slug if company else "",
    }


@require_GET
def platforms(request):
    return render(request, "portal/client_platforms.html")


@login_required
@never_cache
@require_GET
def administration(request, section):
    organizations = _rollout_organizations(request)
    slug = request.GET.get("organization")
    route = "agent-fleets" if section == "rollouts" else "application-profiles"
    if slug:
        return redirect(route, slug=get_object_or_404(organizations, slug=slug).slug)
    candidates = list(organizations[:2])
    if len(candidates) == 1:
        return redirect(route, slug=candidates[0].slug)
    return render(
        request,
        "portal/client_administration.html",
        {"section": section, "organizations": organizations},
    )


@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    if request.method == "POST":
        # Old Linux download forms can still be submitted after a server upgrade.
        slug = request.POST.get("organization")
        require(request.user.is_authenticated and bool(slug))
        require(_rollout_organizations(request).filter(slug=slug).exists())
        return agent_fleet_views.center(request, slug)
    return render(
        request,
        "portal/client_downloads.html",
        {
            "ready": _complete_release(open_artifact, ARTIFACTS),
            "origin": settings.PUBLIC_BASE_URL or request.build_absolute_uri("/").rstrip("/"),
        },
    )


@require_GET
def artifact(request, name):
    return _download(open_artifact, name)


def _open_windows(name):
    return _open(name, settings.WINDOWS_CLIENT_DOWNLOAD_DIR, WINDOWS_ARTIFACTS)


@never_cache
@require_GET
def windows(request):
    if request.GET.get("setup") == "windows":
        org = get_object_or_404(_rollout_organizations(request), slug=request.GET.get("organization", ""))
        return redirect("agent-fleets", slug=org.slug)
    ready = _complete_release(_open_windows, WINDOWS_ARTIFACTS)
    try:
        server = trusted_origin()
    except (ValidationError, ValueError):
        server = request.build_absolute_uri("/").rstrip("/") if request.is_secure() else ""
    commands = []
    if ready and server:
        for architecture, _, filename in WINDOWS_PACKAGES:
            url = (server + reverse("windows-client-artifact", args=[filename])).replace("'", "''")
            commands.append((architecture, f"Invoke-WebRequest -Uri '{url}' -OutFile '{filename}'"))
        manifest = (server + reverse("windows-client-artifact", args=["SHA256SUMS"])).replace("'", "''")
        commands.append(("SHA256SUMS", f"Invoke-WebRequest -Uri '{manifest}' -OutFile 'SHA256SUMS'"))
    return render(
        request,
        "portal/windows_client_downloads.html",
        {
            "ready": ready,
            "packages": WINDOWS_PACKAGES,
            "download_commands": commands,
        },
    )


@require_GET
def windows_artifact(request, name):
    if name not in WINDOWS_ARTIFACTS or not _complete_release(_open_windows, WINDOWS_ARTIFACTS):
        raise Http404
    return _download(_open_windows, name)


def _download(opener, name):
    file = opener(name)
    try:
        if name != "SHA256SUMS":
            with opener("SHA256SUMS") as manifest:
                entries = {}
                for line in manifest.read().decode("ascii").splitlines():
                    digest, filename = line.split()
                    if len(digest) != 64 or filename in entries:
                        raise ValueError
                    entries[filename] = digest
            actual = hashlib.file_digest(file, "sha256").hexdigest()
            if entries.get(name) != actual:
                raise Http404
            file.seek(0)
        response = FileResponse(
            file, as_attachment=True, filename=name, content_type="application/octet-stream"
        )
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except (ValueError, UnicodeError, OSError):
        file.close()
        raise Http404 from None
    except Http404:
        file.close()
        raise
