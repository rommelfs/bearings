from datetime import timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .access import audit_operator_access, require, visible_findings
from .connectors.http import ConnectorError
from .models import FlowIntelCase, FlowIntelInstance
from . import flowintel
from .views import organization


def available_instances():
    import os

    instances = FlowIntelInstance.objects.filter(enabled=True)
    if os.getenv("BEARINGS_DEV_STACK") == "1" and os.getenv("BEARINGS_FLOWINTEL") != "1":
        instances = instances.exclude(name="bundled-flowintel")
    return instances


class HandoffForm(forms.Form):
    instance = forms.ModelChoiceField(queryset=FlowIntelInstance.objects.none())
    deadline = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(
        max_length=3000, widget=forms.Textarea(attrs={"rows": 3}), label="Reason for hand-off"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instance"].queryset = available_instances()


@login_required
def new_case(request, slug, pk):
    org = organization(request, slug)
    finding = get_object_or_404(visible_findings(request.user, org), pk=pk)
    require(flowintel.exportable(request.user, finding))
    form = HandoffForm(
        request.POST or None,
        initial={
            "deadline": timezone.localdate() + timedelta(days=7),
            "reason": "Coordinate evidence review, company notification and remediation follow-up.",
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            binding = flowintel.preview(request.user, finding, **form.cleaned_data)
            return redirect("flowintel-case", slug=slug, pk=binding.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request, "portal/form.html", {"form": form, "org": org, "title": "Prepare private FlowIntel case"}
    )


def binding_for(request, slug, pk):
    org = organization(request, slug)
    binding = get_object_or_404(
        FlowIntelCase.objects.select_related("instance", "creator"), pk=pk, finding__organization=org
    )
    binding.finding = flowintel.finding_for(binding.finding_id)
    if not flowintel.allowed(request.user, binding.finding):
        raise Http404
    audit_operator_access(request.user, org)
    return binding


@login_required
def case_detail(request, slug, pk):
    binding = binding_for(request, slug, pk)
    return render(
        request,
        "portal/flowintel_case.html",
        {
            "org": binding.finding.organization,
            "case": binding,
            "tasks": binding.tasks.order_by("step"),
            "can_approve": binding.state == "draft"
            and binding.creator_id == request.user.pk
            and binding.instance.available,
            "can_reconcile": binding.state in {"uncertain", "creating", "working"},
        },
    )


@login_required
@require_POST
def approve_case(request, slug, pk):
    binding_for(request, slug, pk)
    try:
        flowintel.approve(request.user, pk)
        messages.success(
            request,
            "Private case hand-off approved and queued. The worker will create the case and its playbook tasks.",
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("flowintel-case", slug=slug, pk=pk)


@login_required
@require_POST
def refresh_case(request, slug, pk):
    binding_for(request, slug, pk)
    try:
        if request.POST.get("action") == "reconcile":
            flowintel.reconcile(pk, request.user)
        else:
            flowintel.refresh(pk, request.user)
        messages.success(
            request, "FlowIntel state read. Finding assessment and remediation status are unchanged."
        )
    except (ConnectorError, ValidationError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
    return redirect("flowintel-case", slug=slug, pk=pk)


def decorate(finding, user):
    finding.flowintel_allowed = flowintel.allowed(user, finding)
    finding.flowintel_exportable = flowintel.exportable(user, finding)
    finding.flowintel_bindings = (
        list(finding.flowintel_cases.select_related("instance").all()) if finding.flowintel_allowed else []
    )
    finding.flowintel_available = finding.flowintel_exportable and available_instances().exists()
    finding.flowintel_review_url = reverse("flowintel-new", args=[finding.organization.slug, finding.pk])
