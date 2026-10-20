from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .access import audit, audit_operator_access, can_edit, is_analyst, organizations_for, require
from .models import NotificationBatch, NotificationDelivery, NotificationReceipt
from .notifications import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    NotificationForm,
    approve_local,
    authorized_delivery,
    candidates,
    eligible_contacts,
    preview_batch,
)


@login_required
def center(request):
    operator = request.user.is_superuser or is_analyst(request.user)
    defaults = {
        "mode": "circl" if operator else "company",
        "severity": "high",
        "sort": "severity",
        "subject_template": DEFAULT_SUBJECT,
        "body_template": DEFAULT_BODY,
    }
    if not operator:
        org = (
            organizations_for(request.user)
            .filter(membership__user=request.user, membership__role__in=["admin", "editor"])
            .first()
        )
        if org:
            defaults["organization"] = org.pk
    data = (
        request.POST
        if request.method == "POST"
        else {
            **defaults,
            **{
                k: request.GET[k]
                for k in request.GET
                if k in defaults or k in ["organization", "product", "cve", "assessment"]
            },
        }
    )
    form = NotificationForm(request.user, data)
    matches, groups, total = [], [], 0
    if form.is_valid():
        filters, mode = form.filters(), form.cleaned_data["mode"]
        qs = candidates(request.user, mode, filters)
        total = qs.count()
        matches = list(qs[:100])
        seen = set()
        for f in matches:
            if f.organization_id not in seen:
                seen.add(f.organization_id)
                audit_operator_access(request.user, f.organization)
                groups.append({"org": f.organization, "ready": eligible_contacts(f.organization).count()})
        if request.method == "POST" and request.POST.get("action") == "preview":
            try:
                batch = preview_batch(
                    request.user,
                    mode,
                    filters,
                    form.cleaned_data["subject_template"],
                    form.cleaned_data["body_template"],
                )
                return redirect("notification-batch", pk=batch.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
    # Only messages whose current evidence is redistributable appear in a company inbox.
    inbox_orgs = organizations_for(request.user)
    if not request.user.is_superuser:
        inbox_orgs = inbox_orgs.filter(membership__user=request.user)
    inbox = []
    # Apply current redistribution policy before pagination, including its navigation metadata.
    inbox_page = Paginator(
        NotificationDelivery.objects.filter(organization__in=inbox_orgs, status="filed")
        .exclude(findings__record__shareable=False)
        .select_related("organization", "batch")
        .order_by("-filed_at", "-pk"),
        25,
    ).get_page(request.GET.get("inbox_page"))
    for d in inbox_page:
        if authorized_delivery(request.user, d):
            d.can_ack = can_edit(request.user, d.organization)
            inbox.append(d)
            audit_operator_access(request.user, d.organization)
    recent_batches = []
    for batch in (
        NotificationBatch.objects.filter(creator=request.user)
        .prefetch_related("deliveries__organization")
        .order_by("-created_at")[:10]
    ):
        deliveries = list(batch.deliveries.all())
        if all(authorized_delivery(request.user, d) for d in deliveries):
            batch.recipient_count = len(deliveries)
            recent_batches.append(batch)
    return render(
        request,
        "portal/notifications.html",
        {
            "form": form,
            "matches": matches,
            "total": total,
            "groups": groups,
            "inbox": inbox,
            "inbox_page": inbox_page,
            "recent_batches": recent_batches,
        },
    )


def own_batch(request, pk):
    batch = get_object_or_404(NotificationBatch, pk=pk, creator=request.user)
    deliveries = list(
        batch.deliveries.select_related("organization", "contact").order_by(
            "organization__name", "contact__escalation_order", "pk"
        )
    )
    if any(not authorized_delivery(request.user, d) for d in deliveries):
        raise Http404
    for d in deliveries:
        audit_operator_access(request.user, d.organization)
        d.previously_attempted = NotificationReceipt.objects.filter(fingerprint=d.fingerprint).exists()
    return batch, deliveries


@login_required
def batch_detail(request, pk):
    batch, deliveries = own_batch(request, pk)
    return render(
        request,
        "portal/notification_batch.html",
        {
            "batch": batch,
            "deliveries": deliveries,
            "can_approve": any(not d.previously_attempted for d in deliveries),
        },
    )


@login_required
@require_POST
def approve(request, pk):
    batch, _ = own_batch(request, pk)
    try:
        selected = {int(v) for v in request.POST.getlist("delivery")}
        approve_local(request.user, batch.pk, selected)
        messages.success(
            request,
            "Approval recorded. See each recipient result below. Filed means local file only; uncertain attempts require investigation and are not retried.",
        )
    except (ValidationError, ValueError) as exc:
        messages.error(
            request,
            "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Invalid recipient selection.",
        )
    return redirect("notification-batch", pk=batch.pk)


@login_required
@require_POST
def acknowledge(request, pk):
    d = get_object_or_404(
        NotificationDelivery.objects.select_related("organization"),
        pk=pk,
        organization__in=organizations_for(request.user),
        status="filed",
    )
    require(can_edit(request.user, d.organization))
    if not authorized_delivery(request.user, d):
        raise Http404
    # Conditional update keeps the first acknowledgment actor/time on repeated requests.
    if NotificationDelivery.objects.filter(pk=d.pk, acknowledged_at__isnull=True).update(
        acknowledged_at=timezone.now(), acknowledged_by=request.user
    ):
        audit(request.user, d.organization, "notification.acknowledged", d.pk)
    messages.success(
        request, "Receipt acknowledged. Finding assessment and remediation status are unchanged."
    )
    return redirect("notifications")
