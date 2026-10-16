from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .access import (
    audit,
    audit_operator_access,
    can_edit,
    can_operator_review,
    can_review_contact,
    is_analyst,
    organizations_for,
    require,
    visible_findings,
)
from .connectors.http import ConnectorError
from .forms import (
    AssetForm,
    ClaimForm,
    ClaimReviewForm,
    ContactForm,
    FindingReviewForm,
    InstallationForm,
    VulnerabilityForm,
)
from .models import Asset, Contact, ContactToken, InfrastructureClaim, Installation, Product
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


@login_required
def home(request):
    orgs = list(
        organizations_for(request.user).prefetch_related(
            "contacts", "assets", "findings", "inventory_source__instance"
        )
    )
    for org in orgs:
        audit_operator_access(request.user, org)
        org.overdue_count = sum(c.overdue for c in org.contacts.all())
        org.finding_count = (
            visible_findings(request.user, org).exclude(status__in=["resolved", "false_positive"]).count()
        )
    return render(
        request,
        "portal/home.html",
        {"orgs": orgs, "operator": request.user.is_superuser or is_analyst(request.user)},
    )


@login_required
def detail(request, slug):
    org = organization(request, slug)
    return render(
        request,
        "portal/detail.html",
        {
            "org": org,
            "editable": can_edit(request.user, org),
            "inventory_writable": can_edit(request.user, org)
            and hasattr(org, "inventory_source")
            and org.inventory_source.can_write,
            "contact_reviewer": can_review_contact(request.user, org),
            "operator_reviewer": can_operator_review(request.user, org),
            "findings": visible_findings(request.user, org),
            "claim_review_form": ClaimReviewForm(),
            "finding_review_form": FindingReviewForm(),
            "lookup_form": VulnerabilityForm(),
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
        issue_contact_token(request.user, contact)
        messages.success(request, "Verification prepared in the local development mail sink (.local/mail).")
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


def verify_contact(request):
    if request.method == "POST":
        success = redeem_contact_token(request.POST.get("token", ""))
        return render(
            request,
            "portal/verify.html",
            {
                "result": "Development channel confirmation recorded; external reachability remains untested."
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
        messages.error(request, "Enter a CVE identifier, for example CVE-2021-44228.")
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
    return redirect("organization", slug=slug)


@login_required
def api_inventory(request, slug):
    org = organization(request, slug)
    return JsonResponse(
        {
            "organization": org.slug,
            "assets": [
                {
                    "id": str(a.pk),
                    "name": a.name,
                    "source_id": str(a.source_id),
                    "instance_id": str(a.source.instance_id) if a.source.instance_id else None,
                    "object_type": a.object_type,
                    "external_id": a.external_id,
                    "state": a.state,
                    "software": [
                        {
                            "product": i.product.name,
                            "identifier": i.product.identifier,
                            "version": i.version or None,
                        }
                        for i in a.installations.select_related("product")
                    ],
                }
                for a in org.assets.select_related("source")
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
            if set(changed) & {"availability", "time_zone", "phone", "emergency_phone", "role"}:
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
