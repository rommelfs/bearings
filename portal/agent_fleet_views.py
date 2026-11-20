"""Company administrators approve a bounded rollout once, not once per server."""

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from .agent_protocol import identifier
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_http_methods
from .access import organizations_for, require
from .circl_views import private_response
from .models import AgentFleet, InventorySource
from . import agents, agent_fleets


class FleetForm(forms.Form):
    name = forms.CharField(max_length=100, label="Rollout name")
    new_asset_kind = forms.ChoiceField(
        choices=AgentFleet._meta.get_field("new_asset_kind").choices, initial="server", label="Host type"
    )
    max_devices = forms.IntegerField(min_value=1, max_value=100000, initial=1000, label="Maximum new devices")
    hours = forms.IntegerField(min_value=1, max_value=168, initial=24, label="Valid for hours")
    acknowledged = forms.BooleanField(
        label="Authorize new self-reported hosts for this company, including hostname, configured interface IPs and software observations. Existing devices are not matched by hostname. No NetBox writes or verified ownership claims."
    )


@login_required
@never_cache
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def center(request, slug):
    org = get_object_or_404(organizations_for(request.user), slug=slug)
    require(agents.administrator(request.user, org))
    form = FleetForm(request.POST if request.POST.get("action") == "create" else None)
    token = None
    if request.method == "POST":
        if request.POST.get("action") == "revoke":
            try:
                pk = identifier(request.POST.get("fleet"))
            except (ValueError, TypeError, ValidationError):
                raise Http404 from None
            fleet = get_object_or_404(AgentFleet, pk=pk, organization=org)
            agent_fleets.revoke(request.user, org, fleet.pk)
            return redirect("agent-fleets", slug=org.slug)
        require(request.POST.get("action") == "create")
        if form.is_valid():
            data = dict(form.cleaned_data)
            data.pop("acknowledged")
            try:
                _, token = agent_fleets.create(request.user, org, **data)
            except InventorySource.DoesNotExist:
                form.add_error(None, "Configure the company's inventory source first")
            except ValidationError as error:
                form.add_error(None, error)
    return private_response(
        render(
            request,
            "portal/agent_fleets.html",
            {
                "org": org,
                "form": form,
                "fleet_token": token,
                "fleets": AgentFleet.objects.filter(organization=org).order_by("-created_at")[:50],
            },
        )
    )
