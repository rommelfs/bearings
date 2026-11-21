from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.urls import reverse
from urllib.parse import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods
from .access import require
from .circl_views import private_response
from .connectors.http import ConnectorError
from .models import Organization, MISPServer, MISPInstance
from .misp_customer import connect, disconnect
from .misp_credentials import encryption_ready


class ServerChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} · {obj.base_url}"


class ConnectionForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), label="Your company")
    server = ServerChoice(queryset=MISPServer.objects.none(), label="Approved MISP server")
    api_key = forms.CharField(
        max_length=4096,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Your personal MISP read-only API key",
    )
    consent = forms.BooleanField(
        label="This is my own MISP key with my permissions. Store it encrypted for my personal connection; do not use a CIRCL key on my behalf."
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        companies = Organization.objects.filter(membership__user=actor, merged_into__isnull=True).distinct()
        self.fields["organization"].queryset = companies
        self.fields["server"].queryset = MISPServer.objects.filter(enabled=True)
        if companies.count() == 1:
            self.fields["organization"].initial = companies.first()
        servers = self.fields["server"].queryset
        if servers.count() == 1:
            self.fields["server"].initial = servers.first()


@login_required
@never_cache
@sensitive_post_parameters()
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def connections(request):
    require(request.user.is_active)
    form = ConnectionForm(
        request.POST if request.method == "POST" and request.POST.get("action") == "connect" else None,
        actor=request.user,
    )
    if not encryption_ready():
        form.fields["api_key"].disabled = True
    if request.method == "POST":
        if request.POST.get("action") == "disconnect":
            identity = request.POST.get("source", "")
            if (
                not identity.isascii()
                or not identity.isdigit()
                or len(identity) > 19
                or not 0 < int(identity) < 2**63
            ):
                raise Http404
            source = get_object_or_404(
                MISPInstance,
                pk=int(identity),
                owner=request.user,
                organization__isnull=False,
            )
            disconnect(request.user, source.pk)
            messages.success(
                request,
                "Personal MISP connection disabled and its encrypted key removed. Other users’ connections are unchanged.",
            )
            return redirect("misp-connections")
        if request.POST.get("action") != "connect":
            require(False)
        if form.is_valid():
            try:
                connect(
                    request.user,
                    form.cleaned_data["organization"],
                    form.cleaned_data["server"],
                    form.cleaned_data["api_key"].strip(),
                )
            except ConnectorError:
                form.add_error(
                    None,
                    "Personal MISP key could not be verified. Check its server, account and read permissions; no CIRCL key was substituted.",
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    "Personal MISP connection saved. Its private cache will be refreshed in the background using only your key.",
                )
                return redirect("misp")
    sources = (
        MISPInstance.objects.filter(owner=request.user, organization__membership__user=request.user)
        .select_related("organization", "server")
        .distinct()
    )
    revoked = (
        MISPInstance.objects.filter(owner=request.user, organization__isnull=False)
        .exclude(organization__membership__user=request.user)
        .only("pk")
    )
    return private_response(
        render(
            request,
            "portal/misp_connections.html",
            {
                "form": form,
                "sources": sources,
                "revoked_sources": revoked,
                "encryption_ready": encryption_ready(),
                "has_company_membership": form.fields["organization"].queryset.exists(),
                "my_memberships_url": reverse("admin:portal_membership_changelist")
                + "?"
                + urlencode({"user__id__exact": request.user.pk})
                if request.user.is_superuser
                else "",
                "add_my_membership_url": reverse("admin:portal_membership_add")
                + "?"
                + urlencode({"user": request.user.pk})
                if request.user.is_superuser
                else "",
            },
        )
    )
