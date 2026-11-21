"""Platform-only local service-mail inspection; never reads SMTP mailboxes or arbitrary paths."""

import hashlib
import heapq
from email import policy
from email.parser import BytesHeaderParser
from pathlib import Path
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET
from .access import audit, require
from .circl_views import private_response


def local_messages():
    root = Path(settings.EMAIL_FILE_PATH).resolve()
    if not root.is_dir():
        return []
    candidates = (
        p for p in root.glob("*.log") if not p.is_symlink() and p.is_file() and p.resolve().parent == root
    )
    return heapq.nlargest(200, candidates, key=lambda p: p.name)


@login_required
@never_cache
@require_GET
@sensitive_variables()
def outbox(request, key=None):
    require(request.user.is_active and request.user.is_superuser)
    local = settings.SERVICE_MAIL_TRANSPORT == "file"
    rows, contents = [], None
    if local:
        for path in local_messages():
            opaque = hashlib.sha256(path.name.encode()).hexdigest()
            with path.open("rb") as handle:
                headers = BytesHeaderParser(policy=policy.default).parsebytes(handle.read(8192))
            rows.append(
                {
                    "key": opaque,
                    "name": path.name,
                    "recipient": str(headers.get("To", ""))[:1000],
                    "subject": str(headers.get("Subject", ""))[:1000],
                }
            )
            if key == opaque:
                # Bounded UTF-8 text, escaped by the template. No filesystem or SMTP write.
                with path.open("rb") as handle:
                    contents = handle.read(256001)
                if len(contents) > 256000:
                    contents = contents[:256000] + b"\n[Message preview truncated]"
                contents = contents.decode("utf-8", errors="replace")
        if key and contents is None:
            raise Http404()
    elif key:
        raise Http404()
    audit(
        request.user, None, "operator.local_mail_read" if key else "operator.service_mail_status", key or ""
    )
    response = private_response(
        render(
            request,
            "portal/service_mail_outbox.html",
            {
                "local_mail": local,
                "rows": rows,
                "contents": contents,
                "smtp_configured": bool(settings.EMAIL_HOST),
            },
        )
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
