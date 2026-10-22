"""Product-independent guided orientation; decisions remain in existing audited services."""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.http import Http404
from .access import (
    visible_findings_for,
    visible_findings,
    organizations_for,
    can_edit,
    can_operator_review,
    audit_operator_access,
)
from .forms import FindingReviewForm
from .models import FindingHistory
from .notifications import eligible_contacts
from .presentation import decorate_finding
from .intelligence import visible_links, link_state
from .views import organization

STEPS = [
    ("asset", "Find the machine"),
    ("evidence", "Check the evidence"),
    ("risk", "Understand the risk"),
    ("action", "Choose an action"),
    ("followup", "Follow up"),
]


@login_required
def start(request):
    query = request.GET.get("q", "").strip()[:160]
    reviews = visible_findings_for(request.user).order_by("-evaluated_at", "pk")
    if query:
        reviews = reviews.filter(
            Q(installation__product__name__icontains=query)
            | Q(record__external_id__icontains=query)
            | Q(installation__asset__name__icontains=query)
        )
    examples = list(reviews[:12])
    for finding in examples:
        audit_operator_access(request.user, finding.organization)
    return render(
        request,
        "portal/getting_started.html",
        {"examples": examples, "query": query, "organization_count": organizations_for(request.user).count()},
    )


@login_required
def case(request, slug, pk):
    org = organization(request, slug)
    finding = get_object_or_404(visible_findings(request.user, org), pk=pk)
    step = request.GET.get("step", "asset")
    keys = [key for key, _ in STEPS]
    if step not in keys:
        raise Http404
    decorate_finding(finding)
    links = list(visible_links(request.user, org).filter(finding=finding, withdrawn_at__isnull=True))
    for link in links:
        link.needs_review = any(link_state(link).values())
    editable = can_edit(request.user, org) or can_operator_review(request.user, org)
    mode = "circl" if can_operator_review(request.user, org) and org.operator_visibility else "company"
    contacts = eligible_contacts(org) if editable else []
    peers = (
        visible_findings(request.user, org)
        .filter(installation__asset=finding.installation.asset)
        .exclude(pk=pk)
    )
    index = keys.index(step)
    return render(
        request,
        "portal/case_guide.html",
        {
            "org": org,
            "finding": finding,
            "step": step,
            "workflow_stage": "",
            "next_label": STEPS[index + 1][1] if index < 4 else "",
            "steps": STEPS,
            "editable": editable,
            "previous": keys[index - 1] if index else None,
            "next": keys[index + 1] if index < 4 else None,
            "links": links,
            "contacts": contacts,
            "mode": mode,
            "peers": peers,
            "review_form": FindingReviewForm(
                initial={"status": finding.status, "assessment": finding.analyst_applicability}
            ),
            "history": FindingHistory.objects.filter(finding=finding)
            .select_related("actor")
            .order_by("-created_at")[:10],
            "notify": editable
            and finding.record.shareable
            and finding.analyst_applicability != "not_affected",
        },
    )
