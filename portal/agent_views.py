"""Scoped portal pages for managing inventory clients and reading observations."""

import json
import uuid

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import OperationalError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import agent_enrollment_codes, agents, distro_cves
from .access import audit_operator_access, can_operator_review, organizations_for, require
from .agent_api import private
from .agent_protocol import identifier, public_key
from .models import AgentComponent, AgentDevice, AgentEnrollment, Asset, Installation
from .overview_queries import bounded_list, read_snapshot


class EnrollmentForm(forms.Form):
    asset = forms.ModelChoiceField(
        queryset=Asset.objects.none(),
        required=False,
        label="Existing asset (leave empty for explicitly approved new-host registration)",
    )
    new_asset_kind = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Use existing asset"),
            ("vm", "New virtual machine"),
            ("server", "New physical server"),
            ("desktop", "New desktop"),
            ("laptop", "New laptop"),
        ],
    )
    public_key = forms.CharField(
        max_length=44,
        help_text="Paste the public key printed by the Linux or Windows client init command. Never paste a private key.",
    )
    acknowledged = forms.BooleanField(
        label="I authorize this device to report observations for this asset. Software version ownership is assigned separately."
    )

    def __init__(self, *args, org, asset_query="", selected_asset="", **kwargs):
        super().__init__(*args, **kwargs)
        scoped = Asset.objects.filter(organization=org, source__organization=org, lifecycle="active")
        selection = self.data.get("asset", "") if self.is_bound else selected_asset
        if selection:
            try:
                selection = str(identifier(selection))
            except ValueError:
                selection = ""
        choices = scoped.filter(name__icontains=asset_query).order_by("name", "pk")
        from django.db.models import Q

        allowed = Q(pk__in=choices.values("pk")[:250])
        if selection:
            allowed |= Q(pk=selection)
            self.initial["asset"] = selection
        self.fields["asset"].queryset = scoped.filter(allowed).order_by("name", "pk")

    def clean(self):
        data = super().clean()
        if not data.get("asset") and not data.get("new_asset_kind"):
            raise forms.ValidationError("Select an existing asset or explicitly approve a new host type")
        return data

    def clean_public_key(self):
        key = self.cleaned_data["public_key"]
        public_key(key)
        return key


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def center(request, slug):
    org = get_object_or_404(organizations_for(request.user), slug=slug)
    manage = agents.administrator(request.user, org)
    # Browsing company-owned source data follows the existing workspace/operator policy.
    require(
        manage
        or can_operator_review(request.user, org)
        or org.membership_set.filter(user=request.user).exists()
    )
    audit_operator_access(request.user, org)
    asset_query = request.GET.get("asset_q", "")[:128].strip()
    form = EnrollmentForm(
        request.POST if request.POST.get("action") == "enroll" else None,
        org=org,
        asset_query=asset_query,
        selected_asset=request.GET.get("asset", ""),
    )
    if request.method == "POST":
        require(manage)
        try:
            action = request.POST.get("action")
            if action == "enroll" and form.is_valid():
                grant, token = agents.create_enrollment(
                    request.user,
                    org,
                    form.cleaned_data["asset"],
                    form.cleaned_data["public_key"],
                    new_asset_kind=form.cleaned_data.get("new_asset_kind", ""),
                )
                payload = agent_enrollment_codes.payload(grant, token)
                if request.POST.get("delivery") == "code":
                    return private(
                        render(
                            request,
                            "portal/agent_enrollment.html",
                            {
                                "org": org,
                                "grant": grant,
                                "code": agent_enrollment_codes.encode(payload),
                                "register_host": grant.asset_id is None,
                            },
                        )
                    )
                response = private(JsonResponse(payload))
                response["Content-Disposition"] = 'attachment; filename="bearings-enrollment.json"'
                return response
            if action == "cancel":
                grant = get_object_or_404(AgentEnrollment, pk=request.POST.get("grant"), organization=org)
                agents.cancel_enrollment(request.user, org, grant.pk)
                messages.success(request, "Enrollment cancelled; any already-enrolled device was revoked.")
            elif action == "revoke":
                device = get_object_or_404(AgentDevice, pk=request.POST.get("device"), organization=org)
                agents.revoke(request.user, org, device.pk)
                messages.success(request, "Device revoked; pending observations cannot update software.")
            elif action == "uninstall":
                device = get_object_or_404(AgentDevice, pk=request.POST.get("device"), organization=org)
                if request.POST.get("confirm_uninstall") != "on":
                    raise ValidationError("Confirm removal of the client and its local inventory queue")
                agents.request_uninstall(request.user, org, device.pk)
                messages.success(request, "Device deregistered. Client removal requested.")
            elif action == "software-policy":
                device = get_object_or_404(AgentDevice, pk=request.POST.get("device"), organization=org)
                agents.software_policy(request.user, org, device.pk, request.POST.get("enabled") == "on")
                messages.success(
                    request,
                    "Automatic package inventory updated. Existing manually assigned version ownership is retained.",
                )
                return redirect(request.path + "?device=" + str(device.pk))
            elif action == "detach":
                c = get_object_or_404(
                    AgentComponent, pk=request.POST.get("component"), device__organization=org
                )
                agents.detach(request.user, org, c.pk)
                messages.success(
                    request, "Version ownership released; retained observations and software remain."
                )
            elif action in ("bind", "create"):
                c = get_object_or_404(
                    AgentComponent, pk=request.POST.get("component"), device__organization=org
                )
                agents.bind(
                    request.user,
                    org,
                    c.pk,
                    request.POST.get("installation") or None,
                    create=action == "create",
                )
                messages.success(
                    request, "Software version ownership assigned. Findings remain subject to review."
                )
            elif action != "enroll":
                raise ValidationError("Choose a supported action")
            if action != "enroll":
                return redirect("agent-center", slug=slug)
        except (ValidationError, Installation.DoesNotExist, ValueError, TypeError) as exc:
            messages.error(
                request,
                "; ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "Select an installation on this device",
            )
    devices = (
        AgentDevice.objects.filter(organization=org).select_related("asset", "source").order_by("-created_at")
    )
    selected = None
    components = None
    installations = []
    last_report = None
    if request.GET.get("device"):
        try:
            device_id = uuid.UUID(request.GET["device"])
        except (ValueError, TypeError):
            raise Http404 from None
        selected = get_object_or_404(devices, pk=device_id)
        qs = selected.components.select_related("installation__product", "last_report").order_by(
            "name", "architecture"
        )
        query = request.GET.get("q", "")[:128].strip()
        if query:
            qs = qs.filter(name__icontains=query)
        components = Paginator(qs, 50).get_page(request.GET.get("page"))
        from .windows_cves import resolve

        report_os = {}
        for component in components:
            component.device = selected
            if component.manager == "win-reg" and component.last_report.device_id == selected.pk:
                if component.last_report_id not in report_os:
                    report_os[component.last_report_id] = json.loads(bytes(component.last_report.body))["os"]
                component.windows_mapping = resolve(component, report_os[component.last_report_id])
        installations = list(
            Installation.objects.filter(asset=selected.asset, product__organization=org)
            .select_related("product")
            .order_by("product__name")[:250]
        )
        last_report = selected.reports.order_by("-sequence").first()
        from .windows_updates import presentation

        selected.windows_update_view = presentation(selected)
    from .timelines import report_receipts

    response = private(
        render(
            request,
            "portal/agents.html",
            {
                "org": org,
                "report_timeline": report_receipts(devices.filter(pk=selected.pk) if selected else devices),
                "now": timezone.now(),
                "form": form,
                "asset_query": asset_query,
                "manage": manage,
                "devices": Paginator(devices, 25).get_page(request.GET.get("devices_page")),
                "selected": selected,
                "distro_coverage": distro_cves.coverage(selected) if selected else None,
                "components": components,
                "installations": installations,
                "last_report": last_report,
                "recent_reports": selected.reports.order_by("-sequence")[:10] if selected else [],
                "pending_grants": AgentEnrollment.objects.filter(
                    organization=org, used_at__isnull=True, expires_at__gt=timezone.now()
                ).order_by("expires_at")[:25]
                if manage
                else [],
            },
        )
    )
    response["Referrer-Policy"] = "same-origin"
    return response


@login_required
@never_cache
def kernel_evidence(request, slug, pk):
    from urllib.parse import quote

    from .distro_sources import url_for
    from .models import DistroKernelRevision

    org = get_object_or_404(organizations_for(request.user), slug=slug)
    audit_operator_access(request.user, org)
    from django.db.models import F

    device = get_object_or_404(
        AgentDevice.objects.select_related("asset", "organization", "source"),
        pk=pk,
        organization=org,
        asset__organization=org,
        source__organization=org,
        asset__source_id=F("source_id"),
    )
    coverage = distro_cves.coverage(device)
    kernel = coverage.get("kernel") or {}
    entries = []
    if coverage.get("kernel_current") and kernel.get("evidence_revision"):
        revision = get_object_or_404(DistroKernelRevision, pk=kernel["evidence_revision"], device=device)
        snapshot = revision.snapshot
        if snapshot.get("organization_id") == org.pk and snapshot.get("source_id") == str(device.source_id):
            entries = snapshot.get("matches", [])
    page = Paginator(entries, 50).get_page(request.GET.get("page"))
    for entry in page:
        entry["vendor_url"] = url_for(kernel["feed"]) + "#" + quote(entry["definition"], safe="")
    return private(
        render(
            request,
            "portal/kernel_evidence.html",
            {"org": org, "device": device, "coverage": coverage, "kernel": kernel, "page": page},
        )
    )


@login_required
@never_cache
@require_http_methods(["GET"])
@read_snapshot()
@bounded_list
def lookup_progress(request):
    """Read stored scoped counters only; polling never starts upstream work."""
    from django.db.models import F

    from .distro_evaluation import state as evaluation_state
    from .distro_sources import key_for
    from .models import DistroFeed
    from .ubuntu_status import progress

    raw = request.GET.getlist("device")
    if not raw or len(raw) > 36:
        return private(JsonResponse({"error": "Request 1–36 devices"}, status=400))
    try:
        ids = {uuid.UUID(value) for value in raw if len(value) <= 36}
        if len(ids) != len(set(raw)):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        return private(JsonResponse({"error": "Invalid device selection"}, status=400))
    try:
        devices = list(
            AgentDevice.objects.filter(
                pk__in=ids,
                organization__in=organizations_for(request.user),
                asset__organization_id=F("organization_id"),
                source__organization_id=F("organization_id"),
                asset__source_id=F("source_id"),
            )
            .select_related("organization", "source", "asset")
            .defer("reported_network", "asset__upstream_data")
        )
        if len(devices) != len(ids):
            return private(JsonResponse({"error": "Device selection unavailable"}, status=404))
        for org in {d.organization_id: d.organization for d in devices}.values():
            audit_operator_access(request.user, org)
        rows = progress(ids)
        feeds = {
            f.key: f
            for f in DistroFeed.objects.filter(key__in=[key_for(d.os) for d in devices if key_for(d.os)])
        }
        empty = {"total": 0, "fresh": 0, "pending": 0, "failed": 0, "refresh_errors": 0, "errors": []}
        return private(
            JsonResponse(
                {
                    "schema": "bearings.lookup-progress.v1",
                    "observed_at": timezone.now(),
                    "devices": {
                        str(d.pk): {
                            **rows.get(d.pk, empty),
                            "evaluation": evaluation_state(d, rows.get(d.pk), feeds.get(key_for(d.os))),
                            "evaluation_url": reverse("agent-evaluation", args=[d.organization.slug, d.pk]),
                        }
                        for d in devices
                    },
                }
            )
        )
    except OperationalError:
        response = private(JsonResponse({"error": "Progress temporarily unavailable"}, status=503))
        response["Retry-After"] = "30"
        return response


@login_required
@never_cache
@require_http_methods(["GET"])
@read_snapshot()
@bounded_list
def evaluation_panel(request, slug, pk):
    from django.db.models import F
    from django.template.loader import render_to_string

    org = get_object_or_404(organizations_for(request.user), slug=slug)
    audit_operator_access(request.user, org)
    device = get_object_or_404(
        AgentDevice.objects.select_related("organization", "asset", "source"),
        pk=pk,
        organization=org,
        asset__organization=org,
        source__organization=org,
        asset__source_id=F("source_id"),
    )
    context = distro_cves.coverage(device)
    html = render_to_string(
        "portal/_distro_evaluation.html", {"org": org, "selected": device, "distro_coverage": context}
    )
    return private(
        JsonResponse(
            {
                "schema": "bearings.evaluation-panel.v1",
                "revision": context["evaluation"]["revision"],
                "evaluation": context["evaluation"],
                "html": html,
            }
        )
    )
