"""Public reporting applications and accountable inventory review."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import InfrastructureRegistration, InventoryReviewPolicy
from .scope import normalize


class InfrastructureRegistrationForm(forms.ModelForm):
    company_name = forms.CharField(max_length=180, label="Company / organization")
    contact_name = forms.CharField(max_length=180, label="Responsible person's name")
    email = forms.EmailField(label="Your email address")
    networks = forms.CharField(
        max_length=6000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One CIDR prefix or start-end IP range per line.",
    )
    ips = forms.CharField(
        max_length=6000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Individual static IP addresses",
        help_text="IPv4 or IPv6, one per line.",
    )
    domains = forms.CharField(
        max_length=6000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Domains / hostnames",
        help_text="One DNS name per line, without URL or wildcard.",
    )
    network_context = forms.CharField(
        max_length=100, required=False, label="Internal network context (optional)"
    )
    review_days = forms.IntegerField(min_value=1, max_value=365, initial=90, label="Review data every (days)")
    email_reminders = forms.BooleanField(
        required=False, initial=True, label="Email me when a data review is due"
    )
    consent = forms.BooleanField(
        label="I request CIRCL review and consent to CIRCL reading this new reporting workspace after approval"
    )
    attestation = forms.BooleanField(
        label="I am submitting these reporting details in good faith; I understand that scope authority remains unverified"
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "company_name",
            "contact_name",
            "email",
            "networks",
            "ips",
            "domains",
            "network_context",
            "review_days",
            "email_reminders",
            "consent",
            "attestation",
        ]

    def clean_email(self):
        value = self.cleaned_data["email"].casefold()
        if (
            get_user_model().objects.filter(email__iexact=value).exists()
            or InfrastructureRegistration.objects.filter(email=value).exists()
        ):
            raise forms.ValidationError(
                "This address cannot be registered again. Sign in, resend verification, or contact the operator."
            )
        return value

    def clean(self):
        data = super().clean()
        scopes = []
        for field in ["networks", "ips", "domains"]:
            for line in data.get(field, "").splitlines():
                if not line.strip():
                    continue
                kind = (
                    "domain"
                    if field == "domains"
                    else "ip"
                    if field == "ips"
                    else "network"
                    if "/" in line
                    else "range"
                )
                try:
                    value = normalize(kind, line)
                except forms.ValidationError as error:
                    self.add_error(field, error)
                    continue
                item = {"kind": kind, "value": value, "network_context": data.get("network_context", "")}
                if item not in scopes:
                    scopes.append(item)
        if not scopes:
            self.add_error(None, "Declare at least one IP range, static IP address or domain.")
        if len(scopes) > 100:
            self.add_error(None, "Submit at most 100 scope entries per application.")
        data["scopes"] = scopes
        return data


class RegistrationVerificationForm(forms.Form):
    password1 = forms.CharField(label="Choose your portal password", widget=forms.PasswordInput())
    password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput())
    requested = forms.BooleanField(label="I requested this reporting account and am setting its password")

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        if data.get("password1"):
            validate_password(data["password1"])
        return data

    code = forms.CharField(
        max_length=128,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code"}),
        label="Email verification code",
    )


class VerificationResendForm(forms.Form):
    email = forms.EmailField()


class RegistrationDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approve", "Approve CIRCL workspace access"),
            ("reject", "Reject CIRCL workspace access"),
            ("notify", "Retry decision email"),
        ]
    )
    note = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Internal review note",
    )
    checked = forms.BooleanField(
        label="I checked this application. Approval grants CIRCL visibility; owner access is separate and declared scopes remain unverified."
    )


class InventoryReviewSettingsForm(forms.ModelForm):
    interval_days = forms.IntegerField(min_value=1, max_value=365)
    reminder_days = forms.IntegerField(min_value=1, max_value=90)

    class Meta:
        model = InventoryReviewPolicy
        fields = ["interval_days", "reminder_days", "email_enabled"]


class InventoryReviewForm(forms.Form):
    token = forms.CharField(max_length=2000, widget=forms.HiddenInput())
    checked = forms.BooleanField(
        label="I reviewed the current contacts, declared IP/domain scopes, assets and software versions, including unknowns and gaps"
    )
