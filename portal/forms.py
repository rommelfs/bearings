from django import forms
from .models import Asset, Contact, InfrastructureClaim, Installation, Product, MOSPSource


class ContactForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["function"].required = False
        if self.is_bound and "function" not in self.data:
            self.data = self.data.copy()
            self.data["function"] = self.instance.function or "security"

    def clean_function(self):
        return self.cleaned_data.get("function") or self.instance.function or "security"

    class Meta:
        model = Contact
        fields = [
            "name",
            "role",
            "function",
            "email",
            "phone",
            "emergency_phone",
            "language",
            "time_zone",
            "availability",
            "secure_communication",
            "scope",
            "escalation_order",
            "notification_enabled",
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
        queryset=Product.objects.none(),
        required=False,
        label="Reuse a product already in this organization",
        help_text="This list contains your organization’s saved products, not the public CPE catalog.",
    )
    product_name = forms.CharField(max_length=180, required=False)
    product_identifier = forms.CharField(
        max_length=255,
        required=False,
        label="Product identifier / CPE (optional)",
        help_text="A CPE identifies the product; enter the installed version separately below. Example: cpe:2.3:a:misp:misp:*:*:*:*:*:*:*:*",
    )
    vendor = forms.CharField(max_length=120, required=False, widget=forms.HiddenInput)
    product_key = forms.CharField(max_length=120, required=False, widget=forms.HiddenInput)

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
            "component_type",
        ]

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["component_type"].required = False
        if organization:
            self.fields["existing_product"].queryset = Product.objects.filter(
                organization=organization
            ).order_by("name")

    def clean_component_type(self):
        return self.cleaned_data.get("component_type") or "software"

    def clean(self):
        data = super().clean()
        vendor, key = data.get("vendor", ""), data.get("product_key", "")
        if vendor or key:
            from .product_matching import valid_key, catalog_cpe

            if not valid_key(vendor) or not valid_key(key):
                raise forms.ValidationError(
                    "Choose both manufacturer and product from the public catalog, or clear the selection and enter a CPE directly."
                )
            if data.get("existing_product"):
                raise forms.ValidationError(
                    "Choose a saved organization product or a public catalog product, not both."
                )
            data["product_name"] = data.get("product_name") or key
            identifier = data.get("product_identifier", "")
            if identifier:
                parts = identifier.split(":")
                if len(parts) != 13 or parts[:3] != ["cpe", "2.3", "a"] or tuple(parts[3:5]) != (vendor, key):
                    raise forms.ValidationError(
                        "The CPE and catalog selection identify different products. Clear one selection and retry."
                    )
            else:
                data["product_identifier"] = catalog_cpe(vendor, key)
            from .models import ProductWatch

            watch = ProductWatch.objects.filter(
                product__organization=self.organization,
                product__name=data["product_name"],
                product__identifier=data["product_identifier"],
            ).first()
            if watch and (watch.vendor, watch.product_key) != (vendor, key):
                raise forms.ValidationError(
                    "This saved product already has a different monitoring identity. Review its existing mapping in Automatic CVE discovery first."
                )
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
    source = forms.ModelChoiceField(queryset=MOSPSource.objects.none(), widget=forms.HiddenInput)
    risk_uuid = forms.UUIDField(widget=forms.HiddenInput)
    reviewed_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
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


class LocalAssetForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible_contact"].queryset = Contact.objects.filter(
            organization=self.instance.organization
        ).order_by("name")

    class Meta:
        model = Asset
        fields = ["criticality", "lifecycle", "responsible_team", "responsible_contact"]


class ManualAssetForm(LocalAssetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [
            (value, label)
            for value, label in self.fields["kind"].choices
            if value not in {"ip_address", "prefix"}
        ]

    class Meta(LocalAssetForm.Meta):
        fields = ["name", "kind", *LocalAssetForm.Meta.fields]
