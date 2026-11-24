"""Explicit navigation between company infrastructure and platform work; grants are unchanged."""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from urllib.parse import urlencode
from .access import organizations_for, is_analyst, require, audit
from .circl_views import private_response
from .models import Membership

SESSION_COMPANY = "bearings_workspace_company"
SESSION_MODE = "bearings_workspace_mode"


def remembered_company(request):
    value = request.session.get(SESSION_COMPANY)
    if not isinstance(value, int) or isinstance(value, bool) or not request.user.is_authenticated:
        return None
    return organizations_for(request.user).filter(pk=value).first()


def company_url(org):
    return reverse("overview") + "?" + urlencode({"organization": org.slug})


def view_switch(request, selected, operator):
    """Resolve a reauthorized view preference; it never changes a user's grants."""
    if not request.user.is_authenticated:
        return {}
    match = request.resolver_match
    route = match.url_name if match else ""
    scoped_queries = {
        "overview",
        "discovery",
        "issues",
        "risk-register",
        "company-actions",
        "notifications",
        "plum",
        "linux-client-downloads",
        "windows-client-downloads",
        "client-platforms",
        "client-rollouts",
        "client-profiles",
    }
    selector = (match.kwargs.get("slug") if match else None) or (
        request.GET.get("organization", "") if route in scoped_queries else ""
    )
    actual = None
    if selector:
        criteria = Q(slug=selector)
        if str(selector).isascii() and str(selector).isdigit() and len(str(selector)) <= 19:
            criteria |= Q(pk=int(selector))
        cached = getattr(request, "_navigation_organization", None)
        actual = (
            cached
            if cached and str(selector) in {cached.slug, str(cached.pk)}
            else organizations_for(request.user).filter(criteria).first()
        )
        if actual:
            selected = actual
            if operator and request.session.get(SESSION_COMPANY) != selected.pk:
                request.session[SESSION_COMPANY] = selected.pk
    if selected is None and operator:
        own = Membership.objects.filter(
            user=request.user, organization__slug="circl", organization__merged_into=None
        )
        if not request.user.is_superuser:
            own = own.filter(organization__operator_visibility=True)
        membership = own.select_related("organization").first()
        selected = membership.organization if membership else None
    national_page = (
        request.path.startswith(("/circl/", "/operator/", "/admin/"))
        or request.GET.get("workspace") == "national"
    )
    # Shared collection routes without an organization are explicitly the wide
    # view, even if another browser tab last visited a company workspace.
    wide = (
        route
        in {
            "home",
            "inventory",
            "overview",
            "discovery",
            "issues",
            "risk-register",
            "company-actions",
            "notifications",
            "plum",
            "linux-client-downloads",
        }
        and not actual
    )
    company_page = bool(
        selected
        and not national_page
        and not wide
        and (
            actual
            or request.GET.get("workspace") == "company"
            or request.session.get(SESSION_MODE) == "company"
        )
    )
    mode = "company" if company_page else "national"
    if operator and request.session.get(SESSION_MODE) != mode:
        request.session[SESSION_MODE] = mode
    return {
        "switch_company_label": f"{selected.name} infrastructure" if selected else "Company infrastructure",
        "switch_company_url": company_url(selected)
        if selected
        else reverse("workspace-switch") + "?open=company",
        "switch_company_active": company_page,
        "switch_national_active": bool(operator and not company_page),
        "navigation_company": selected if company_page else None,
        "workspace_national": bool(operator and not company_page),
        "selected_company_workspace": selected,
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def center(request):
    operator = request.user.is_active and (request.user.is_superuser or is_analyst(request.user))
    orgs = organizations_for(request.user)
    selected = remembered_company(request)
    if request.method == "POST":
        if request.POST.get("action") == "platform":
            require(operator)
            audit(request.user, None, "workspace.platform_opened")
            return redirect("circl-overview")
        require(request.POST.get("action") == "company")
        value = request.POST.get("organization", "")
        if not value.isascii() or not value.isdigit() or len(value) > 19:
            require(False)
        org = get_object_or_404(orgs, pk=int(value))
        request.session[SESSION_COMPANY] = org.pk
        audit(request.user, org, "workspace.company_opened", org.pk)
        return redirect(company_url(org))
    if request.GET.get("open") == "company" and selected:
        return redirect(company_url(selected))
    query = request.GET.get("q", "")[:160].strip()
    if query:
        criteria = Q(name__icontains=query) | Q(slug__icontains=query)
        if query.isascii() and query.isdigit() and len(query) <= 19:
            criteria |= Q(pk=int(query))
        orgs = orgs.filter(criteria)
    rows = list(orgs.select_related("inventory_source").order_by("name", "pk")[:26])
    roles = dict(
        Membership.objects.filter(user=request.user, organization__in=rows[:25]).values_list(
            "organization_id", "role"
        )
    )
    for org in rows[:25]:
        org.workspace_role = dict(Membership.ROLES).get(
            roles.get(org.pk), "Platform access; no company membership"
        )
    return private_response(
        render(
            request,
            "portal/workspaces.html",
            {
                "workspace_companies": rows[:25],
                "workspace_more": len(rows) > 25,
                "workspace_operator": operator,
                "query": query,
                "remembered": selected,
            },
        )
    )
