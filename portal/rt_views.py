from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from . import rt
from .access import can_operator_review
from .connectors.http import ConnectorError
from .issue_views import scoped
from .models import RTInstance, RTTicket


def instances(actor, issue):
    qs = RTInstance.objects.filter(enabled=True, private_queue_confirmed=True).filter(
        Q(organization=issue.organization) | Q(organization__isnull=True)
    )
    if not can_operator_review(actor, issue.organization) or not issue.organization.operator_visibility:
        qs = qs.filter(organization=issue.organization)
    return qs.order_by("name")


class HandoffForm(forms.Form):
    instance = forms.ModelChoiceField(queryset=RTInstance.objects.none())
    reason = forms.CharField(max_length=3000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, actor, issue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instance"].queryset = instances(actor, issue)


@login_required
def new(request, slug, pk):
    issue = scoped(request, slug, pk)
    form = HandoffForm(
        request.POST or None,
        actor=request.user,
        issue=issue,
        initial={"reason": "Coordinate issue review, ownership and remediation follow-up."},
    )
    if request.method == "POST" and form.is_valid():
        try:
            row = rt.preview(request.user, issue, **form.cleaned_data)
            return redirect("rt-ticket", slug=slug, pk=row.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "portal/form.html",
        {"title": "Prepare RT / RTIR ticket", "form": form, "org": issue.organization},
    )


def binding(request, slug, pk):
    candidate = get_object_or_404(RTTicket, pk=pk, issue__organization__slug=slug)
    issue = scoped(request, slug, candidate.issue_id)
    row = rt.load(candidate.pk)
    if not rt.can_read(request.user, issue, row.instance):
        from django.http import Http404

        raise Http404
    return row


@login_required
def detail(request, slug, pk):
    row = binding(request, slug, pk)
    return render(
        request,
        "portal/rt_ticket.html",
        {
            "ticket": row,
            "org": row.issue.organization,
            "can_approve": row.state == "draft"
            and row.creator_id == request.user.pk
            and rt.can_write(request.user, row.issue, row.instance),
            "can_reconcile": row.state in {"uncertain", "creating"},
        },
    )


@login_required
@require_POST
def action(request, slug, pk):
    row = binding(request, slug, pk)
    try:
        operation = request.POST.get("action")
        if operation == "approve":
            rt.approve(request.user, row.pk)
            messages.success(request, "Approved RT ticket export queued. No duplicate POST retries are made.")
        elif operation == "reconcile":
            rt.reconcile(row.pk, request.user)
            messages.success(request, "Ticket identity reconciled using reads only.")
        elif operation == "refresh":
            rt.refresh(row.pk, request.user)
            messages.success(request, "RT workflow refreshed. Asset issue assessment unchanged.")
        else:
            raise ValidationError("Unsupported action")
    except (ValidationError, ConnectorError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
    return redirect("rt-ticket", slug=slug, pk=pk)
