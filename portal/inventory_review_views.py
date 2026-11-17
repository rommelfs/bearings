"""Periodic owner confirmation is separate from proof of infrastructure authority."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .access import require
from .circl_views import private_response
from .inventory_review import configure_review, confirm_review, owner_can_review, review_token, snapshot
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
    error = None
    if request.method == "POST":
        require(editable)
        if request.POST.get("action") == "settings":
            settings_form = InventoryReviewSettingsForm(
                request.POST, instance=policy or InventoryReviewPolicy(organization=org)
            )
            if settings_form.is_valid():
                configure_review(request.user, org, settings_form.cleaned_data)
                messages.success(request, "Review interval and service-email reminders updated.")
                return redirect("inventory-review", slug=slug)
            error = settings_form.errors
        else:
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
    return private_response(
        render(
            request,
            "portal/inventory_review.html",
            {
                "org": org,
                "policy": policy,
                "counts": counts,
                "editable": editable,
                "review_form": form,
                "error": error,
                "settings_form": InventoryReviewSettingsForm(
                    instance=policy or InventoryReviewPolicy(organization=org)
                ),
                "history": policy.confirmations.select_related("actor").order_by("-reviewed_at", "-pk")[:10]
                if policy
                else [],
                "deliveries": policy.deliveries.order_by("-created_at", "-pk")[:10] if policy else [],
            },
        )
    )
