from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .access import audit_operator_access, organizations_for, can_edit
from .overview import company_state, priority_assets


@login_required
def overview(request):
    orgs = organizations_for(request.user).order_by("name", "pk")
    selected = request.GET.get("organization", "")
    if selected:
        org = get_object_or_404(orgs, slug=selected)
        orgs = orgs.filter(pk=org.pk)
    query = request.GET.get("q", "")[:160].strip()
    if query:
        orgs = orgs.filter(name__icontains=query)
    page = Paginator(orgs, 12).get_page(request.GET.get("page"))
    companies = []
    for org in page:
        audit_operator_access(request.user, org)
        state = company_state(request.user, org)
        state["editable"] = can_edit(request.user, org)
        companies.append(state)
    return render(
        request,
        "portal/overview.html",
        {
            "companies": companies,
            "page": page,
            "priority_assets": priority_assets(
                request.user, orgs.filter(pk__in=[s["org"].pk for s in companies])
            ),
            "updated_at": timezone.now(),
            "query": query,
            "selected": selected,
        },
    )
