"""Finding queues, vulnerability lookup and review actions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, Q, TextField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .access import (
    analyst_read_snapshot,
    audit,
    audit_organizations,
    can_edit,
    can_operator_review,
    is_analyst,
    organization,
    organizations_for,
    require,
    visible_findings,
    visible_findings_for,
)
from .connectors.http import ConnectorError
from .forms import (
    FindingReviewForm,
    VulnerabilityForm,
)
from .inventory_presentation import (
    assigned_addresses,
    decorate_addresses,
)
from .inventory_views import company_cards
from .models import (
    Installation,
    Membership,
)
from .overview_queries import bounded_list, read_snapshot
from .presentation import ACTIVE_REVIEWS, SEVERITY_ORDER, decorate_finding
from .queue_context import return_url
from .review_cases import case_identity, case_page, evidence_page
from .review_queue import BUCKETS, classified
from .services import (
    lookup_for_installation,
    transition_finding,
)


@login_required
@analyst_read_snapshot
@read_snapshot()
@bounded_list
def home(request):
    org_scope = organizations_for(request.user)
    org_page = company_cards(request.user, org_scope.order_by("name", "pk"), request.GET.get("org_page"))
    orgs = org_page.object_list
    if request.user.is_superuser or is_analyst(request.user):
        audit(request.user, None, "operator.review_queue")
    query = request.GET.get("q", "")[:160].strip()
    severity = request.GET.get("severity", "").lower()
    if severity not in SEVERITY_ORDER:
        severity = ""
    reviews = visible_findings_for(request.user).filter(status__in=ACTIVE_REVIEWS)
    has_package_proofs = reviews.filter(distro_match__isnull=False).exists()
    reviews = classified(
        reviews, organizations=org_scope.order_by().values("pk"), package_evidence=has_package_proofs
    )
    search = None
    if query:
        reviews = reviews.annotate(
            inventory_text=Cast("installation__asset__upstream_data", TextField()),
            assigned_ip_match=Exists(
                assigned_addresses()
                .filter(network_host_id=OuterRef("installation__asset_id"))
                .filter(Q(name__icontains=query) | Q(address_dns__icontains=query))
            ),
        )
        search = (
            Q(record__external_id__icontains=query)
            | Q(installation__asset__name__icontains=query)
            | Q(organization__name__icontains=query)
            | Q(installation__product__name__icontains=query)
            | Q(installation__asset__responsible_team__icontains=query)
            | Q(inventory_text__icontains=query)
            | Q(assigned_ip_match=True)
        )
    from .distro_verdicts import decorate_package_verdict
    from .inventory_presentation import host_network_summary

    bucket = request.GET.get("state", "action")
    if bucket not in dict(BUCKETS):
        bucket = "action"
    review_page, queue_states, severity_counts, review_total = case_page(
        reviews, request.GET.get("review_page"), bucket, severity, search
    )
    audit_organizations(request.user, [finding.organization for finding in review_page])
    operator = request.user.is_superuser or is_analyst(request.user)
    roles = dict(
        Membership.objects.filter(
            user=request.user, organization_id__in=[finding.organization_id for finding in review_page]
        ).values_list("organization_id", "role")
    )
    assets = {finding.installation.asset_id: finding.installation.asset for finding in review_page}
    for finding in review_page:
        assets[finding.installation.asset_id].organization = finding.organization
    decorate_addresses(list(assets.values()))
    networks = {pk: host_network_summary(asset) for pk, asset in assets.items()}
    for finding in review_page:
        decorate_finding(finding)
        for key in ("addresses", "dns_names", "assigned_address_count", "addresses_truncated"):
            finding.asset_context[key] = networks[finding.installation.asset_id][key]
        if not finding.multiple_installations:
            decorate_package_verdict(finding)
        finding.notification_mode = ""
        if finding.record.shareable and finding.analyst_applicability != "not_affected":
            if operator and finding.organization.operator_visibility:
                finding.notification_mode = "circl"
            elif request.user.is_superuser or roles.get(finding.organization_id) in {"admin", "editor"}:
                finding.notification_mode = "company"
    return render(
        request,
        "portal/home.html",
        {
            "orgs": orgs,
            "org_page": org_page,
            "operator": request.user.is_superuser or is_analyst(request.user),
            "review_page": review_page,
            "query": query,
            "severity": severity,
            "severity_counts": severity_counts,
            "queue_states": queue_states,
            "queue_state": bucket,
            "queue_heading": dict(BUCKETS)[bucket],
            "review_total": review_total,
        },
    )


@login_required
@analyst_read_snapshot
@read_snapshot()
@bounded_list
def review_evidence(request, pk):
    visible = case_identity(visible_findings_for(request.user)).filter(status__in=ACTIVE_REVIEWS)
    finding = get_object_or_404(visible, pk=pk)
    page = evidence_page(visible, finding, request.GET.get("page"))
    audit_organizations(request.user, [finding.organization])
    return render(
        request,
        "portal/review_evidence.html",
        {
            "finding": finding,
            "page": page,
            "return_url": return_url(request) or reverse("home"),
        },
    )


@login_required
@require_POST
def lookup_vulnerability(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    installation = get_object_or_404(Installation, pk=pk, asset__organization=org)
    form = VulnerabilityForm(request.POST)
    if form.is_valid():
        try:
            lookup_for_installation(request.user, installation, form.cleaned_data["identifier"])
        except ConnectorError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request, "Vulnerability record retrieved for review. Applicability remains unknown."
            )
    else:
        messages.error(
            request, "Enter the CVE identifier you want to investigate, in CVE-year-number format."
        )
    return redirect("organization", slug=slug)


@login_required
@require_POST
def finding_review(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org) or can_operator_review(request.user, org))
    finding = get_object_or_404(visible_findings(request.user, org), pk=pk)
    form = FindingReviewForm(request.POST)
    if form.is_valid():
        transition_finding(request.user, finding, **form.cleaned_data)
    else:
        messages.error(request, "Choose a workflow state and record a reason.")
    if request.GET.get("return") == "guide":
        from django.urls import reverse

        from .queue_context import with_return

        return redirect(with_return(request, reverse("case-guide", args=[slug, pk]) + "?step=risk"))
    if request.GET.get("return") == "intelligence":
        from django.urls import reverse

        from .queue_context import with_return

        return redirect(
            with_return(
                request,
                reverse("intelligence", kwargs={"slug": slug})
                + f"?finding={finding.pk}#finding-{finding.pk}",
            )
        )
    return redirect("organization", slug=slug)
