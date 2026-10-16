from django import forms
from .models import Asset, Contact, InfrastructureClaim, Installation, Product, MOSPSource


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "name",
            "role",
            "email",
            "phone",
            "emergency_phone",
            "language",
            "time_zone",
            "availability",
            "secure_communication",
            "scope",
            "escalation_order",
        ]


class ClaimForm(forms.ModelForm):
    class Meta:
        model = InfrastructureClaim
        fields = ["kind", "value", "network_context", "valid_from", "valid_until"]
        widgets = {
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class AssetForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [
            (value, label)
            for value, label in self.fields["kind"].choices
            if value not in {"ip_address", "prefix"}
        ]

    class Meta:
        model = Asset
        fields = ["name", "kind", "criticality", "lifecycle", "responsible_team"]


class InstallationForm(forms.ModelForm):
    existing_product = forms.ModelChoiceField(
        queryset=Product.objects.none(), required=False, label="Select an existing product"
    )
    product_name = forms.CharField(max_length=180, required=False)
    product_identifier = forms.CharField(max_length=255, required=False)

    class Meta:
        model = Installation
        fields = [
            "existing_product",
            "product_name",
            "product_identifier",
            "version",
            "edition",
            "build",
            "is_operating_system",
        ]

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["existing_product"].queryset = Product.objects.filter(
                organization=organization
            ).order_by("name")

    def clean(self):
        data = super().clean()
        if not data.get("existing_product") and not data.get("product_name"):
            raise forms.ValidationError("Select a product or enter a new product name")
        if data.get("existing_product") and (data.get("product_name") or data.get("product_identifier")):
            raise forms.ValidationError("Select an existing product or enter a new one, not both")
        return data


class FindingReviewForm(forms.Form):
    assessment = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Keep existing assessment"),
            ("potential", "Potentially affected"),
            ("affected", "Affected"),
            ("not_affected", "Not affected"),
            ("unknown", "Unknown"),
        ],
    )
    status = forms.ChoiceField(
        choices=[
            (x, x.replace("_", " ").title())
            for x in ["under_review", "confirmed", "resolved", "false_positive", "accepted_risk"]
        ]
    )
    reason = forms.CharField(max_length=4000, widget=forms.Textarea)


class ClaimReviewForm(forms.Form):
    status = forms.ChoiceField(choices=[(x, x.title()) for x in ["verified", "disputed", "expired"]])
    method = forms.CharField(max_length=200)


class VulnerabilityForm(forms.Form):
    identifier = forms.RegexField(
        regex=r"(?i)^CVE-\d{4}-\d{4,}$", max_length=40, label="CVE identifier to investigate"
    )


class MissingReviewForm(forms.Form):
    reason = forms.CharField(
        max_length=1000, widget=forms.Textarea, label="Review reason (inventory is retained)"
    )


class RiskLinkForm(forms.Form):
    source = forms.ModelChoiceField(queryset=MOSPSource.objects.none(), label="Approved MOSP catalog")
    risk_uuid = forms.UUIDField(label="MONARC risk UUID")
    reason = forms.CharField(
        max_length=4000,
        widget=forms.Textarea,
        label="Why is this scenario relevant? Describe assumptions and uncertainty.",
    )

    def __init__(self, *args, **kwargs):
        from .models import MOSPSource

        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = MOSPSource.objects.filter(enabled=True)


class RiskWithdrawalForm(forms.Form):
    reason = forms.CharField(
        max_length=4000, widget=forms.Textarea, label="Reason for withdrawing this mapping"
    )
