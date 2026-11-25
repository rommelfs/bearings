"""Finding queues, vulnerability lookup and review actions."""

from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import (
    Case,
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    TextField,
    Value,
    When,
)
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect, render
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
from .overview_queries import bounded_list
from .pagination import object_page
from .presentation import ACTIVE_REVIEWS, decorate_finding
from .services import (
    lookup_for_installation,
    transition_finding,
)


@login_required
@analyst_read_snapshot
@bounded_list
def home(request):
    org_page = company_cards(
        request.user, organizations_for(request.user).order_by("name", "pk"), request.GET.get("org_page")
    )
    orgs = org_page.object_list
    if request.user.is_superuser or is_analyst(request.user):
        audit(request.user, None, "operator.review_queue")
    query = request.GET.get("q", "")[:160].strip()
    severity = request.GET.get("severity", "").lower()
    severity_choices = ["critical", "high", "medium", "low", "none", "unknown"]
    if severity not in severity_choices:
        severity = ""
    reviews = (
        visible_findings_for(request.user)
        .filter(status__in=ACTIVE_REVIEWS)
        .annotate(
            severity_order=Case(
                *[When(record__source_severity=key, then=Value(i)) for i, key in enumerate(severity_choices)],
                default=Value(5),
                output_field=IntegerField(),
            ),
            review_order=Case(
                When(installation__asset__criticality="high", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("severity_order", "review_order", "-evaluated_at", "pk")
    )
    if query:
        reviews = reviews.annotate(
            inventory_text=Cast("installation__asset__upstream_data", TextField()),
            assigned_ip_match=Exists(
                assigned_addresses()
                .filter(network_host_id=OuterRef("installation__asset_id"))
                .filter(Q(name__icontains=query) | Q(address_dns__icontains=query))
            ),
        ).filter(
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
    from .review_queue import BUCKETS, classified

    reviews = classified(reviews)
    bucket = request.GET.get("state", "action")
    if bucket not in dict(BUCKETS):
        bucket = "action"
    bucket_counts = Counter()
    counts = Counter()
    for row in (
        reviews.order_by().values("queue_bucket", "record__source_severity").annotate(total=Count("pk"))
    ):
        bucket_counts[row["queue_bucket"]] += row["total"]
        if bucket == "all" or bucket == row["queue_bucket"]:
            counts[row["record__source_severity"]] += row["total"]
    queue_states = [
        {
            "key": key,
            "label": label,
            "count": sum(bucket_counts.values()) if key == "all" else bucket_counts.get(key, 0),
        }
        for key, label in BUCKETS
    ]
    if bucket != "all":
        reviews = reviews.filter(queue_bucket=bucket)
    reviews = reviews.select_related("distro_match__component__device", "distro_match__advisory__feed")
    severity_counts = [
        {"key": key, "label": key.title(), "count": counts.get(key, 0)} for key in severity_choices
    ]
    review_total = sum(counts.values())
    if severity:
        reviews = reviews.filter(record__source_severity=severity)
    review_page = object_page(
        reviews,
        25,
        request.GET.get("review_page"),
        count=counts.get(severity, 0) if severity else review_total,
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
