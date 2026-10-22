"""Browser-only hand-off. Each application authenticates and authorizes its own user."""

import os
from urllib.parse import urlsplit
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from .access import audit, audit_operator_access, is_analyst, organizations_for
from .browser_policy import browser_base, origin
from .models import FlowIntelInstance, InventorySource, RTInstance


def applications(actor):
    orgs = organizations_for(actor)
    result = []

    def add(product, instance, path, login_path, organizations):
        # Never expose internal API endpoints as browser destinations.
        if not instance.browser_url:
            return
        try:
            base = browser_base(instance.browser_url)
            parsed = urlsplit(base)
            app_origin = origin(f"https://{parsed.netloc}")
        except ValueError:
            return
        key = f"{product}-{instance.pk}"
        result.append(
            {
                "key": key,
                "product": product,
                "label": {"netbox": "NetBox", "flowintel": "FlowIntel", "rt": "RT", "rtir": "RTIR"}[product],
                "name": instance.name,
                "url": base + path,
                "login_url": base + login_path,
                "origin": app_origin,
                "organizations": list(organizations),
                "embeddable": app_origin in settings.CANVAS_FRAME_ORIGINS
                and bool(settings.CANVAS_ORIGIN)
                and app_origin != settings.CANVAS_ORIGIN,
                "workspace_url": reverse("application", args=[key]),
            }
        )

    sources = (
        InventorySource.objects.filter(organization__in=orgs, instance__enabled=True)
        .select_related("instance", "organization")
        .order_by("instance__name", "organization__name")
    )
    grouped = {}
    for source in sources:
        row = grouped.setdefault(source.instance_id, [source.instance, []])
        row[1].append(source.organization)
    for instance, organizations in grouped.values():
        add("netbox", instance, "/", "/login/", organizations)
    operator = (actor.is_superuser or is_analyst(actor)) and orgs.filter(operator_visibility=True).exists()
    if operator:
        for instance in FlowIntelInstance.objects.filter(enabled=True).order_by("name"):
            if instance.available:
                add("flowintel", instance, "/", "/account/login", [])
    connections = RTInstance.objects.filter(enabled=True).filter(Q(organization__in=orgs))
    if operator:
        connections = RTInstance.objects.filter(enabled=True).filter(
            Q(organization__in=orgs) | Q(organization__isnull=True)
        )
    for instance in connections.select_related("organization").order_by("product", "name"):
        if instance.product == "rtir" and not operator:
            continue
        if (
            os.getenv("BEARINGS_DEV_STACK") == "1"
            and instance.name.startswith("bundled-")
            and os.getenv("BEARINGS_RT") != "1"
        ):
            continue
        add(
            instance.product,
            instance,
            "/RTIR/" if instance.product == "rtir" else "/",
            "/RTIR/" if instance.product == "rtir" else "/",
            [instance.organization] if instance.organization_id else [],
        )
    return result


@login_required
@require_GET
def canvas(request, key=None):
    entries = applications(request.user)
    selected = next((entry for entry in entries if entry["key"] == key), None)
    if key and selected is None:
        raise Http404
    # Host + scheme both matter for SameSite cookies. The target is operator-owned,
    # never taken from next/url/query parameters or an upstream response.
    if settings.CANVAS_ORIGIN and request.build_absolute_uri("/").rstrip("/") != settings.CANVAS_ORIGIN:
        return redirect(settings.CANVAS_ORIGIN + request.path)
    if selected:
        for org in selected["organizations"]:
            audit_operator_access(request.user, org)
        audit(request.user, None, "application.workspace_opened", selected["key"])
    else:
        seen = set()
        for entry in entries:
            for org in entry["organizations"]:
                if org.pk not in seen:
                    audit_operator_access(request.user, org)
                    seen.add(org.pk)
    response = render(
        request,
        "portal/applications.html",
        {
            "applications": entries,
            "selected": selected,
            "show_frame": bool(selected and selected["embeddable"] and request.GET.get("show") == "1"),
        },
    )
    allowed = selected["origin"] if selected and selected["embeddable"] else "'none'"
    response["Content-Security-Policy"] = (
        f"frame-src {allowed}; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; script-src 'self'; style-src 'self'"
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response
