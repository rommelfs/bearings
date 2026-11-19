"""Periodic owner confirmation is separate from proof of infrastructure authority."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .access import require
from .circl_views import private_response
from .inventory_review import (
    configure_review,
    confirm_review,
    owner_can_review,
    review_token,
    snapshot,
    can_configure_review,
    mandatory_review_mail,
)
from .models import InventoryReviewPolicy
from .registration_forms import InventoryReviewForm, InventoryReviewSettingsForm
from .views import organization


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def review(request, slug):
    org = organization(request, slug)
    policy = InventoryReviewPolicy.objects.filter(organization=org).first()
    editable = owner_can_review(request.user, org)
    configurable = can_configure_review(request.user, org)
    mandatory_email = mandatory_review_mail(org)
    error = None
    if request.method == "POST":
        if request.POST.get("action") == "settings":
            require(configurable)
            settings_form = InventoryReviewSettingsForm(
                request.POST,
                instance=policy or InventoryReviewPolicy(organization=org),
                mandatory_email=mandatory_email,
            )
            if settings_form.is_valid():
                configure_review(request.user, org, settings_form.cleaned_data)
                messages.success(request, "Review interval and service-email reminders updated.")
                return redirect("inventory-review", slug=slug)
            error = settings_form.errors
        else:
            require(editable)
            require(policy is not None)
            form = InventoryReviewForm(request.POST)
            if form.is_valid():
                try:
                    confirm_review(request.user, org, form.cleaned_data["token"])
                except ValidationError as failure:
                    error = failure.messages
                else:
                    messages.success(
                        request,
                        "Current reporting data confirmed. Scope verification and patch/applicability decisions remain separate.",
                    )
                    return redirect("inventory-review", slug=slug)
            else:
                error = form.errors
    digest, counts = snapshot(org)
    form = (
        InventoryReviewForm(initial={"token": review_token(request.user, policy, digest)})
        if policy and editable
        else None
    )
    from .review_followup import deliveries_for, delivery_label

    deliveries = list(deliveries_for(policy)[:10]) if policy else []
    for item in deliveries:
        item.display_status = delivery_label(item)
    return private_response(
        render(
            request,
            "portal/inventory_review.html",
            {
                "org": org,
                "policy": policy,
                "counts": counts,
                "editable": editable,
                "configurable": configurable,
                "mandatory_email": mandatory_email,
                "review_form": form,
                "error": error,
                "settings_form": InventoryReviewSettingsForm(
                    instance=policy or InventoryReviewPolicy(organization=org),
                    mandatory_email=mandatory_email,
                ),
                "history": policy.confirmations.select_related("actor").order_by("-reviewed_at", "-pk")[:10]
                if policy
                else [],
                "deliveries": deliveries,
            },
        )
    )
