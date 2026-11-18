"""Public email-confirmed reporting applications and operator-only approvals."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from .access import audit, is_analyst, require
from .circl_views import private_response
from .models import InfrastructureRegistration
from .registration import (
    decide_registration,
    issue_verification,
    notify_decision,
    permit_public_attempt,
    submit_registration,
    verify_registration,
    prepare_team_verification,
)
from .registration_forms import (
    InfrastructureRegistrationForm,
    RegistrationDecisionForm,
    RegistrationVerificationForm,
    VerificationResendForm,
)


@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def register(request):
    if not settings.PUBLIC_REGISTRATION_ENABLED:
        return render(request, "portal/registration.html", {"closed": True}, status=403)
    if request.user.is_authenticated:
        return redirect("overview")
    form = InfrastructureRegistrationForm(request.POST or None)
    if request.method == "POST":
        if not permit_public_attempt(request):
            form.add_error(None, "Too many public attempts. Try again later or contact the operator.")
            return private_response(render(request, "portal/registration.html", {"form": form}, status=429))
        if form.is_valid():
            try:
                item = submit_registration(form)
            except IntegrityError:
                form.add_error(
                    None, "This account cannot be registered. Use sign-in or contact the operator."
                )
            else:
                if not issue_verification(item.pk):
                    messages.warning(
                        request,
                        "Application saved, but verification email could not be prepared. Use resend later or contact the operator.",
                    )
                return redirect("registration-sent")
    return private_response(render(request, "portal/registration.html", {"form": form}))


@never_cache
@require_http_methods(["GET"])
def sent(request):
    return private_response(render(request, "portal/registration.html", {"sent": True}))


@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def verify(request):
    form = RegistrationVerificationForm(request.POST or None)
    if request.method == "POST":
        if not permit_public_attempt(request):
            return private_response(
                render(
                    request, "portal/registration_verify.html", {"form": form, "limited": True}, status=429
                )
            )
        if form.is_valid():
            try:
                verified = verify_registration(form.cleaned_data["code"], form.cleaned_data["password1"])
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if verified:
                    team_ready = prepare_team_verification(verified)
                    return private_response(
                        render(
                            request,
                            "portal/registration_verify.html",
                            {"verified": True, "item": verified, "team_ready": team_ready},
                        )
                    )
                form.add_error(
                    None,
                    "This code is invalid, expired or already used. Resend verification or contact the operator.",
                )
    return private_response(render(request, "portal/registration_verify.html", {"form": form}))


@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def resend(request):
    form = VerificationResendForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if permit_public_attempt(request):
            item = InfrastructureRegistration.objects.filter(
                email=form.cleaned_data["email"].casefold(), status="awaiting_email"
            ).first()
            if item:
                issue_verification(item.pk)
        return private_response(render(request, "portal/registration_verify.html", {"resent": True}))
    return private_response(
        render(request, "portal/form.html", {"title": "Resend registration verification", "form": form})
    )


@login_required
@never_cache
@require_http_methods(["GET"])
def applications(request):
    require(request.user.is_superuser or is_analyst(request.user))
    audit(request.user, None, "operator.registrations_read")
    state = request.GET.get("status", "awaiting_review")
    if state not in {"awaiting_review", "awaiting_email", "approved", "rejected"}:
        state = "awaiting_review"
    page = Paginator(
        InfrastructureRegistration.objects.filter(status=state)
        .select_related("user", "organization")
        .order_by("created_at", "pk"),
        25,
    ).get_page(request.GET.get("page"))
    return private_response(render(request, "portal/registrations.html", {"page": page, "state": state}))


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def application(request, pk):
    require(request.user.is_superuser or is_analyst(request.user))
    item = get_object_or_404(
        InfrastructureRegistration.objects.select_related("user", "organization", "reviewed_by"), pk=pk
    )
    form = RegistrationDecisionForm(request.POST or None)
    if item.status == "awaiting_email":
        require(request.method == "GET")
        form = None
    elif item.status in {"approved", "rejected"}:
        form.fields["decision"].choices = [("notify", "Retry decision email")]
    if request.method == "POST" and form.is_valid():
        item = decide_registration(
            request.user, item.pk, form.cleaned_data["decision"], form.cleaned_data["note"]
        )
        delivered = notify_decision(item.pk)
        messages.success(
            request,
            "Decision saved. CIRCL sharing is separate from private owner access; scopes remain declared.",
        )
        if not delivered and item.email_verified_at and not item.decision_mail_sent_at:
            messages.warning(
                request, "Decision email was not confirmed. Check service mail and retry notification."
            )
        return redirect("registration-application", pk=item.pk)
    audit(request.user, item.organization, "operator.registration_read", item.pk)
    return private_response(
        render(request, "portal/registration_application.html", {"item": item, "form": form})
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def correct_scope(request, slug, pk):
    from django.db import transaction
    from django.utils import timezone
    from .access import can_edit
    from .forms import ClaimForm
    from .models import InfrastructureClaim
    from .views import organization

    org = organization(request, slug)
    require(can_edit(request.user, org))
    claim = get_object_or_404(InfrastructureClaim, organization=org, pk=pk)
    form = ClaimForm(request.POST or None, instance=claim)
    if request.method == "POST":
        if request.POST.get("action") == "withdraw":
            with transaction.atomic():
                current = InfrastructureClaim.objects.select_for_update().get(organization=org, pk=pk)
                current.status = "expired"
                now = timezone.now()
                if current.valid_until is None or current.valid_until > now:
                    current.valid_until = now
                current.save(update_fields=["status", "valid_until"])
                audit(request.user, org, "scope.owner_withdrew", current.pk)
            return redirect("organization", slug=slug)
        if form.is_valid():
            with transaction.atomic():
                current = InfrastructureClaim.objects.select_for_update().get(organization=org, pk=pk)
                if any(getattr(current, field) != form.cleaned_data[field] for field in form.Meta.fields):
                    old_id = current.pk
                    current.status = "expired"
                    current.valid_until = (
                        min(current.valid_until, timezone.now()) if current.valid_until else timezone.now()
                    )
                    current.save(update_fields=["status", "valid_until"])
                    replacement = InfrastructureClaim(
                        organization=org, **{field: form.cleaned_data[field] for field in form.Meta.fields}
                    )
                    replacement.full_clean()
                    replacement.save()
                    audit(request.user, org, "scope.owner_corrected", old_id, replacement=replacement.pk)
            return redirect("organization", slug=slug)
    return private_response(
        render(request, "portal/scope_correction.html", {"org": org, "claim": claim, "form": form})
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def company_address(request, slug):
    from django.db import transaction
    from .access import can_review_contact
    from .models import Organization
    from .registration_forms import CompanyAddressForm
    from .views import organization

    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    form = CompanyAddressForm(request.POST or None, instance=org)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            current = Organization.objects.select_for_update().get(pk=org.pk)
            require(can_review_contact(request.user, current))
            if current.postal_address != form.cleaned_data["postal_address"]:
                current.postal_address = form.cleaned_data["postal_address"]
                current.save(update_fields=["postal_address"])
                audit(request.user, current, "organization.address_updated", current.pk)
        return redirect("organization", slug=slug)
    return private_response(
        render(
            request,
            "portal/form.html",
            {
                "org": org,
                "title": "Update company address",
                "form": form,
            },
        )
    )
