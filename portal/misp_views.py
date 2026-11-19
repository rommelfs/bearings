from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from . import misp
from .access import audit, is_analyst, require
from .circl_views import private_response
from .models import MISPInstance


def authorize(user):
    require(user.is_active and (user.is_superuser or is_analyst(user)))


@login_required
@never_cache
@require_http_methods(["GET"])
def center(request):
    authorize(request.user)
    audit(request.user, None, "misp.cache_list")
    events = misp.visible_events(request.user).order_by("-timestamp", "pk")
    return private_response(
        render(
            request,
            "portal/misp.html",
            {
                "page": Paginator(events, 25).get_page(request.GET.get("page")),
                "sources": MISPInstance.objects.all()
                if request.user.is_superuser
                else MISPInstance.objects.filter(owner=request.user),
            },
        )
    )


@login_required
@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def detail(request, pk):
    authorize(request.user)
    event = get_object_or_404(misp.visible_events(request.user).defer(None), pk=pk)
    audit(request.user, None, "misp.event_read", event.pk)
    matches, truncated = None, False
    if request.method == "POST":
        if request.POST.get("action") == "research":
            matches, truncated = misp.research(request.user, event)
            audit(request.user, None, "misp.infrastructure_research", event.pk)
        else:
            require(False)
    import json
    from urllib.parse import quote

    # Plain escaped text, never HTML/markdown and never follow a URL supplied by event contents.
    raw = json.dumps(event.payload, ensure_ascii=False, indent=2)
    return private_response(
        render(
            request,
            "portal/misp_event.html",
            {
                "event": event,
                "matches": matches,
                "truncated": truncated,
                "payload_text": raw[:50000],
                "payload_truncated": len(raw) > 50000,
                "source_url": event.source.base_url.rstrip("/")
                + "/events/view/"
                + quote(str(event.event_uuid), safe=""),
            },
        )
    )
