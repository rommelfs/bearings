from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from .access import organizations_for, require
from .demo_data import purge, removal_plan, unmanaged_fixtures
from .models import DemoDataset


@login_required
def index(request):
    require(request.user.is_active and request.user.is_superuser)
    dataset = DemoDataset.objects.filter(key="explore-v1").first()
    if request.method == "POST":
        require(request.POST.get("confirmation") == "REMOVE SYNTHETIC DATA")
        if dataset:
            try:
                purge(request.user, dataset.key, request.POST.get("fingerprint", ""))
                messages.success(
                    request,
                    "Tracked synthetic data removed. Automatic reseeding remains disabled. Audit history retained.",
                )
                return redirect("demo-data")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
    plan = removal_plan(dataset)[0] if dataset else None
    return render(request, "portal/demo_data.html", {"plan": plan, "legacy": unmanaged_fixtures()})


@login_required
def explore(request):
    from django.db.models import Count
    from .models import DemoObject, Asset, NotificationDelivery
    from .notifications import authorized_delivery
    from .issues import visible_issues

    dataset = DemoDataset.objects.filter(key="explore-v1", state="active").first()
    ids = (
        list(
            DemoObject.objects.filter(dataset=dataset, model_label="portal.organization").values_list(
                "object_pk", flat=True
            )
        )
        if dataset
        else []
    )
    orgs = (
        organizations_for(request.user)
        .filter(pk__in=ids)
        .annotate(asset_count=Count("assets", distinct=True))
        .order_by("name")
    )
    delivery_ids = (
        list(
            DemoObject.objects.filter(dataset=dataset, model_label="portal.notificationdelivery").values_list(
                "object_pk", flat=True
            )
        )
        if dataset
        else []
    )
    candidates = (
        NotificationDelivery.objects.filter(pk__in=delivery_ids, organization__in=orgs)
        .select_related("organization", "contact")
        .order_by("organization__name", "pk")
    )
    previews = [row for row in candidates if authorized_delivery(request.user, row)][:4]
    return render(
        request,
        "portal/demo_explore.html",
        {
            "demo_orgs": orgs,
            "demo_previews": previews,
            "demo_assets": Asset.objects.filter(organization__in=orgs).count(),
            "demo_issues": visible_issues(request.user).filter(organization__in=orgs).count(),
            "demo_installed": bool(dataset),
        },
    )
