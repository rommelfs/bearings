from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .access import audit, is_analyst, organizations_for
from .models import Membership
from .overview import company_states, priority_assets


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
    page.object_list = list(page.object_list.select_related("inventory_source__instance"))
    if request.user.is_superuser:
        audited_orgs = page.object_list
    elif is_analyst(request.user):
        member_ids = set(
            Membership.objects.filter(user=request.user, organization__in=page.object_list).values_list(
                "organization_id", flat=True
            )
        )
        audited_orgs = [org for org in page if org.pk not in member_ids]
    else:
        audited_orgs = []
    for org in audited_orgs:
        audit(request.user, org, "operator.access")
    companies = company_states(request.user, page.object_list)
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
