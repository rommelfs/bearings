"""Transient local inventory research; an inventory match is not confirmed affectedness."""

from django import forms
from .discovery import semver


class ResearchForm(forms.Form):
    product = forms.CharField(max_length=180, label="Product name or identifier")
    product_match = forms.ChoiceField(
        choices=[("contains", "Contains text"), ("exact", "Exact name or identifier")]
    )
    mode = forms.ChoiceField(
        choices=[
            ("all", "All recorded versions"),
            ("exact", "Exact version"),
            ("range", "Release SemVer range"),
        ],
        label="Version rule",
    )
    version = forms.CharField(max_length=120, required=False, strip=False, label="Exact version")
    minimum = forms.CharField(max_length=120, required=False, label="Minimum version (inclusive)")
    maximum = forms.CharField(max_length=120, required=False, label="Maximum version (exclusive)")
    bucket = forms.ChoiceField(
        choices=[
            ("matches", "Matching recorded versions"),
            ("unknown", "Unknown versions"),
            ("unsupported", "Non-comparable versions"),
        ],
        label="Show",
    )
    page = forms.IntegerField(min_value=1, max_value=100000, required=False)

    def clean(self):
        data = super().clean()
        if data.get("mode") == "exact" and not data.get("version"):
            self.add_error("version", "Enter the recorded version, including any vendor suffix.")
        if data.get("mode") == "range":
            low, high = data.get("minimum", ""), data.get("maximum", "")
            if not low and not high:
                self.add_error(None, "Supply at least one range boundary.")
            for key, value in [("minimum", low), ("maximum", high)]:
                if value and semver(value) is None:
                    self.add_error(
                        key, "Use a plain release such as 2.14.1; vendor suffixes require exact matching."
                    )
            if semver(low) is not None and semver(high) is not None and semver(low) >= semver(high):
                self.add_error(None, "The inclusive minimum must be below the exclusive maximum.")
        if data.get("bucket") == "unsupported" and data.get("mode") != "range":
            self.add_error("bucket", "Non-comparable versions apply to range searches.")
        return data
