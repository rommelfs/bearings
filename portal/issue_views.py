from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, F, IntegerField, Q, TextField, Value, When
from django.db.models.functions import Cast, Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import issues
from .access import audit_operator_access, organizations_for, require, can_edit, can_operator_review
from .asset_context import asset_context
from .issue_forms import IssueForm, RiskForm
from .models import AssetIssue, IssueRiskLink
from .presentation import vulnerability_summary
from .views import organization


def scoped(request, slug, pk):
    org = organization(request, slug)
    return get_object_or_404(issues.visible_issues(request.user), organization=org, pk=pk)


def decorate(issue):
    issue.facts = asset_context(issue.asset)
    issue.source_summary = vulnerability_summary(issue.finding.record.payload) if issue.finding_id else None
    return issue


@login_required
def board(request):
    orgs = organizations_for(request.user).order_by("name")
    base = issues.visible_issues(request.user)
    org_id = request.GET.get("organization", "")
    if org_id:
        org = get_object_or_404(orgs, slug=org_id)
        base = base.filter(organization=org)
    # Counts, filters and pagination all start from the same currently visible rows.
    for org in orgs:
        audit_operator_access(request.user, org)
        org.issue_editable = can_edit(request.user, org) or can_operator_review(request.user, org)
    kind = request.GET.get("kind", "")
    if kind in dict(AssetIssue.KINDS):
        base = base.filter(kind=kind)
    else:
        kind = ""
    state = request.GET.get("state", "active")
    if state == "active":
        base = base.filter(issues.active_filter())
    elif state == "closed":
        base = base.exclude(issues.active_filter())
    else:
        state = "all"
    query = request.GET.get("q", "")[:180].strip()
    if query:
        base = base.annotate(inventory_text=Cast("asset__upstream_data", TextField())).filter(
            Q(title__icontains=query)
            | Q(asset__name__icontains=query)
            | Q(owner_team__icontains=query)
            | Q(organization__name__icontains=query)
            | Q(installation__product__name__icontains=query)
            | Q(inventory_text__icontains=query)
            | Q(contract_reference__icontains=query)
        )
    base = base.annotate(
        deadline_order=Coalesce("action_due", "event_date"),
        priority_order=Case(
            When(priority="critical", then=Value(0)),
            When(priority="high", then=Value(1)),
            When(priority="review", then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
    )
    today = timezone.localdate()
    counts = {
        "total": base.count(),
        "overdue": base.filter(deadline_order__lt=today).count(),
        "soon": base.filter(
            deadline_order__gte=today, deadline_order__lte=today + timedelta(days=30)
        ).count(),
        "unknown": base.filter(deadline_order__isnull=True).count(),
    }
    timing = request.GET.get("timing", "")
    if timing == "overdue":
        base = base.filter(deadline_order__lt=today)
    elif timing == "soon":
        base = base.filter(deadline_order__gte=today, deadline_order__lte=today + timedelta(days=30))
    elif timing == "unknown":
        base = base.filter(deadline_order__isnull=True)
    else:
        timing = ""
    page = Paginator(
        base.order_by("priority_order", F("deadline_order").asc(nulls_last=True), "-updated_at", "pk"), 25
    ).get_page(request.GET.get("page"))
    for issue in page:
        decorate(issue)
    filters = request.GET.copy()
    filters.pop("page", None)
    return render(
        request,
        "portal/issues.html",
        {
            "page": page,
            "orgs": orgs,
            "kind_choices": AssetIssue.KINDS,
            "kind": kind,
            "state": state,
            "query": query,
            "organization_filter": org_id,
            "counts": counts,
            "timing": timing,
            "filters": filters.urlencode(),
        },
    )


@login_required
def detail(request, slug, pk):
    issue = decorate(scoped(request, slug, pk))
    current = issues.data_for(issue)
    risks = issue.risk_scenarios.select_related("risk_revision__risk__source", "issue_revision").order_by(
        "-created_at"
    )
    for link in risks:
        link.evidence_changed = link.issue_revision.snapshot != current
    from . import rt
    from .rt_views import instances

    rt_rows = [
        row
        for row in issue.rt_tickets.select_related("instance")
        if rt.can_read(request.user, issue, row.instance)
    ]
    can_rt_export = any(
        rt.can_write(request.user, issue, instance) for instance in instances(request.user, issue)
    )
    return render(
        request,
        "portal/issue.html",
        {
            "issue": issue,
            "org": issue.organization,
            "asset": issue.asset,
            "facts": issue.facts,
            "editable": issues.editable(request.user, issue),
            "history": issue.history.select_related("actor", "revision").order_by("-created_at")[:50],
            "risks": risks,
            "rt_tickets": rt_rows,
            "can_rt_export": can_rt_export,
            "risk_form": RiskForm(),
        },
    )


@login_required
def create(request, slug):
    org = organization(request, slug)
    require(can_edit(request.user, org) or can_operator_review(request.user, org))
    form = IssueForm(
        request.POST or None,
        organization=org,
        actor=request.user,
        initial={"asset": request.GET.get("asset"), "source_label": "Manual evidence review"},
    )
    if request.method == "POST" and form.is_valid():
        try:
            values = dict(form.cleaned_data)
            reason = values.pop("reason")
            issue = issues.save_issue(request.user, AssetIssue(organization=org), values, reason)
            messages.success(request, "Asset issue recorded with an immutable evidence revision.")
            return redirect("issue", slug=org.slug, pk=issue.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request, "portal/issue_form.html", {"form": form, "org": org, "title": "Record asset issue"}
    )


@login_required
def edit(request, slug, pk):
    issue = scoped(request, slug, pk)
    require(issues.editable(request.user, issue))
    form = IssueForm(
        request.POST or None, instance=issue, organization=issue.organization, actor=request.user
    )
    if request.method == "POST" and form.is_valid():
        try:
            values = dict(form.cleaned_data)
            reason = values.pop("reason")
            issue = issues.save_issue(request.user, issue, values, reason)
            messages.success(request, "Review recorded. Earlier evidence and history were retained.")
            return redirect("issue", slug=slug, pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "portal/issue_form.html",
        {"form": form, "org": issue.organization, "title": "Review asset issue", "issue": issue},
    )


@login_required
@require_POST
def add_risk(request, slug, pk):
    issue = scoped(request, slug, pk)
    require(issues.editable(request.user, issue))
    form = RiskForm(request.POST)
    if form.is_valid():
        try:
            issues.link_risk(request.user, issue, **form.cleaned_data)
            messages.success(request, "Risk scenario linked with pinned issue and catalog evidence.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    else:
        messages.error(request, "Choose an available scenario and provide a reason.")
    return redirect("issue", slug=slug, pk=pk)


@login_required
@require_POST
def withdraw_risk(request, slug, pk, link_pk):
    issue = scoped(request, slug, pk)
    require(issues.editable(request.user, issue))
    link = get_object_or_404(IssueRiskLink, pk=link_pk, issue=issue)
    issues.withdraw_risk(request.user, link, request.POST.get("reason", "")[:4001])
    return redirect("issue", slug=slug, pk=pk)


@login_required
def api_list(request, slug):
    org = organization(request, slug)
    page = Paginator(
        issues.visible_issues(request.user).filter(organization=org).order_by("pk"), 100
    ).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "schema": "bearings.asset-issues/v1",
            "organization": str(org.pk),
            "page": page.number,
            "pages": page.paginator.num_pages,
            "count": page.paginator.count,
            "results": [issues.issue_json(issue) for issue in page],
        }
    )


@login_required
def api_evidence(request, slug, pk):
    issue = scoped(request, slug, pk)
    if issue.finding_id:
        return redirect("api-evidence", slug=slug, pk=issue.finding_id)
    revision_id = request.GET.get("revision")
    revision = (
        get_object_or_404(issue.revisions, pk=revision_id)
        if revision_id
        else issue.revisions.order_by("-captured_at", "-pk").first()
    )
    if not revision:
        return JsonResponse({"error": "No evidence revision recorded"}, status=404)
    return JsonResponse(
        {
            "schema": "bearings.issue-evidence/v1",
            "issue": str(issue.pk),
            "revision": revision.pk,
            "digest": revision.digest,
            "captured_at": revision.captured_at,
            "snapshot": revision.snapshot,
        }
    )
