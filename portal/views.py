from .overview_queries import bounded_list
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Prefetch, Q, TextField, Value, When
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from .access import (
    audit,
    audit_operator_access,
    audit_organizations,
    can_edit,
    can_operator_review,
    can_review_contact,
    is_analyst,
    organizations_for,
    require,
    visible_findings,
    visible_findings_for,
)
from .connectors.http import ConnectorError
from .forms import (
    AssetForm,
    LocalAssetForm,
    ClaimForm,
    ClaimReviewForm,
    ContactForm,
    FindingReviewForm,
    InstallationForm,
    MissingReviewForm,
    VulnerabilityForm,
)
from .presentation import ACTIVE_REVIEWS, decorate_finding, severity_first
from .asset_context import asset_context
from .pagination import object_page
from .models import (
    AgentDevice,
    Asset,
    Contact,
    ContactToken,
    InfrastructureClaim,
    Installation,
    Product,
    Membership,
)
from .services import (
    issue_contact_token,
    lookup_for_installation,
    redeem_contact_token,
    review_contact,
    submit_asset,
    transition_finding,
)


def organization(request, slug):
    org = get_object_or_404(organizations_for(request.user), slug=slug)
    audit_operator_access(request.user, org)
    return org


def company_cards(user, orgs, page_number):
    page = Paginator(orgs, 24).get_page(page_number)
    page.object_list = list(
        page.object_list.select_related("inventory_source__instance").prefetch_related("contacts")
    )
    ids = [org.pk for org in page]
    asset_counts = dict(
        Asset.objects.filter(organization_id__in=ids)
        .values("organization_id")
        .annotate(total=Count("pk"))
        .values_list("organization_id", "total")
    )
    finding_counts = dict(
        visible_findings_for(user)
        .filter(organization_id__in=ids, status__in=ACTIVE_REVIEWS)
        .order_by()
        .values("organization_id")
        .annotate(total=Count("pk"))
        .values_list("organization_id", "total")
    )
    audit_organizations(user, page.object_list)
    for org in page:
        org.asset_count = asset_counts.get(org.pk, 0)
        org.overdue_count = sum(c.overdue for c in org.contacts.all())
        org.finding_count = finding_counts.get(org.pk, 0)
    return page


@login_required
def inventory(request):
    query = request.GET.get("q", "")[:160].strip()
    orgs = organizations_for(request.user).order_by("name", "pk")
    if query:
        orgs = orgs.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    page = company_cards(request.user, orgs, request.GET.get("page"))
    return render(request, "portal/inventory.html", {"page": page, "query": query})


@login_required
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
            inventory_text=Cast("installation__asset__upstream_data", TextField())
        ).filter(
            Q(record__external_id__icontains=query)
            | Q(installation__asset__name__icontains=query)
            | Q(organization__name__icontains=query)
            | Q(installation__product__name__icontains=query)
            | Q(installation__asset__responsible_team__icontains=query)
            | Q(inventory_text__icontains=query)
        )
    counts = {
        r["record__source_severity"]: r["total"]
        for r in reviews.order_by().values("record__source_severity").annotate(total=Count("pk"))
    }
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
    for finding in review_page:
        decorate_finding(finding)
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
            "review_total": review_total,
        },
    )


@login_required
def detail(request, slug):
    from .models import OrganizationConfiguration

    org = organization(request, slug)
    inventory_page = Paginator(
        org.assets.select_related("source__instance")
        .prefetch_related(
            Prefetch(
                "installations",
                queryset=Installation.objects.select_related("product").order_by("product__name", "pk")[:10],
                to_attr="software_preview",
            )
        )
        .order_by("name", "pk"),
        50,
    ).get_page(request.GET.get("inventory_page"))
    inventory_page.object_list = list(inventory_page.object_list)
    counts = dict(
        Installation.objects.filter(asset_id__in=[a.pk for a in inventory_page])
        .values("asset_id")
        .annotate(total=Count("pk"))
        .values_list("asset_id", "total")
    )
    from .distro_display import decorate_installations

    decorate_installations(request.user, [i for a in inventory_page for i in a.software_preview])
    for a in inventory_page:
        a.software_count = counts.get(a.pk, 0)
    return render(
        request,
        "portal/detail.html",
        {
            "org": org,
            "editable": can_edit(request.user, org),
            "inventory_writable": can_edit(request.user, org)
            and hasattr(org, "inventory_source")
            and org.inventory_source.can_write,
            "public_keys": OrganizationConfiguration.objects.filter(organization=org)
            .values("pgp_public_key", "smime_certificate")
            .first(),
            "contact_reviewer": can_review_contact(request.user, org),
            "member_admin": org.membership_set.filter(user=request.user, role="admin").exists(),
            "operator_reviewer": can_operator_review(request.user, org),
            "findings": severity_first(visible_findings(request.user, org)),
            "claim_review_form": ClaimReviewForm(),
            "finding_review_form": FindingReviewForm(),
            "lookup_form": VulnerabilityForm(),
            "missing_review_form": MissingReviewForm(),
            "inventory_page": inventory_page,
        },
    )


@login_required
def create_contact(request, slug):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            contact = form.save(commit=False)
            contact.organization = org
            contact.save()
            audit(request.user, org, "contact.created", contact.pk)
        return redirect("organization", slug=slug)
    return render(request, "portal/form.html", {"form": form, "title": "Add emergency contact", "org": org})


@login_required
@require_POST
def contact_action(request, slug, pk, action):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    contact = get_object_or_404(Contact, organization=org, pk=pk)
    if action == "review":
        review_contact(request.user, contact)
        messages.success(
            request,
            "Role and details reviewed. Channel reachability and emergency availability are separate.",
        )
    elif action == "verify":
        service = contact.registration_notifications.exists()
        if service:
            try:
                sent = issue_contact_token(request.user, contact, service=True)
            except Exception:
                sent = False
                audit(request.user, org, "contact.service_verification_failed", contact.pk)
            if sent:
                messages.success(
                    request, "Team mailbox verification prepared using the configured service mail transport."
                )
            else:
                messages.warning(
                    request,
                    "Team verification was not prepared. Allow 15 minutes between requests or check service mail configuration and retry.",
                )
        else:
            issue_contact_token(request.user, contact)
            messages.success(
                request, "Verification prepared in the local development mail sink (.local/mail)."
            )
    elif action == "availability":
        contact.availability_confirmed_at = timezone.now()
        contact.save(update_fields=["availability_confirmed_at"])
        audit(request.user, org, "contact.availability_confirmed", contact.pk)
    elif action == "invalid":
        contact.invalid_delivery = True
        contact.reachable_at = None
        contact.save(update_fields=["invalid_delivery", "reachable_at"])
        audit(request.user, org, "contact.delivery_invalid", contact.pk)
    else:
        require(False)
    return redirect("organization", slug=slug)


@never_cache
@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def verify_contact(request):
    if request.method == "POST":
        success = redeem_contact_token(request.POST.get("token", ""))
        return render(
            request,
            "portal/verify.html",
            {
                "result": "Mailbox confirmation recorded. Contact role, emergency availability and infrastructure authority remain separate."
                if success
                else "Invalid or expired token."
            },
        )
    return render(request, "portal/verify.html")


@login_required
def create_claim(request, slug):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    form = ClaimForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            claim = form.save(commit=False)
            claim.organization = org
            claim.save()
            audit(request.user, org, "scope.declared", claim.pk)
        return redirect("organization", slug=slug)
    return render(
        request, "portal/form.html", {"form": form, "title": "Declare infrastructure scope", "org": org}
    )


@login_required
@require_POST
def claim_review(request, slug, pk):
    org = organization(request, slug)
    require(can_operator_review(request.user, org))
    claim = get_object_or_404(InfrastructureClaim, pk=pk, organization=org)
    form = ClaimReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            claim.status, claim.method = form.cleaned_data["status"], form.cleaned_data["method"]
            claim.reviewed_by, claim.reviewed_at = request.user, timezone.now()
            claim.save()
            audit(request.user, org, "scope.reviewed", claim.pk, status=claim.status, method=claim.method)
    else:
        messages.error(request, "Select a review status and describe the authority verification method.")
    return redirect("organization", slug=slug)


@login_required
def create_asset(request, slug):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    require(hasattr(org, "inventory_source") and org.inventory_source.can_write)
    form = AssetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        submit_asset(request.user, org, form)
        messages.success(
            request,
            "Inventory write queued. Run process_jobs; it is not yet confirmed by the inventory source.",
        )
        return redirect("organization", slug=slug)
    return render(request, "portal/form.html", {"form": form, "title": "Submit an asset", "org": org})


@login_required
@require_POST
def request_inventory_import(request, slug):
    from .models import InventorySource

    org = organization(request, slug)
    require(can_edit(request.user, org))
    with transaction.atomic():
        source = get_object_or_404(InventorySource.objects.select_for_update(), organization=org)
        require(source.mode in {"central", "external"} and source.instance_id and source.instance.enabled)
        source.import_requested = True
        source.save(update_fields=["import_requested"])
        audit(request.user, org, "inventory.import_requested", source.pk)
    messages.success(request, "Inventory import queued. The worker will perform a complete GET-only refresh.")
    return redirect("organization", slug=slug)


@login_required
@require_POST
def review_missing_asset(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    form = MissingReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            asset = get_object_or_404(Asset.objects.select_for_update(), organization=org, pk=pk)
            require(asset.missing_since is not None)
            asset.missing_reviewed_at = timezone.now()
            asset.missing_review_reason = form.cleaned_data["reason"]
            asset.save(update_fields=["missing_reviewed_at", "missing_review_reason"])
            audit(
                request.user, org, "inventory.missing_reviewed", asset.pk, reason=asset.missing_review_reason
            )
        messages.success(request, "Missing-object review recorded. Inventory and assessments retained.")
    else:
        messages.error(request, "Record a reason for the missing-object review.")
    return redirect("organization", slug=slug)


@login_required
def create_installation(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    asset = get_object_or_404(Asset, pk=pk, organization=org)
    form = InstallationForm(request.POST or None, organization=org)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            product = form.cleaned_data["existing_product"]
            if not product:
                product, _ = Product.objects.get_or_create(
                    organization=org,
                    name=form.cleaned_data["product_name"],
                    identifier=form.cleaned_data["product_identifier"],
                )
            installation = form.save(commit=False)
            installation.asset, installation.product = asset, product
            installation.full_clean()
            installation.save()
            from .models import ProductWatch
            from .product_matching import ensure_watch
            from django.core.exceptions import ValidationError

            try:
                ensure_watch(product, request.user)
            except ValidationError:
                messages.warning(
                    request, "Software saved. Automatic monitoring needs an operator-approved source."
                )

            ProductWatch.objects.filter(product=product).update(requested=True)
            audit(request.user, org, "software.installed", installation.pk)
        return redirect("organization", slug=slug)
    return render(
        request, "portal/form.html", {"form": form, "title": f"Software on {asset.name}", "org": org}
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

        return redirect(reverse("case-guide", args=[slug, pk]) + "?step=risk")
    if request.GET.get("return") == "intelligence":
        from django.urls import reverse

        return redirect(
            reverse("intelligence", kwargs={"slug": slug}) + f"?finding={finding.pk}#finding-{finding.pk}"
        )
    return redirect("organization", slug=slug)


@login_required
def api_inventory(request, slug):
    org = organization(request, slug)
    page = Paginator(
        org.assets.select_related("source__instance")
        .prefetch_related("installations__product")
        .order_by("name", "pk"),
        100,
    ).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "organization": org.slug,
            "pagination": {
                "page": page.number,
                "pages": page.paginator.num_pages,
                "count": page.paginator.count,
            },
            "import": {
                "last_attempt": org.inventory_source.last_import_attempt,
                "last_success": org.inventory_source.last_import_success,
                "stale": org.inventory_source.import_stale,
                "error": org.inventory_source.import_error,
                "summary": org.inventory_source.import_summary,
            }
            if hasattr(org, "inventory_source")
            else None,
            "assets": [
                {
                    "id": str(a.pk),
                    "name": a.name,
                    "source_id": str(a.source_id),
                    "instance_id": str(a.source.instance_id) if a.source.instance_id else None,
                    "object_type": a.object_type,
                    "external_id": a.external_id,
                    "state": a.state,
                    "kind": a.kind,
                    "source_url": a.source_url,
                    "upstream": a.upstream_data,
                    "last_seen": a.inventory_seen_at,
                    "missing_since": a.missing_since,
                    "missing_reviewed_at": a.missing_reviewed_at,
                    "software": [
                        {
                            "product": i.product.name,
                            "identifier": i.product.identifier,
                            "version": i.version or None,
                            "component_type": i.component_type,
                            "edition": i.edition or None,
                            "build": i.build or None,
                        }
                        for i in a.installations.all()
                    ],
                }
                for a in page
            ],
        }
    )


@login_required
def api_findings(request, slug):
    org = organization(request, slug)
    return JsonResponse(
        {
            "organization": org.slug,
            "findings": [
                {
                    "id": f.pk,
                    "category": f.category,
                    "status": f.status,
                    "applicability": f.applicability,
                    "analyst_applicability": f.analyst_applicability,
                    "explanation": f.explanation,
                    "source": f.record.source,
                    "record_id": f.record.external_id,
                    "rule": f.rule,
                    "ingested_at": f.record.ingested_at.isoformat(),
                    "evaluated_at": f.evaluated_at.isoformat(),
                }
                for f in visible_findings(request.user, org)
            ],
        }
    )


@login_required
def edit_contact(request, slug, pk):
    org = organization(request, slug)
    require(can_review_contact(request.user, org))
    contact = get_object_or_404(Contact, organization=org, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            changed = form.changed_data
            if changed:
                contact.reviewed_at = contact.reviewed_by = contact.next_review = None
            if "email" in changed:
                contact.reachable_at = None
                ContactToken.objects.filter(contact=contact, used_at__isnull=True).update(
                    used_at=timezone.now()
                )
            if set(changed) & {"availability", "time_zone", "phone", "emergency_phone", "role", "function"}:
                contact.availability_confirmed_at = None
            form.save()
            audit(request.user, org, "contact.updated", contact.pk, fields=changed)
        return redirect("organization", slug=slug)
    return render(request, "portal/form.html", {"form": form, "title": "Update contact details", "org": org})


@login_required
def api_evidence(request, slug, pk):
    org = organization(request, slug)
    finding = get_object_or_404(visible_findings(request.user, org), pk=pk)
    return JsonResponse(
        {
            "source": finding.record.source,
            "record_id": finding.record.external_id,
            "ingested_at": finding.record.ingested_at.isoformat(),
            "record": finding.record.payload,
        }
    )


@login_required
def asset_detail(request, slug, pk):
    org = organization(request, slug)
    asset = get_object_or_404(
        org.assets.select_related("source__instance"),
        pk=pk,
    )
    findings = (
        visible_findings(request.user, org)
        .select_related("installation__asset__source__instance")
        .filter(installation__asset=asset)
        .order_by("-evaluated_at", "pk")
    )
    software = asset.installations.select_related("product", "agent_component__device").order_by(
        "product__name", "pk"
    )
    software_query = request.GET.get("software_q", "")[:128].strip()
    if software_query:
        software = software.filter(
            Q(product__name__icontains=software_query) | Q(product__identifier__icontains=software_query)
        )
    software_page = Paginator(software, 100).get_page(request.GET.get("software_page"))
    from .distro_display import decorate_installations

    software_page.object_list = list(software_page.object_list)
    decorate_installations(request.user, software_page.object_list)
    page = Paginator(severity_first(findings), 25).get_page(request.GET.get("page"))
    for finding in page:
        decorate_finding(finding)
    return render(
        request,
        "portal/asset.html",
        {
            "org": org,
            "asset": asset,
            "facts": asset_context(asset, workspace=True),
            "software_page": software_page,
            "software_query": software_query,
            "agent_device": AgentDevice.objects.filter(asset=asset, organization=org)
            .order_by("-enabled", "-created_at")
            .first(),
            "page": page,
            "editable": can_edit(request.user, org),
        },
    )


@login_required
def edit_local_asset(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    asset = get_object_or_404(org.assets, pk=pk)
    from .forms import ManualAssetForm

    form = (ManualAssetForm if asset.source.mode == "manual" else LocalAssetForm)(
        request.POST or None, instance=asset
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            from .models import InventorySource

            InventorySource.objects.select_for_update().get(pk=asset.source_id)
            current = Asset.objects.select_for_update().get(pk=asset.pk, organization=org)
            for field in form.Meta.fields:
                setattr(current, field, form.cleaned_data[field])
            current.full_clean()
            current.save(update_fields=[*form.Meta.fields, "updated_at"])
            audit(request.user, org, "asset.context_reviewed", current.pk, fields=list(form.Meta.fields))
        return redirect("asset", slug=slug, pk=asset.pk)
    return render(
        request, "portal/form.html", {"org": org, "form": form, "title": f"Local assessment · {asset.name}"}
    )
