"""Organization-scoped inventory, findings and evidence responses."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .access import (
    organization,
    visible_findings,
)


@login_required
def api_inventory(request, slug):
    org = organization(request, slug)
    page = Paginator(
        org.assets.select_related("source__instance")
        .prefetch_related("installations__product")
        .order_by("name", "pk"),
        100,
    ).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "organization": org.slug,
            "pagination": {
                "page": page.number,
                "pages": page.paginator.num_pages,
                "count": page.paginator.count,
            },
            "import": {
                "last_attempt": org.inventory_source.last_import_attempt,
                "last_success": org.inventory_source.last_import_success,
                "stale": org.inventory_source.import_stale,
                "error": org.inventory_source.import_error,
                "summary": org.inventory_source.import_summary,
            }
            if hasattr(org, "inventory_source")
            else None,
            "assets": [
                {
                    "id": str(a.pk),
                    "name": a.name,
                    "source_id": str(a.source_id),
                    "instance_id": str(a.source.instance_id) if a.source.instance_id else None,
                    "object_type": a.object_type,
                    "external_id": a.external_id,
                    "state": a.state,
                    "kind": a.kind,
                    "source_url": a.source_url,
                    "upstream": a.upstream_data,
                    "last_seen": a.inventory_seen_at,
                    "missing_since": a.missing_since,
                    "missing_reviewed_at": a.missing_reviewed_at,
                    "software": [
                        {
                            "product": i.product.name,
                            "identifier": i.product.identifier,
                            "version": i.version or None,
                            "component_type": i.component_type,
                            "edition": i.edition or None,
                            "build": i.build or None,
                        }
                        for i in a.installations.all()
                    ],
                }
                for a in page
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
