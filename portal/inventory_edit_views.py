"""Inventory edits and local or upstream registration requests."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import (
    audit,
    can_edit,
    organization,
    require,
)
from .connectors.http import ConnectorError
from .forms import (
    AssetForm,
    InstallationForm,
    LocalAssetForm,
    MissingReviewForm,
)
from .models import (
    Asset,
    Product,
)
from .services import (
    submit_asset,
)


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
            from django.core.exceptions import ValidationError

            from .models import ProductWatch
            from .product_matching import ensure_watch

            try:
                selected = (
                    (form.cleaned_data.get("vendor"), form.cleaned_data.get("product_key"))
                    if form.cleaned_data.get("vendor")
                    else None
                )
                watch, _ = ensure_watch(product, request.user, identity=selected)
                if watch:
                    messages.success(
                        request,
                        "Software saved. Automatic CVE monitoring is queued."
                        if watch.enabled
                        else "Software saved. Its existing CVE monitoring is paused; enable it in Automatic CVE discovery when ready.",
                    )
                else:
                    messages.warning(
                        request,
                        "Software saved. Choose its manufacturer/product mapping in Automatic CVE discovery to enable monitoring.",
                    )
            except ValidationError:
                messages.warning(
                    request,
                    "Software saved. Review Automatic CVE discovery to complete monitoring; any saved mapping was preserved.",
                )

            ProductWatch.objects.filter(product=product).update(requested=True)
            audit(request.user, org, "software.installed", installation.pk)
        return redirect("organization", slug=slug)
    return render(
        request,
        "portal/installation_form.html",
        {"form": form, "title": f"Software on {asset.name}", "org": org, "asset": asset},
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


@login_required
@require_POST
def installation_catalog(request, slug, pk):
    """Search before creating software; only explicit public search terms leave Bearings."""
    from django.conf import settings

    from .connectors.vulnerability_lookup import browse_products

    org = organization(request, slug)
    require(can_edit(request.user, org))
    asset = get_object_or_404(Asset, pk=pk, organization=org)
    try:
        result = browse_products(
            settings.VULNERABILITY_LOOKUP_URL,
            kind=request.POST.get("kind", "vendors"),
            query=request.POST.get("q", ""),
            vendor=request.POST.get("vendor", ""),
            page=int(request.POST.get("page", "1")),
        )
    except (ConnectorError, ValueError):
        return JsonResponse(
            {
                "error": "Product catalog unavailable or search invalid. Enter a CPE directly or retry; your form is retained."
            },
            status=400,
        )
    if request.POST.get("kind") == "products":
        from .product_matching import catalog_cpe

        for item in result["results"]:
            item["identifier"] = catalog_cpe(request.POST.get("vendor", ""), item["key"])
    audit(request.user, org, "vulnerability.installation_catalog_searched", asset.pk)
    return JsonResponse(result)
