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


def remembered_company(request):
    value = request.session.get(SESSION_COMPANY)
    if not isinstance(value, int) or isinstance(value, bool) or not request.user.is_authenticated:
        return None
    return organizations_for(request.user).filter(pk=value).first()


def company_url(org):
    return reverse("overview") + "?" + urlencode({"organization": org.slug})


def view_switch(request, selected, operator):
    """A view selector, never impersonation or an authorization override."""
    if not operator:
        return {}
    if selected is None:
        own = (
            Membership.objects.filter(
                user=request.user, organization__slug="circl", organization__merged_into=None
            )
            .select_related("organization")
            .first()
        )
        selected = own.organization if own else None
    match = request.resolver_match
    route = match.url_name if match else ""
    company_page = bool(
        selected
        and (
            (route == "overview" and request.GET.get("organization") == selected.slug)
            or (match and match.kwargs.get("slug") == selected.slug)
        )
    )
    national_page = request.path.startswith(("/circl/", "/operator/", "/admin/"))
    return {
        "switch_company_label": f"{selected.name} infrastructure" if selected else "Company infrastructure",
        "switch_company_url": company_url(selected)
        if selected
        else reverse("workspace-switch") + "?open=company",
        "switch_company_active": company_page and not national_page,
        "switch_national_active": national_page,
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
