"""Operator-only map data and explicit address-bound manual positioning."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .access import audit, require
from .circl_map import company_location, map_data
from .circl_views import authorize, private_response
from .geography import address_digest
from .inventory_review import can_configure_review
from .models import Organization, OrganizationLocation
from .overview_queries import overview_queries
from .views import organization

SALT = "company-map-address/v1"


class LocationForm(forms.Form):
    latitude = forms.DecimalField(min_value=-90, max_value=90, max_digits=9, decimal_places=6)
    longitude = forms.DecimalField(min_value=-180, max_value=180, max_digits=9, decimal_places=6)
    token = forms.CharField(max_length=2000, widget=forms.HiddenInput())


@login_required
@never_cache
@require_GET
def data(request):
    authorize(request, "operator.national_map")
    with overview_queries(planning_limit=4) as database:
        payload = map_data(request.user)
    response = private_response(JsonResponse(payload))
    response["Server-Timing"] = (
        f"mapdatabase;dur={database.seconds * 1000:.1f}, dbmax;dur={database.slowest * 1000:.1f}"
    )
    return response


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def location(request, slug):
    authorize(request, "operator.company_map_location")
    org = organization(request, slug)
    require(can_configure_review(request.user, org))
    current = company_location(org)
    token = signing.dumps({"org": org.pk, "address": address_digest(org.postal_address)}, salt=SALT)
    form = LocationForm(
        request.POST or None,
        initial={
            **(
                {"latitude": round(current["lat"], 6), "longitude": round(current["lon"], 6)}
                if current
                else {}
            ),
            "token": token,
        },
    )
    if request.method == "POST" and (request.POST.get("action") == "clear" or form.is_valid()):
        with transaction.atomic():
            locked = Organization.objects.select_for_update().get(pk=org.pk)
            require(can_configure_review(request.user, locked))
            try:
                proof = signing.loads(request.POST.get("token", ""), salt=SALT, max_age=3600)
            except signing.BadSignature:
                proof = None
            if proof != {"org": org.pk, "address": address_digest(locked.postal_address)}:
                form.add_error(
                    None, "Address changed or form expired. Reload before positioning this company."
                )
            else:
                if request.POST.get("action") == "clear":
                    OrganizationLocation.objects.filter(organization=locked).delete()
                    action = "cleared"
                else:
                    OrganizationLocation.objects.update_or_create(
                        organization=locked,
                        defaults={
                            "latitude": form.cleaned_data["latitude"],
                            "longitude": form.cleaned_data["longitude"],
                            "address_digest": address_digest(locked.postal_address),
                            "updated_by": request.user,
                        },
                    )
                    action = "positioned"
                audit(request.user, locked, "organization.map_" + action, locked.pk)
                messages.success(
                    request,
                    "Company map location updated. This does not verify its address or infrastructure authority.",
                )
                return redirect("circl-map-location", slug=slug)
    return private_response(
        render(request, "portal/circl_map_location.html", {"org": org, "form": form, "current": current})
    )
