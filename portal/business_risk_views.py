from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .access import can_edit, can_operator_review, require, organization
from .business_risk import RiskAssessmentForm, assess, evidence
from .intelligence import digest
from .issues import visible_issues
from .models import BusinessRiskRevision, Contact


@login_required
def register(request):
    from django.core.paginator import Paginator
    from django.db.models import OuterRef, Subquery
    from .access import audit_operator_access

    issues = visible_issues(request.user)
    if request.GET.get("organization"):
        org = organization(request, request.GET["organization"])
        issues = issues.filter(organization=org)
    latest = (
        BusinessRiskRevision.objects.filter(issue_id=OuterRef("issue_id")).order_by("-pk").values("pk")[:1]
    )
    rows = (
        BusinessRiskRevision.objects.filter(issue__in=issues, pk=Subquery(latest))
        .select_related(
            "issue__organization",
            "issue__asset",
            "issue__finding__record",
            "issue__finding__installation",
            "actor",
        )
        .order_by("-created_at", "-pk")
    )
    decision = request.GET.get("decision", "")
    if decision in {"review", "mitigate", "avoid", "transfer", "accept"}:
        rows = rows.filter(snapshot__decision=decision)
    page = Paginator(rows, 25).get_page(request.GET.get("page"))
    for row in page:
        row.owner_contact = Contact.objects.filter(
            organization=row.issue.organization, pk=row.snapshot["owner"]
        ).first()
        audit_operator_access(request.user, row.issue.organization)
        row.stale = row.evidence_hash != digest(evidence(row.issue))
        row.overdue = row.snapshot["action_due"] < timezone.localdate().isoformat()
        row.acceptance_expired = bool(
            row.snapshot.get("acceptance_until")
            and row.snapshot["acceptance_until"] < timezone.localdate().isoformat()
        )
    filters = request.GET.copy()
    filters.pop("page", None)
    return render(
        request,
        "portal/risk_register.html",
        {"page": page, "filters": filters.urlencode(), "decision": decision},
    )


@login_required
def assessment(request, slug, pk):
    org = organization(request, slug)
    issue = get_object_or_404(visible_issues(request.user), organization=org, pk=pk)
    latest = issue.business_risks.first()
    from .scenario_suggestions import draft_scenario

    draft = draft_scenario(issue)
    current_hash = digest(evidence(issue))
    initial = (
        dict(latest.snapshot)
        if latest
        else {
            "owner": issue.asset.responsible_contact_id,
            "business_process": f"Service hosted by {issue.asset.name}",
            "business_impact": issue.consequence or draft["consequence"],
            "assumptions": draft["assumptions"],
            "planned_measures": issue.next_action or draft["next_action"],
            "action_due": issue.action_due,
            "reason": draft["reason"],
        }
    )
    initial.update(previous_revision=latest.pk if latest else 0, reviewed_evidence=current_hash)
    editable = can_edit(request.user, org) or can_operator_review(request.user, org)
    form = RiskAssessmentForm(request.POST or None, issue=issue, initial=initial)
    if request.method == "POST":
        require(editable)
        if form.is_valid():
            try:
                # Pass raw form values so model-choice validation also runs in the service.
                assess(request.user, issue, request.POST)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(
                    request, "Company risk assessment recorded with pinned evidence and decision history."
                )
                return redirect("business-risk", slug=slug, pk=pk)
    revisions = list(issue.business_risks.select_related("actor")[:50])
    for revision in revisions:
        revision.owner_contact = Contact.objects.filter(
            organization=org, pk=revision.snapshot["owner"]
        ).first()
        revision.stale = revision.evidence_hash != current_hash
        revision.overdue = revision.snapshot["action_due"] < timezone.localdate().isoformat()
        revision.acceptance_expired = bool(
            revision.snapshot.get("acceptance_until")
            and revision.snapshot["acceptance_until"] < timezone.localdate().isoformat()
        )
    if request.GET.get("format") == "json":
        return JsonResponse(
            {
                "issue": str(issue.pk),
                "revisions": [
                    {
                        "id": r.pk,
                        "created_at": r.created_at,
                        "actor": r.actor_id,
                        "evidence_changed": r.stale,
                        "review_due": r.overdue,
                        "acceptance_expired": r.acceptance_expired,
                        "assessment": r.snapshot,
                    }
                    for r in revisions
                ],
            }
        )
    return render(
        request,
        "portal/business_risk.html",
        {
            "org": org,
            "issue": issue,
            "form": form,
            "editable": editable,
            "revisions": revisions,
            "automatic_scenario": draft,
        },
    )
