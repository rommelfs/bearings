from urllib.parse import quote
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .access import can_edit, can_operator_review, require, visible_findings
from .connectors.http import ConnectorError, validate_base
from .forms import RiskLinkForm, RiskWithdrawalForm
from .intelligence import link_risk, link_state, visible_links, withdraw_link
from .models import MOSPRisk, MOSPSource, RiskLink
from .views import organization
from .presentation import decorate_finding


def vulnerability_url(finding):
    try:
        base = validate_base(finding.record.source).geturl().rstrip("/")
    except ConnectorError:
        return ""
    return base + "/api/vulnerability/" + quote(finding.record.external_id, safe="")


def finding_page(request, org):
    links = RiskLink.objects.select_related("risk_revision__risk__source", "evidence_revision", "created_by")
    findings = (
        visible_findings(request.user, org)
        .select_related("installation__asset__source__instance")
        .prefetch_related(Prefetch("risk_links", queryset=links))
        .order_by("-evaluated_at", "pk")
    )
    if request.GET.get("finding"):
        try:
            finding_id = int(request.GET["finding"])
        except ValueError:
            raise Http404 from None
        get_object_or_404(findings, pk=finding_id)
        findings = findings.filter(pk=finding_id)
    page = Paginator(findings, 25).get_page(request.GET.get("page"))
    for finding in page:
        decorate_finding(finding)
        finding.vulnerability_url = vulnerability_url(finding)
        finding.links = list(finding.risk_links.all())
        for link in finding.links:
            link.review_flags = link_state(link)
            link.needs_review = any(link.review_flags.values())
    return page


@login_required
def intelligence(request, slug):
    org = organization(request, slug)
    return render(
        request,
        "portal/intelligence.html",
        {
            "org": org,
            "page": finding_page(request, org),
            "editable": can_edit(request.user, org) or can_operator_review(request.user, org),
            "sources": MOSPSource.objects.all(),
            "withdrawal_form": RiskWithdrawalForm(),
        },
    )


@login_required
def risk_catalog(request, slug):
    org = organization(request, slug)
    finding = None
    if request.GET.get("finding"):
        try:
            finding_id = int(request.GET["finding"])
        except ValueError:
            raise Http404 from None
        finding = get_object_or_404(visible_findings(request.user, org), pk=finding_id)
        require(can_edit(request.user, org) or can_operator_review(request.user, org))
    risks = (
        MOSPRisk.objects.filter(source__enabled=True, missing_since__isnull=True)
        .select_related("source")
        .order_by("description", "pk")
    )
    query = request.GET.get("q", "")[:200]
    if query:
        risks = risks.filter(Q(description__icontains=query) | Q(uuid__icontains=query))
    return render(
        request,
        "portal/risk_catalog.html",
        {
            "org": org,
            "finding": finding,
            "query": query,
            "page": Paginator(risks, 50).get_page(request.GET.get("page")),
            "sources": MOSPSource.objects.all(),
        },
    )


@login_required
def create_risk_link(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org) or can_operator_review(request.user, org))
    finding = get_object_or_404(visible_findings(request.user, org), pk=pk)
    form = RiskLinkForm(
        request.POST or None,
        initial={"source": request.GET.get("source"), "risk_uuid": request.GET.get("risk_uuid")},
    )
    if request.method == "POST" and form.is_valid():
        try:
            link_risk(
                request.user,
                finding,
                form.cleaned_data["source"].pk,
                form.cleaned_data["risk_uuid"],
                form.cleaned_data["reason"],
            )
        except ConnectorError:
            messages.error(
                request,
                "MOSP reference could not be verified. Existing mappings retained; check source, UUID, language and CC0 licensing.",
            )
        else:
            messages.success(
                request,
                "Risk scenario reference recorded with pinned evidence. Applicability and organizational risk remain unassessed.",
            )
            return redirect("intelligence", slug=slug)
    return render(request, "portal/risk_link_form.html", {"org": org, "finding": finding, "form": form})


@login_required
@require_POST
def withdraw_risk_link(request, slug, pk):
    org = organization(request, slug)
    link = get_object_or_404(visible_links(request.user, org), pk=pk)
    require(can_edit(request.user, org) or can_operator_review(request.user, org))
    form = RiskWithdrawalForm(request.POST)
    if form.is_valid():
        withdraw_link(request.user, link.pk, form.cleaned_data["reason"])
        messages.success(
            request, "Mapping withdrawn; original evidence and justification retained in history."
        )
    else:
        messages.error(request, "Record a reason for withdrawing the mapping.")
    return redirect("intelligence", slug=slug)


@login_required
def risk_link_evidence(request, slug, pk):
    org = organization(request, slug)
    link = get_object_or_404(visible_links(request.user, org), pk=pk)
    return JsonResponse(
        {
            "rule": "analyst-catalog-reference/v1",
            "reason": link.reason,
            "created_at": link.created_at,
            "created_by": link.created_by.get_username() if link.created_by else None,
            "evidence_hash": link.evidence_revision.content_hash,
            "evidence_captured_at": link.evidence_revision.captured_at,
            "vulnerability_source": link.finding.record.source,
            "vulnerability_id": link.finding.record.external_id,
            "vulnerability": link.evidence_revision.payload,
            "catalog_hash": link.risk_revision.content_hash,
            "catalog_captured_at": link.risk_revision.captured_at,
            "catalog": link.risk_revision.payload,
            "review_flags": link_state(link),
            "withdrawn_at": link.withdrawn_at,
            "withdrawal_reason": link.withdrawal_reason,
        }
    )


@login_required
def api_intelligence(request, slug):
    org = organization(request, slug)
    page = finding_page(request, org)
    rows = []
    for finding in page:
        asset = finding.installation.asset
        rows.append(
            {
                "finding_id": finding.pk,
                "source_summary": finding.source_summary,
                "status": finding.status,
                "asset": {
                    "id": str(asset.pk),
                    "name": asset.name,
                    "source_id": str(asset.source_id),
                    "instance_id": str(asset.source.instance_id) if asset.source.instance_id else None,
                    "object_type": asset.object_type,
                    "external_id": asset.external_id,
                    "source_url": asset.source_url,
                    "missing_since": asset.missing_since,
                },
                "software": {
                    "name": finding.installation.product.name,
                    "identifier": finding.installation.product.identifier,
                    "version": finding.installation.version or None,
                },
                "vulnerability": {
                    "id": finding.record.external_id,
                    "source": finding.record.source,
                    "url": finding.vulnerability_url,
                    "ingested_at": finding.record.ingested_at,
                    "automated_applicability": finding.applicability,
                    "analyst_applicability": finding.analyst_applicability,
                },
                "risk_links": [
                    {
                        "id": link.pk,
                        "risk_uuid": str(link.risk_revision.risk.uuid),
                        "source_url": link.risk_revision.risk.source_url,
                        "catalog_hash": link.risk_revision.content_hash,
                        "evidence_hash": link.evidence_revision.content_hash,
                        "scenario": link.risk_revision.payload,
                        "reason": link.reason,
                        "created_at": link.created_at,
                        "withdrawn_at": link.withdrawn_at,
                        "withdrawal_reason": link.withdrawal_reason,
                        "review_flags": link.review_flags,
                        "assessment": "unassessed",
                        "rule": "analyst-catalog-reference/v1",
                    }
                    for link in finding.links
                ],
            }
        )
    return JsonResponse(
        {
            "organization": org.slug,
            "pagination": {
                "page": page.number,
                "pages": page.paginator.num_pages,
                "count": page.paginator.count,
            },
            "relationships": rows,
        }
    )
