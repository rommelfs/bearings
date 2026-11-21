from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .access import is_analyst, organizations_for, require, audit
from .circl_views import private_response
from .inventory_review import can_configure_review, reminder_recipients
from .models import InventoryReviewPolicy, InventoryReviewDelivery
from .review_followup import deliveries_for, delivery_label, preview_token, queue_followup, record_feedback
from .views import organization


@login_required
@never_cache
@require_http_methods(["GET"])
def center(request):
    require(request.user.is_active and (request.user.is_superuser or is_analyst(request.user)))
    policy = InventoryReviewPolicy.objects.filter(
        organization__in=organizations_for(request.user), next_due__lte=timezone.localdate()
    ).select_related("organization")
    if not request.user.is_superuser:
        policy = policy.filter(organization__operator_visibility=True)
    latest = InventoryReviewDelivery.objects.filter(
        policy=OuterRef("pk"), due_date=OuterRef("next_due")
    ).order_by("-created_at", "-pk")
    policy = policy.annotate(
        latest_status=Subquery(latest.values("status")[:1]),
        latest_outcome=Subquery(latest.values("delivery_outcome")[:1]),
    ).order_by("next_due", "pk")
    audit(request.user, None, "inventory.nonresponse_queue")
    return private_response(
        render(
            request,
            "portal/review_followups.html",
            {"page": Paginator(policy, 25).get_page(request.GET.get("page"))},
        )
    )


class RecipientForm(forms.Form):
    recipient = forms.ChoiceField(label="Eligible owner or response-team mailbox")


class DeliveryChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.recipient} · {obj.created_at:%Y-%m-%d} · #{obj.pk}"


class FeedbackForm(forms.Form):
    delivery = DeliveryChoice(queryset=InventoryReviewDelivery.objects.none())
    outcome = forms.ChoiceField(choices=[("bounced", "Bounce reported"), ("delivered", "Delivery reported")])
    note = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Delivery evidence / source (no message body or credentials)",
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def detail(request, slug):
    org = organization(request, slug)
    require(can_configure_review(request.user, org))
    policy = get_object_or_404(InventoryReviewPolicy, organization=org)
    form = RecipientForm(
        request.POST if request.method == "POST" and request.POST.get("action") == "preview" else None
    )
    form.fields["recipient"].choices = [(email, email) for email in reminder_recipients(policy)]
    feedback = FeedbackForm(
        request.POST if request.method == "POST" and request.POST.get("action") == "feedback" else None
    )
    feedback.fields["delivery"].queryset = policy.deliveries.filter(
        pk__in=policy.deliveries.filter(status="sent", transport="smtp")
        .order_by("-created_at", "-pk")
        .values("pk")[:100]
    )
    token, recipient, error = None, None, None
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "preview" and form.is_valid():
                recipient = form.cleaned_data["recipient"]
                token = preview_token(request.user, policy, recipient)
            elif action == "confirm":
                require(request.POST.get("approved") == "on")
                queue_followup(request.user, policy.pk, request.POST.get("token", ""))
                messages.success(
                    request, "Follow-up queued. Delivery rechecks current recipients and review policy."
                )
                return redirect("review-followup", slug=slug)
            elif action == "feedback" and feedback.is_valid():
                record_feedback(
                    request.user,
                    feedback.cleaned_data["delivery"].pk,
                    feedback.cleaned_data["outcome"],
                    feedback.cleaned_data["note"],
                )
                messages.success(
                    request,
                    "Delivery evidence recorded. This does not confirm a data review or emergency availability.",
                )
                return redirect("review-followup", slug=slug)
            elif action not in {"preview", "feedback"}:
                require(False)
        except ValidationError as failure:
            error = failure.messages
    rows = list(deliveries_for(policy)[:25])
    for row in rows:
        row.display_status = delivery_label(row)
    audit(request.user, org, "inventory.followup_read", policy.pk)
    return private_response(
        render(
            request,
            "portal/review_followup.html",
            {
                "org": org,
                "policy": policy,
                "form": form,
                "feedback": feedback,
                "deliveries": rows,
                "token": token,
                "recipient": recipient,
                "error": error,
            },
        )
    )
