"""Public static marketing content, distinct from the authenticated inventory workspace."""

import mimetypes
from pathlib import Path
from urllib.parse import urlsplit
from django.conf import settings
from django.http import HttpResponse, FileResponse, Http404
from django.views.decorators.http import require_safe
from website import build

ROOT = Path(build.ROOT)
FILES = {
    str(p.relative_to(ROOT / "assets")): p
    for p in (ROOT / "assets").rglob("*")
    if p.is_file() and p.suffix.lower() in {".svg", ".png", ".webp"}
}
FILES.update({name: ROOT / name for name in ["style.css", "site.js"]})


@require_safe
def page(request, lang="en", faq=False):
    if lang not in build.LANGUAGES:
        raise Http404
    configured = settings.PUBLIC_BASE_URL
    origin = urlsplit(configured)
    base = (
        configured
        if origin.scheme == "https" and origin.hostname not in {None, "localhost", "127.0.0.1", "::1"}
        else ""
    )
    response = HttpResponse(
        build.page(lang, faq, base=base, registration="/register/", login="/accounts/login/")
    )
    response["Cache-Control"] = "private, no-store" if request.COOKIES else "public, max-age=60"
    response["Content-Language"] = lang
    return response


@require_safe
def asset(request, name):
    path = FILES.get(name)
    if path is None or path.is_symlink():
        raise Http404
    response = FileResponse(
        path.open("rb"), content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response
