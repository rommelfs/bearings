from django import forms
from .models import Asset, AssetIssue, Installation, MOSPRisk
from .access import can_operator_review
from .issues import FACT_FIELDS


class InstallationChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.asset.name} / {obj.product.name} / {obj.version or 'unknown version'}"


class IssueForm(forms.ModelForm):
    reason = forms.CharField(
        max_length=4000, widget=forms.Textarea(attrs={"rows": 2}), label="Reason / evidence for this change"
    )
    installation = InstallationChoice(queryset=Installation.objects.none(), required=False)

    class Meta:
        model = AssetIssue
        fields = ["asset", "installation", *FACT_FIELDS]
        widgets = {
            **{
                field: forms.DateInput(attrs={"type": "date"})
                for field in ["event_date", "action_due", "valid_from", "valid_until"]
            },
            "observed_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            **{
                field: forms.Textarea(attrs={"rows": 3})
                for field in ["evidence_text", "consequence", "next_action"]
            },
        }

    def __init__(self, *args, organization, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        self.fields["asset"].queryset = Asset.objects.filter(
            organization=organization, source__organization=organization
        ).order_by("name")
        self.fields["installation"].queryset = (
            Installation.objects.filter(asset__organization=organization, product__organization=organization)
            .select_related("asset", "product")
            .order_by("asset__name", "product__name")
        )
        self.fields["kind"].choices = [choice for choice in AssetIssue.KINDS if choice[0] != "vulnerability"]
        if not can_operator_review(actor, organization):
            self.fields.pop("operator_only")
        if self.instance.pk and not self.instance._state.adding:
            self.fields.pop("asset")
            self.fields.pop("installation")
            self.fields.pop("kind")
            if self.instance.finding_id:
                for field in [
                    "status",
                    "shareable",
                    "source_label",
                    "source_url",
                    "observed_at",
                    "evidence_text",
                    "fact_status",
                    "valid_from",
                    "valid_until",
                    "event_date",
                    "fact_scope",
                    "contract_reference",
                ]:
                    self.fields.pop(field, None)


class RiskForm(forms.Form):
    risk = forms.ModelChoiceField(queryset=MOSPRisk.objects.none())
    reason = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["risk"].queryset = (
            MOSPRisk.objects.filter(
                source__enabled=True, missing_since__isnull=True, current_revision__isnull=False
            )
            .select_related("source", "current_revision")
            .order_by("description")
        )
