"""Public, fixed-name distribution of operator-built client artifacts; public artifacts and private, organization-scoped rollout controls."""

import hashlib
import os
from pathlib import Path
import stat
from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache
from .access import organizations_for, require
from . import agent_fleet_views

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


def open_artifact(name):
    directory = settings.LINUX_CLIENT_DOWNLOAD_DIR
    if name not in ARTIFACTS or not directory or not Path(directory).is_absolute():
        raise Http404
    path = Path(directory) / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        raise Http404 from None
    file = os.fdopen(fd, "rb")
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= ARTIFACTS[name] or info.st_mode & 0o022:
        file.close()
        raise Http404
    return file


def page_context(request):
    ready = True
    try:
        for name in ARTIFACTS:
            with open_artifact(name):
                pass
    except Http404:
        ready = False
    organizations = organizations_for(request.user)
    if not request.user.is_authenticated or not request.user.is_active:
        organizations = organizations.none()
    elif not request.user.is_superuser:
        organizations = organizations.filter(membership__user=request.user, membership__role="admin")
    return {
        "ready": ready,
        "origin": settings.PUBLIC_BASE_URL or request.build_absolute_uri("/").rstrip("/"),
        "rollout_organizations": organizations.order_by("name", "pk"),
        "downloads_page": True,
    }


@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    context = page_context(request)
    slug = request.POST.get("organization") if request.method == "POST" else request.GET.get("organization")
    if request.method == "POST":
        require(request.user.is_authenticated and bool(slug))
    if not slug and context["rollout_organizations"].count() == 1:
        slug = context["rollout_organizations"].first().slug
    if slug:
        require(context["rollout_organizations"].filter(slug=slug).exists())
        return agent_fleet_views.center(request, slug, downloads_page=True)
    return render(request, "portal/client_downloads.html", context)


@require_GET
def artifact(request, name):
    file = open_artifact(name)
    try:
        if name != "SHA256SUMS":
            with open_artifact("SHA256SUMS") as manifest:
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
