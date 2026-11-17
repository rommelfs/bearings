from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .access import audit, can_edit, organizations_for, require, audit_operator_access, visible_findings
from .models import Product, ProductWatch, Installation
from .views import organization


class WatchForm(forms.ModelForm):
    class Meta:
        model = ProductWatch
        fields = ["vendor", "product_key", "enabled", "interval_minutes"]
        help_texts = {
            "vendor": "Exact public Vulnerability-Lookup vendor key; sent to the public service.",
            "product_key": "Exact public product key. This mapping asserts product identity, not affectedness.",
        }


@login_required
def center(request):
    orgs = organizations_for(request.user)
    qs = (
        Product.objects.filter(organization__in=orgs)
        .select_related("organization", "watch")
        .order_by("organization__name", "name", "pk")
    )
    if request.GET.get("organization"):
        org = organization(request, request.GET["organization"])
        qs = qs.filter(organization=org)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    for product in page:
        product.editable = can_edit(request.user, product.organization)
        product.pending_reviews = (
            visible_findings(request.user, product.organization)
            .filter(installation__product=product, discovery__review_required=True)
            .count()
        )
        audit_operator_access(request.user, product.organization)
    return render(request, "portal/discovery.html", {"page": page})


@login_required
def configure(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    product = get_object_or_404(Product, pk=pk, organization=org)
    watch = ProductWatch.objects.filter(product=product).first() or ProductWatch(
        product=product, source_url=settings.VULNERABILITY_LOOKUP_URL.rstrip("/")
    )
    form = WatchForm(request.POST or None, instance=watch)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            Product.objects.select_for_update().get(pk=product.pk)
            current = ProductWatch.objects.select_for_update().filter(product=product).first()
            if current is None:
                current = ProductWatch(
                    product=product, source_url=settings.VULNERABILITY_LOOKUP_URL.rstrip("/")
                )
            identity_changed = (current.vendor, current.product_key) != (
                form.cleaned_data["vendor"],
                form.cleaned_data["product_key"],
            )
            for field in form.Meta.fields:
                setattr(current, field, form.cleaned_data[field])
            current.requested = True
            if identity_changed:
                current.last_success, current.summary = None, {}
            current.full_clean()
            current.save()
            audit(
                request.user,
                org,
                "vulnerability.watch_configured",
                current.pk,
                vendor=current.vendor,
                product=current.product_key,
                enabled=current.enabled,
            )
        messages.success(
            request,
            "Product watch saved and queued. Only public product keys are sent; findings require review.",
        )
        return redirect("discovery")
    return render(
        request,
        "portal/form.html",
        {"form": form, "org": org, "title": f"Automatic CVE discovery · {product.name}"},
    )


@login_required
@require_POST
def refresh(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    with transaction.atomic():
        watch = get_object_or_404(ProductWatch.objects.select_for_update(), pk=pk, product__organization=org)
        watch.requested = True
        watch.save(update_fields=["requested"])
        audit(request.user, org, "vulnerability.watch_requested", watch.pk)
    return redirect("discovery")


class VersionForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ["version", "edition", "build"]


@login_required
def version(request, slug, pk):
    org = organization(request, slug)
    require(can_edit(request.user, org))
    installation = get_object_or_404(Installation, pk=pk, asset__organization=org, product__organization=org)
    form = VersionForm(request.POST or None, instance=installation)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            current = Installation.objects.select_for_update().get(pk=pk)
            for field in form.Meta.fields:
                setattr(current, field, form.cleaned_data[field])
            current.full_clean()
            current.save(update_fields=form.Meta.fields)
            ProductWatch.objects.filter(product=current.product).update(requested=True)
            audit(request.user, org, "installation.version_updated", current.pk)
        return redirect("asset", slug=slug, pk=installation.asset_id)
    return render(
        request,
        "portal/form.html",
        {"form": form, "org": org, "title": f"Installed version · {installation.product.name}"},
    )
