"""Organization contacts and declared infrastructure scope."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from .access import (
    audit,
    can_edit,
    can_operator_review,
    can_review_contact,
    organization,
    require,
)
from .forms import (
    ClaimForm,
    ClaimReviewForm,
    ContactForm,
)
from .models import (
    Contact,
    ContactToken,
    InfrastructureClaim,
)
from .services import (
    issue_contact_token,
    redeem_contact_token,
    review_contact,
)


@login_required
def create_contact(request, slug):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            contact = form.save(commit=False)
            contact.organization = org
            contact.save()
            audit(request.user, org, "contact.created", contact.pk)
        return redirect("organization", slug=slug)
    return render(request, "portal/form.html", {"form": form, "title": "Add emergency contact", "org": org})


@login_required
@require_POST
def contact_action(request, slug, pk, action):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    contact = get_object_or_404(Contact, organization=org, pk=pk)
    if action == "review":
        review_contact(request.user, contact)
        messages.success(
            request,
            "Role and details reviewed. Channel reachability and emergency availability are separate.",
        )
    elif action == "verify":
        service = contact.registration_notifications.exists()
        if service:
            try:
                sent = issue_contact_token(request.user, contact, service=True)
            except Exception:
                sent = False
                audit(request.user, org, "contact.service_verification_failed", contact.pk)
            if sent:
                messages.success(
                    request, "Team mailbox verification prepared using the configured service mail transport."
                )
            else:
                messages.warning(
                    request,
                    "Team verification was not prepared. Allow 15 minutes between requests or check service mail configuration and retry.",
                )
        else:
            issue_contact_token(request.user, contact)
            messages.success(
                request, "Verification prepared in the local development mail sink (.local/mail)."
            )
    elif action == "availability":
        contact.availability_confirmed_at = timezone.now()
        contact.save(update_fields=["availability_confirmed_at"])
        audit(request.user, org, "contact.availability_confirmed", contact.pk)
    elif action == "invalid":
        contact.invalid_delivery = True
        contact.reachable_at = None
        contact.save(update_fields=["invalid_delivery", "reachable_at"])
        audit(request.user, org, "contact.delivery_invalid", contact.pk)
    else:
        require(False)
    return redirect("organization", slug=slug)


@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def verify_contact(request):
    if request.method == "POST":
        success = redeem_contact_token(request.POST.get("token", ""))
        return render(
            request,
            "portal/verify.html",
            {
                "result": "Mailbox confirmation recorded. Contact role, emergency availability and infrastructure authority remain separate."
                if success
                else "Invalid or expired token."
            },
        )
    return render(request, "portal/verify.html")


@login_required
def create_claim(request, slug):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    form = ClaimForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            claim = form.save(commit=False)
            claim.organization = org
            claim.save()
            audit(request.user, org, "scope.declared", claim.pk)
        return redirect("organization", slug=slug)
    return render(
        request, "portal/form.html", {"form": form, "title": "Declare infrastructure scope", "org": org}
    )


@login_required
@require_POST
def claim_review(request, slug, pk):
    org = organization(request, slug)
    require(can_operator_review(request.user, org))
    claim = get_object_or_404(InfrastructureClaim, pk=pk, organization=org)
    form = ClaimReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            claim.status, claim.method = form.cleaned_data["status"], form.cleaned_data["method"]
            claim.reviewed_by, claim.reviewed_at = request.user, timezone.now()
            claim.save()
            audit(request.user, org, "scope.reviewed", claim.pk, status=claim.status, method=claim.method)
    else:
        messages.error(request, "Select a review status and describe the authority verification method.")
    return redirect("organization", slug=slug)


@login_required
def edit_contact(request, slug, pk):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    contact = get_object_or_404(Contact, organization=org, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            changed = form.changed_data
            if changed:
                contact.reviewed_at = contact.reviewed_by = contact.next_review = None
            if "email" in changed:
                contact.reachable_at = None
                ContactToken.objects.filter(contact=contact, used_at__isnull=True).update(
                    used_at=timezone.now()
                )
            if set(changed) & {"availability", "time_zone", "phone", "emergency_phone", "role", "function"}:
                contact.availability_confirmed_at = None
            form.save()
            audit(request.user, org, "contact.updated", contact.pk, fields=changed)
        return redirect("organization", slug=slug)
    return render(request, "portal/form.html", {"form": form, "title": "Update contact details", "org": org})
