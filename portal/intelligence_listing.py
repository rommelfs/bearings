"""Filters and grouped result pages for organization Intelligence."""

from django import forms
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q

from .models import Finding
from .review_cases import CVE_ID, case_identity
from .review_work import AFFECTED_CVE, REVIEW_SCOPES

VIEWS = {"cve": "By CVE", "machine": "By machine", "software": "By software"}
UBUNTU_PRIORITIES = ("negligible", "low", "medium", "high", "critical")
FILTER_SCOPE = ("asset", "product", "installation", "attention", "changed", "return_to")


class IntelligenceFilters(forms.Form):
    q = forms.CharField(required=False, max_length=160, label="CVE, machine or software")
    cvss_min = forms.DecimalField(
        required=False, min_value=0, max_value=10, max_digits=6, decimal_places=4, label="Minimum CVSS"
    )
    ubuntu_above = forms.ChoiceField(
        required=False,
        label="Ubuntu priority above",
        choices=[("", "Any priority"), *((key, key.title()) for key in UBUNTU_PRIORITIES[:-1])],
    )
    state = forms.ChoiceField(required=False, label="Assessment", choices=REVIEW_SCOPES, initial="attention")
    workflow = forms.ChoiceField(
        required=False,
        label="Workflow status",
        choices=[("", "Any status"), *Finding._meta.get_field("status").choices],
    )

    def apply(self, findings):
        data = self.cleaned_data
        if query := data["q"]:
            findings = findings.filter(
                Q(record__external_id__icontains=query)
                | Q(installation__asset__name__icontains=query)
                | Q(installation__product__name__icontains=query)
            )
        if data["cvss_min"] is not None:
            findings = findings.filter(record__source_cvss__gte=data["cvss_min"])
        if threshold := data["ubuntu_above"]:
            priorities = UBUNTU_PRIORITIES[UBUNTU_PRIORITIES.index(threshold) + 1 :]
            findings = findings.filter(
                record__source__startswith="https://security-metadata.canonical.com/oval/com.ubuntu.",
                record__payload__bearings_distro__schema="bearings.distro-oval.v1",
                record__payload__bearings_distro__feed__startswith="ubuntu:",
                record__payload__bearings_distro__severity__in=priorities,
            )
        if status := data["workflow"]:
            findings = findings.filter(status=status)
        return findings


def grouped_page(findings, view, number, filters, return_to, *, show_affected):
    dimension, related = (
        ("installation__asset", "installation__product")
        if view == "machine"
        else ("installation__product", "installation__asset")
    )
    key, name = dimension + "_id", dimension + "__name"
    cve = Q(record__external_id__iregex=CVE_ID)
    scores = (
        {
            "affected_cves": Count("case_identifier", distinct=True, filter=AFFECTED_CVE),
            "max_cvss": Max("record__source_cvss", filter=AFFECTED_CVE),
        }
        if show_affected
        else {"max_cvss": Max("record__source_cvss")}
    )
    groups = (
        case_identity(findings)
        .values(key, name)
        .annotate(
            cves=Count("case_identifier", distinct=True, filter=cve),
            related_count=Count(related, distinct=True),
            **scores,
        )
        .order_by(name, key)
    )
    page = Paginator(groups, 25).get_page(number)
    rows = list(page)
    for row in rows:
        if show_affected:
            row["unverified_cves"] = row["cves"] - row["affected_cves"]
        params = filters.copy()
        params["view"] = "cve"
        params["asset" if view == "machine" else "product"] = row[key]
        params["return_to"] = return_to
        row.update(name=row[name], url="?" + params.urlencode())
        if row.get("affected_cves"):
            params["state"] = "affected"
            row["affected_url"] = "?" + params.urlencode()
    page.object_list = rows
    return page
