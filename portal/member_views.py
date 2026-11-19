from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UsernameField
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods
from .access import require, audit
from .circl_views import private_response
from .company_members import admin, invite, accept, change_member
from .models import Organization, OrganizationInvitation, Membership
from .registration import permit_public_attempt


class InvitationForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Membership.ROLES, initial="reader")


class AcceptForm(forms.Form):
    code = forms.CharField(max_length=128, widget=forms.PasswordInput(attrs={"autocomplete": "off"}))
    username = UsernameField(max_length=150, required=False, validators=[UnicodeUsernameValidator()])
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(
        label="Choose your password (new accounts only)", required=False, widget=forms.PasswordInput()
    )
    password2 = forms.CharField(label="Repeat password", required=False, widget=forms.PasswordInput())
    confirmed = forms.BooleanField(label="I accept this invitation to join the organization")

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "Passwords do not match")
        return data


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def members(request, slug):
    org = get_object_or_404(Organization, slug=slug)
    require(admin(request.user, org) and not org.merged_into_id)
    form = InvitationForm(request.POST if request.POST.get("action") == "invite" else None)
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "invite" and form.is_valid():
                item = invite(request.user, org, **form.cleaned_data)
                messages.warning(
                    request, "Invitation saved, but mail preparation failed. Send a new invitation later."
                ) if item.mail_error else messages.success(
                    request, "Invitation email prepared. Local mail mode does not send externally."
                )
                return redirect("company-members", slug=slug)
            elif action == "revoke":
                with transaction.atomic():
                    Organization.objects.select_for_update().get(pk=org.pk)
                    require(admin(request.user, org))
                    item = get_object_or_404(
                        OrganizationInvitation, pk=request.POST.get("invitation"), organization=org
                    )
                    item.revoked_at = timezone.now()
                    item.save(update_fields=["revoked_at"])
                    audit(request.user, org, "membership.invitation_revoked", item.pk)
                return redirect("company-members", slug=slug)
            elif action == "member":
                item = get_object_or_404(Membership, pk=request.POST.get("member"), organization=org)
                change_member(request.user, org, item.pk, request.POST.get("role"))
                return redirect("company-members", slug=slug)
            elif action != "invite":
                require(False)
        except (ValidationError, ValueError) as error:
            form.add_error(None, error if isinstance(error, ValidationError) else "Invalid selection")
    return private_response(
        render(
            request,
            "portal/company_members.html",
            {
                "org": org,
                "form": form,
                "members": org.membership_set.select_related("user").order_by("user__username"),
                "invitations": org.organizationinvitation_set.order_by("-created_at")[:50],
                "roles": Membership.ROLES,
                "now": timezone.now(),
            },
        )
    )


@never_cache
@sensitive_post_parameters()
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def join(request):
    form = AcceptForm(request.POST or None)
    if request.user.is_authenticated:
        for field in ("username", "first_name", "last_name", "password1", "password2"):
            form.fields.pop(field)
    if request.method == "POST":
        if not permit_public_attempt(request):
            form.add_error(None, "Too many attempts. Try again later.")
        elif form.is_valid():
            data = form.cleaned_data
            try:
                org = accept(
                    request.user,
                    data["code"],
                    username=data.get("username", ""),
                    first_name=data.get("first_name", ""),
                    last_name=data.get("last_name", ""),
                    password=data.get("password1", ""),
                )
            except ValidationError as error:
                form.add_error(None, error)
            except IntegrityError:
                form.add_error(None, "This account cannot be created. Sign in or choose another username.")
            else:
                return private_response(render(request, "portal/company_join.html", {"joined": org}))
    response = private_response(render(request, "portal/company_join.html", {"form": form}))
    return response


class MergeForm(forms.Form):
    source = forms.ModelChoiceField(
        queryset=Organization.objects.filter(merged_into=None), label="Source company to archive"
    )
    target = forms.ModelChoiceField(
        queryset=Organization.objects.filter(merged_into=None), label="Company to keep"
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def merge_companies(request):
    from .company_merge import plan, merge

    require(request.user.is_active and request.user.is_superuser)
    form = MergeForm(request.POST if request.POST.get("action") == "preview" else None)
    preview = None
    if request.method == "POST":
        try:
            if request.POST.get("action") == "commit":
                require(request.POST.get("confirmed") == "yes")
                target = merge(request.user, request.POST.get("ticket", ""))
                messages.success(
                    request,
                    "Company merged. Source is archived; review the resulting company data and contacts.",
                )
                return redirect("organization", slug=target.slug)
            require(request.POST.get("action") == "preview")
            if form.is_valid():
                preview = plan(request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        except IntegrityError:
            form.add_error(
                None,
                "A data identity conflict prevented the merge. Nothing was transferred; reconcile the conflict and preview again.",
            )
    return private_response(render(request, "portal/company_merge.html", {"form": form, "preview": preview}))
