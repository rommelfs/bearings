from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.shortcuts import render
from .access import organizations_for, audit_operator_access
from .models import CompanyInstance, FederatedReport


@login_required
def center(request):
    sources = list(CompanyInstance.objects.filter(organization__in=organizations_for(request.user)))
    for source in sources:
        source.stale = (
            not source.enabled
            or bool(source.error)
            or not source.last_success
            or source.last_success < timezone.now() - timedelta(hours=1)
        )
        audit_operator_access(request.user, source.organization)
    # Company-reported data is never mixed into authoritative local NetBox assets or outbound messages.
    page = Paginator(
        FederatedReport.objects.filter(source__in=sources, source__enabled=True)
        .select_related("source__organization")
        .order_by("-seen_at", "pk"),
        25,
    ).get_page(request.GET.get("page"))
    return render(request, "portal/companies.html", {"sources": sources, "page": page})
