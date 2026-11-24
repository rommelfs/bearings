"""Machine endpoints accept only signed HTTPS requests; management uses normal scoped sessions/CSRF."""

import uuid
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError
from django.http import JsonResponse, Http404
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST, require_http_methods
from http_message_signatures.exceptions import HTTPMessageSignaturesException
from . import agents, agent_enrollment_codes, distro_cves
from .agent_protocol import MAX_BYTES, verify, decode, public_key, identifier
from .access import organizations_for, require, can_operator_review, audit_operator_access
from .overview_queries import bounded_list, read_snapshot
from .models import AgentDevice, AgentEnrollment, AgentComponent, AgentReport, Asset, Installation, AgentFleet


def private(response):
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Referrer-Policy"] = "no-referrer"
    return response


def body(request, limit=MAX_BYTES):
    if not request.is_secure():
        raise ValueError("HTTPS required")
    size = int(request.META.get("CONTENT_LENGTH", "0"))
    if not 0 < size <= limit:
        raise ValueError("Invalid content length")
    raw = request.read(limit + 1)
    if len(raw) != size:
        raise ValueError("Invalid body size")
    return raw


@csrf_exempt
@require_POST
@sensitive_variables()
def fleet_bootstrap(request):
    try:
        raw = body(request, 4096)
        data = decode(raw)
        if (
            not isinstance(data, dict)
            or set(data) != {"schema", "public_key", "request_id"}
            or data["schema"] != "bearings.agent.bootstrap.v1"
        ):
            raise ValueError("Invalid bootstrap")
        credential = request.headers.get("Authorization", "")
        if not credential.startswith("Bearer ") or len(credential) > 150:
            raise ValueError("Invalid authorization")
        identity, secret = credential[7:].split(".")
        pk = identifier(identity)
        public_key(data["public_key"])
        verify(request, raw, "fleet:" + str(pk), data["public_key"])
        from .agent_fleets import issue

        return private(JsonResponse(issue(pk, secret, data["public_key"], data["request_id"])))
    except (
        ValueError,
        TypeError,
        KeyError,
        ValidationError,
        PermissionDenied,
        AgentFleet.DoesNotExist,
        IntegrityError,
        HTTPMessageSignaturesException,
    ):
        return private(JsonResponse({"error": "Rollout registration unavailable"}, status=403))
    except OperationalError:
        return private(JsonResponse({"error": "Temporarily unavailable"}, status=503))


@csrf_exempt
@require_POST
@sensitive_variables()
def enrollment(request):
    try:
        raw = body(request)
        credential = request.headers.get("Authorization", "")
        if not credential.startswith("Bearer ") or len(credential) > 150:
            raise ValueError("Invalid grant")
        identity, secret = credential[7:].split(".")
        pk = uuid.UUID(identity)
        grant = AgentEnrollment.objects.get(pk=pk)
        data = decode(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid enrollment")
        key = data.get("public_key") if grant.claim_key_on_redeem else grant.public_key
        verify(request, raw, "enroll:" + str(pk), key)
        device = agents.redeem(
            pk,
            secret,
            raw,
            request.headers["Signature-Input"],
            request.headers["Signature"],
            request.build_absolute_uri(),
        )
        return private(
            JsonResponse(
                {
                    "schema": "bearings.agent.enrolled.v1",
                    "device_id": str(device.pk),
                    "asset_id": str(device.asset_id),
                    "expires_at": device.expires_at.isoformat(),
                }
            )
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        ValidationError,
        PermissionDenied,
        AgentEnrollment.DoesNotExist,
        AgentDevice.DoesNotExist,
        HTTPMessageSignaturesException,
        IntegrityError,
    ):
        return private(JsonResponse({"error": "Enrollment unavailable"}, status=403))
    except OperationalError:
        return private(JsonResponse({"error": "Temporarily unavailable"}, status=503))


def authenticate(request):
    raw = body(request)
    key = request.headers.get("X-Bearings-Key", "")
    if not key.startswith("device:") or len(key) != 43:
        raise ValueError("Invalid key")
    device = AgentDevice.objects.select_related("organization", "asset", "source").get(pk=uuid.UUID(key[7:]))
    if not agents.current(device):
        raise ValueError("Device unavailable")
    verify(request, raw, key, device.public_key)
    return device, raw


@csrf_exempt
@require_POST
def reports(request):
    try:
        device, raw = authenticate(request)
        row = agents.receive(
            device.pk,
            raw,
            request.headers["Signature-Input"],
            request.headers["Signature"],
            request.build_absolute_uri(),
            request.headers["Content-Type"],
        )
        return private(JsonResponse(agents.receipt(row), status=202 if row.status == "pending" else 200))
    except OverflowError:
        response = private(JsonResponse({"error": "Device backlog full; retry later"}, status=429))
        response["Retry-After"] = "60"
        return response
    except (
        ValueError,
        TypeError,
        KeyError,
        ValidationError,
        AgentDevice.DoesNotExist,
        HTTPMessageSignaturesException,
        IntegrityError,
    ):
        return private(
            JsonResponse(
                {"error": "Report rejected; check device, signature, schema and sequence"}, status=403
            )
        )
    except OperationalError:
        return private(JsonResponse({"error": "Temporarily unavailable"}, status=503))


@csrf_exempt
@require_POST
def status(request):
    try:
        device, raw = authenticate(request)
        data = decode(raw)
        if set(data) != {"schema", "report_id"} or data["schema"] != "bearings.agent.status.v1":
            raise ValueError("Invalid receipt request")
        row = AgentReport.objects.get(pk=identifier(data["report_id"]), device=device)
        return private(JsonResponse(agents.receipt(row)))
    except (
        ValueError,
        TypeError,
        KeyError,
        ValidationError,
        AgentDevice.DoesNotExist,
        AgentReport.DoesNotExist,
        HTTPMessageSignaturesException,
    ):
        return private(JsonResponse({"error": "Receipt unavailable"}, status=403))
    except OperationalError:
        return private(JsonResponse({"error": "Temporarily unavailable"}, status=503))


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


class WindowsEnrollmentForm(EnrollmentForm):
    public_key = None
    new_asset_kind = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset"].label = "Existing Windows asset"
        self.fields["asset"].required = True


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
    windows_form = WindowsEnrollmentForm(
        request.POST if request.POST.get("action") == "enroll-windows" else None,
        org=org,
        asset_query=asset_query,
        selected_asset=request.GET.get("asset", ""),
    )
    if request.method == "POST":
        require(manage)
        try:
            action = request.POST.get("action")
            if action == "enroll-windows" and windows_form.is_valid():
                agent_enrollment_codes.trusted_origin()
                grant, token = agents.create_enrollment(
                    request.user, org, windows_form.cleaned_data["asset"], "", claim_key_on_redeem=True
                )
                return private(
                    render(
                        request,
                        "portal/agent_enrollment.html",
                        {
                            "org": org,
                            "grant": grant,
                            "code": agent_enrollment_codes.windows_code(grant, token),
                        },
                    )
                )
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
        installations = list(
            Installation.objects.filter(asset=selected.asset, product__organization=org)
            .select_related("product")
            .order_by("product__name")[:250]
        )
        last_report = selected.reports.order_by("-sequence").first()
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
                "windows_form": windows_form,
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
    from .models import DistroKernelRevision
    from .distro_sources import url_for
    from urllib.parse import quote

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
    from .ubuntu_status import progress
    from .distro_evaluation import state as evaluation_state
    from .distro_sources import key_for
    from .models import DistroFeed

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
