import json
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from . import plum
from .access import audit_operator_access, can_edit, can_operator_review, organizations_for, require
from .connectors.http import ConnectorError
from .models import PlumInstance
from .views import organization


class ImportForm(forms.Form):
    source = forms.ModelChoiceField(queryset=PlumInstance.objects.none())
    file = forms.FileField(label="Plum InfoIP result or bounded full JSON export")

    def __init__(self, *args, actor, org, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = PlumInstance.objects.filter(
            pk__in=[
                source.pk
                for source in PlumInstance.objects.filter(enabled=True)
                if plum.source_allowed(actor, org, source)
            ]
        )


@login_required
def center(request):
    qs = plum.visible_snapshots(request.user).order_by("-window_stop", "-ingested_at", "pk")
    org_filter = request.GET.get("organization", "")
    if org_filter:
        org = get_object_or_404(organizations_for(request.user), slug=org_filter)
        qs = qs.filter(organization=org)
    query = request.GET.get("ip", "")[:100]
    if query:
        try:
            qs = qs.filter(ip=plum.normalize("ip", query))
        except ValidationError:
            qs = qs.none()
            messages.error(request, "Enter one valid IP address")
    orgs = list(organizations_for(request.user))
    for org in orgs:
        org.issue_editable = can_edit(request.user, org) or can_operator_review(request.user, org)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    for org in organizations_for(request.user):
        audit_operator_access(request.user, org)
    return render(
        request,
        "portal/plum.html",
        {
            "page": page,
            "orgs": orgs,
            "organization_filter": org_filter,
            "ip_filter": query,
        },
    )


@login_required
def detail(request, slug, pk):
    org = organization(request, slug)
    snapshot = get_object_or_404(plum.visible_snapshots(request.user), pk=pk, organization=org)
    previous = (
        plum.visible_snapshots(request.user)
        .filter(
            organization=org,
            source=snapshot.source,
            ip=snapshot.ip,
            asset_id=snapshot.asset_id,
            window_stop__lt=snapshot.window_stop,
        )
        .order_by("-window_stop", "-ingested_at")
        .first()
    )
    return render(
        request,
        "portal/plum_snapshot.html",
        {
            "observation": snapshot,
            "org": org,
            "baseline": previous,
            "changes": plum.compare(snapshot, previous),
            "can_review": can_edit(request.user, org) or can_operator_review(request.user, org),
        },
    )


@login_required
def upload(request, slug):
    org = organization(request, slug)
    require(can_edit(request.user, org) or can_operator_review(request.user, org))
    form = ImportForm(request.POST or None, request.FILES or None, actor=request.user, org=org)
    if request.method == "POST" and form.is_valid():
        try:
            file = form.cleaned_data["file"]
            if file.size > 2_000_000:
                raise ValidationError(
                    "Browser import limit is 2 MB; partition the customer/time export or use the bounded operator command"
                )
            payload = json.loads(file.read(2_000_001))
            if isinstance(payload, dict) and "results" in payload:
                observations = plum.import_export(request.user, org, form.cleaned_data["source"], payload)
            else:
                observations = [plum.ingest(request.user, org, form.cleaned_data["source"], payload)]
            messages.success(
                request, f"Imported {len(observations)} scoped observations. No targets or scans submitted."
            )
            return redirect(
                "plum",
            )
        except (ValueError, ValidationError, ConnectorError) as exc:
            form.add_error(
                None,
                "; ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "Import failed; validate JSON/schema and source policy. Existing observations retained.",
            )
    return render(request, "portal/plum_import.html", {"form": form, "org": org})


@login_required
@require_POST
def review(request, slug, pk):
    org = organization(request, slug)
    snapshot = get_object_or_404(plum.visible_snapshots(request.user), pk=pk, organization=org)
    try:
        port = int(request.POST.get("port", ""))
        protocol = request.POST.get("protocol", "")
        require(protocol in {"tcp", "udp", "unknown"})
        issue = plum.create_review(
            request.user,
            snapshot,
            port,
            protocol,
            request.POST.get("hostname", "")[:254],
            request.POST.get("reason", "")[:4001],
        )
        return redirect("issue", slug=slug, pk=issue.pk)
    except (ValueError, ValidationError) as exc:
        messages.error(
            request,
            "; ".join(exc.messages)
            if isinstance(exc, ValidationError)
            else "Choose a valid observation and review reason",
        )
    return redirect("plum-snapshot", slug=slug, pk=pk)


@login_required
def evidence(request, slug, pk):
    org = organization(request, slug)
    snapshot = get_object_or_404(plum.visible_snapshots(request.user), pk=pk, organization=org)
    return JsonResponse(
        {
            "schema": "bearings.plum-observation/v1",
            "id": str(snapshot.pk),
            "source": snapshot.source.name,
            "source_digest": snapshot.source_digest,
            "ip": snapshot.ip,
            "window_start": snapshot.window_start,
            "window_stop": snapshot.window_stop,
            "state": snapshot.state,
            "report_count": snapshot.report_count,
            "ingested_at": snapshot.ingested_at,
            "asset_id": str(snapshot.asset_id) if snapshot.asset_id else None,
            "ports": snapshot.ports,
            "coverage": "Positive history/export evidence; complete scan coverage is not asserted",
        }
    )
