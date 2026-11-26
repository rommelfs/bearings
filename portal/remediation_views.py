from collections import Counter
from datetime import timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import remediation
from .access import organization, require
from .flowintel import load, require_read
from .flowintel_views import available_instances
from .models import Contact, Finding, FlowIntelInstance


class RemediationForm(forms.Form):
    instance = forms.ModelChoiceField(
        queryset=FlowIntelInstance.objects.none(), label="Private FlowIntel destination"
    )
    deadline = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    recipients = forms.ModelMultipleChoiceField(
        queryset=Contact.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select who should receive the notification. Leave empty to create internal tasks only. Technical contacts receive actions for their assigned hosts.",
    )
    review = forms.ModelChoiceField(
        queryset=Finding.objects.none(),
        required=False,
        label="Review ID for an optional mitigation",
        widget=forms.NumberInput,
    )
    action = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Reviewed mitigation or workaround",
    )
    source = forms.CharField(
        required=False, max_length=240, label="Vendor advisory or reviewed runbook reference"
    )
    verification = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="How to verify the mitigation",
    )

    def __init__(self, *args, org, queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instance"].queryset = available_instances().exclude(bearings_url="")
        self.fields["recipients"].queryset = remediation.contacts_for(org)
        self.fields["review"].queryset = queryset

    def clean(self):
        data = super().clean()
        values = [data.get(key) for key in ("review", "action", "source", "verification")]
        if any(values) and not all(values):
            raise forms.ValidationError(
                "For a mitigation, provide the review ID, action, reference and verification."
            )
        data["mitigation"] = (
            {
                "finding": values[0].pk,
                **{key: data[key] for key in ("action", "source", "verification")},
            }
            if all(values)
            else None
        )
        return data


def permitted_cases(actor, ids):
    for pk in sorted(ids)[:25]:
        case = load(pk)
        try:
            require_read(actor, case)
        except PermissionDenied:
            continue
        yield case


@login_required
def prepare(request, slug, pk=None, cve=None):
    org = organization(request, slug)
    require(remediation.available_to(request.user, org))
    asset = None
    if pk:
        asset = get_object_or_404(org.assets.filter(source__organization=org, lifecycle="active"), pk=pk)
    elif not cve or len(cve) > 32 or not remediation.CVE.fullmatch(cve):
        raise Http404
    scope = {"asset": asset.pk if asset else None, "cve": cve}
    qs = remediation.work(request.user, org, **scope)
    form = RemediationForm(
        request.POST if request.method == "POST" else None,
        org=org,
        queryset=qs,
        initial={
            "deadline": timezone.localdate() + timedelta(days=7),
            "instance": available_instances().exclude(bearings_url="").values_list("pk", flat=True).first(),
            "recipients": [asset.responsible_contact_id] if asset and asset.responsible_contact_id else [],
        },
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            case, _ = remediation.preview(
                request.user,
                org,
                **scope,
                instance=data["instance"],
                deadline=data["deadline"],
                contact_ids=[contact.pk for contact in data["recipients"]],
                mitigation=data["mitigation"],
            )
            if case:
                return redirect("flowintel-case", slug=slug, pk=case.pk)
            form.add_error(None, "There are no new actions in this scope. Review any plans listed below.")
        except ValidationError as exc:
            form.add_error(None, exc)
    rows = list(qs[: remediation.MAX_FINDINGS + 1])
    groups, existing = ([], set())
    if len(rows) <= remediation.MAX_FINDINGS:
        groups, existing = remediation.grouped_actions(
            rows, remediation.target_rows(qs), None, skip_reserved=True
        )
    return render(
        request,
        "portal/remediation_prepare.html",
        {
            "org": org,
            "asset": asset,
            "cve": cve,
            "form": form,
            "has_destination": form.fields["instance"].queryset.exists(),
            "has_recipients": form.fields["recipients"].queryset.exists(),
            "reviews": rows[: remediation.MAX_FINDINGS],
            "existing": list(permitted_cases(request.user, existing)),
            "too_many": len(rows) > remediation.MAX_FINDINGS or len(groups) > remediation.MAX_TASKS,
        },
    )


def render_case(request, case):
    states = remediation.verification_for(request.user, case)
    org = case.finding.organization
    tasks = []
    for task, group in zip(case.tasks.order_by("step"), case.snapshot["groups"], strict=True):
        verification = Counter(states.get(item["finding"], "Verification pending") for item in group["items"])
        tasks.append(
            {
                "label": task.label,
                "state": task.state,
                "text": remediation.action_text(group, case.snapshot["bearings_url"], org),
                "verification": verification.items(),
            }
        )
    return render(
        request,
        "portal/remediation_case.html",
        {
            "org": org,
            "case": case,
            "tasks": tasks,
            "deliveries": case.remediation_batch.deliveries.select_related("contact").order_by("pk"),
            "batch": case.remediation_batch,
            "can_approve": case.state == "draft"
            and case.creator_id == request.user.pk
            and case.instance.available,
            "stale_after": timezone.now() - timedelta(minutes=10),
        },
    )
