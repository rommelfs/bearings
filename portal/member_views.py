from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UsernameField
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods
from .access import require, audit
from .circl_views import private_response
from .company_members import admin, invite, accept, change_member
from .models import Organization, OrganizationInvitation, Membership
from . import domain_membership
from .registration import permit_public_attempt


def report_operation_error(form, error):
    """Action POSTs do not necessarily bind the separate create/preview form."""
    if form.is_bound:
        form.add_error(None, error)
        return ""
    return " ".join(error.messages) if isinstance(error, ValidationError) else str(error)


class InvitationForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Membership.ROLES, initial="reader")


class DomainCodeForm(forms.Form):
    domain = forms.CharField(
        max_length=253, help_text="Exact email domain, e.g. circl.lu. Subdomains are separate."
    )
    role = forms.ChoiceField(choices=[("reader", "Reader"), ("editor", "Inventory editor")], initial="reader")
    days = forms.IntegerField(min_value=1, max_value=90, initial=30, label="Valid for days")
    max_acceptances = forms.IntegerField(min_value=1, max_value=10000, initial=100)


class DomainJoinForm(forms.Form):
    code = forms.CharField(max_length=128, widget=forms.PasswordInput(attrs={"autocomplete": "off"}))
    email = forms.EmailField(label="Your company email address")


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
@sensitive_post_parameters()
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def members(request, slug):
    org = get_object_or_404(Organization, slug=slug)
    require(admin(request.user, org) and not org.merged_into_id)
    form = InvitationForm(request.POST if request.POST.get("action") == "invite" else None)
    domain_form = DomainCodeForm(
        request.POST if request.POST.get("action") == "domain-create" else None, prefix="domain"
    )
    created_code = ""
    operation_error = ""
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "domain-create":
                if domain_form.is_valid():
                    _, created_code = domain_membership.create(request.user, org, **domain_form.cleaned_data)
            elif action == "domain-revoke":
                domain_membership.revoke(request.user, org, request.POST.get("domain_code"))
                return redirect("company-members", slug=slug)
            elif action == "invite" and form.is_valid():
                item = invite(request.user, org, **form.cleaned_data)
                messages.warning(
                    request,
                    "Invitation saved, but email submission failed. Check service mail before sending a new invitation.",
                ) if item.mail_error else messages.success(
                    request,
                    "Invitation submitted to the configured SMTP relay; delivery is not yet confirmed."
                    if settings.SERVICE_MAIL_TRANSPORT == "smtp"
                    else "Invitation saved in the local outbox; no external email was sent.",
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
            operation_error = report_operation_error(
                domain_form if request.POST.get("action") == "domain-create" else form,
                error if isinstance(error, ValidationError) else "Invalid selection",
            )
    return private_response(
        render(
            request,
            "portal/company_members.html",
            {
                "org": org,
                "form": form,
                "domain_form": domain_form,
                "created_code": created_code,
                "domain_codes": org.organizationdomaincode_set.order_by("-created_at")[:50],
                "operation_error": operation_error,
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


@never_cache
@sensitive_post_parameters()
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def join_domain(request):
    form = DomainJoinForm(request.POST or None)
    sent = False
    if request.method == "POST":
        if not permit_public_attempt(request):
            form.add_error(None, "Too many attempts. Try again later.")
        elif form.is_valid():
            try:
                domain_membership.request_invitation(**form.cleaned_data)
            except ValidationError:
                pass  # No public distinction between unavailable code/domain, cooldown or quota.
            sent = True
    return private_response(render(request, "portal/company_domain_join.html", {"form": form, "sent": sent}))


class MergeCompanyChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        source = getattr(obj, "inventory_source", None)
        inventory = source.get_mode_display() if source else "No inventory source"
        return f"{obj.display_label} · {inventory}"


class MergeForm(forms.Form):
    source = MergeCompanyChoice(
        queryset=Organization.objects.filter(merged_into=None)
        .select_related("inventory_source")
        .order_by("name", "pk"),
        label="Source company to archive",
    )
    target = MergeCompanyChoice(
        queryset=Organization.objects.filter(merged_into=None)
        .select_related("inventory_source")
        .order_by("name", "pk"),
        label="Company to keep",
    )
    retire_personal_misp = forms.BooleanField(
        required=False,
        label="Disable the archived company's personal MISP connections. Keep keys and cached history on the archive; each owner reconnects under the company we keep.",
    )

    def __init__(self, *args, query="", **kwargs):
        super().__init__(*args, **kwargs)
        base = Organization.objects.filter(merged_into=None)
        matches = base
        query = query[:160].strip()
        if query:
            criteria = Q(name__icontains=query) | Q(slug__icontains=query)
            if query.isascii() and query.isdigit() and len(query) <= 19:
                criteria |= Q(pk=int(query))
            matches = matches.filter(criteria)
        selected = []
        for name in ["source", "target"]:
            value = str(self.data.get(name, ""))
            if value.isascii() and value.isdigit() and len(value) <= 19:
                selected.append(int(value))
        choices = (
            base.filter(Q(pk__in=matches.order_by("name", "pk").values("pk")[:50]) | Q(pk__in=selected))
            .select_related("inventory_source")
            .order_by("name", "pk")
        )
        self.fields["source"].queryset = self.fields["target"].queryset = choices


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def merge_companies(request):
    from .company_merge import plan, merge

    require(request.user.is_active and request.user.is_superuser)
    query = request.GET.get("q", "")[:160].strip()
    form = MergeForm(request.POST if request.POST.get("action") == "preview" else None, query=query)
    preview = None
    operation_error = ""
    if request.method == "POST":
        try:
            if request.POST.get("action") == "commit":
                require(request.POST.get("confirmed") == "yes")
                target = merge(request.user, request.POST.get("ticket", ""))
                from .workspace_views import SESSION_COMPANY

                request.session[SESSION_COMPANY] = target.pk
                messages.success(
                    request,
                    "Company merged. Source is archived; review the resulting company data and contacts.",
                )
                return redirect("organization", slug=target.slug)
            require(request.POST.get("action") == "preview")
            if form.is_valid():
                preview = plan(request.user, **form.cleaned_data)
        except ValidationError as error:
            operation_error = report_operation_error(form, error)
        except IntegrityError:
            operation_error = report_operation_error(
                form,
                "A data identity conflict prevented the merge. Nothing was transferred; reconcile the conflict and preview again.",
            )
    return private_response(
        render(
            request,
            "portal/company_merge.html",
            {"form": form, "preview": preview, "merge_query": query, "operation_error": operation_error},
        )
    )
