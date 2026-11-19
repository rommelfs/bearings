from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from . import misp
from .access import ANALYST_GROUP, audit, is_analyst, require
from .circl_views import private_response
from .models import MISPInstance


class ReaderForm(forms.Form):
    expected_digest = forms.RegexField(regex=r"^[a-f0-9]{64}$", widget=forms.HiddenInput)
    readers = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        label="Authorized CIRCL recipients for this exact revision",
    )
    note = forms.CharField(
        max_length=1000, widget=forms.Textarea, label="Recipient and handling justification"
    )
    acknowledged = forms.BooleanField(
        label="I checked the event and all nested restrictions, including TLP and sharing groups, for these recipients. This grants no company-facing redistribution."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["readers"].queryset = (
            get_user_model().objects.filter(is_active=True, groups__name=ANALYST_GROUP).distinct()
        )


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
                "sources": MISPInstance.objects.all() if request.user.is_superuser else [],
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
    form = (
        ReaderForm(
            request.POST if request.method == "POST" and request.POST.get("action") == "grant" else None,
            initial={"expected_digest": event.digest},
        )
        if request.user.is_superuser
        else None
    )
    matches, truncated = None, False
    if request.method == "POST":
        if request.POST.get("action") == "grant":
            require(request.user.is_superuser)
            if form.is_valid():
                try:
                    misp.grant_readers(
                        request.user,
                        event.pk,
                        list(form.cleaned_data["readers"]),
                        form.cleaned_data["note"],
                        expected_digest=form.cleaned_data["expected_digest"],
                    )
                except ValidationError as error:
                    form.add_error(None, error)
                else:
                    return redirect("misp-event", pk=event.pk)
        elif request.POST.get("action") == "research":
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
                "reader_form": form,
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
