"""Signed HTTPS endpoints for inventory clients."""

import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST
from http_message_signatures.exceptions import HTTPMessageSignaturesException

from . import agents
from .agent_protocol import MAX_BYTES, decode, identifier, public_key, verify
from .models import AgentDevice, AgentEnrollment, AgentFleet, AgentReport


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
def uninstall(request):
    try:
        raw = body(request, 1024)
        message = decode(raw)
        if (
            not isinstance(message, dict)
            or set(message) != {"schema", "action"}
            or message["schema"] != "bearings.agent.uninstall.v1"
            or message["action"] not in ("check", "acknowledge", "local")
        ):
            raise ValueError("Invalid uninstall request")
        identity = request.headers.get("X-Bearings-Key", "")
        if not identity.startswith("device:") or len(identity) != 43:
            raise ValueError("Invalid key")
        device = AgentDevice.objects.get(pk=identifier(identity[7:]))
        verify(request, raw, identity, device.public_key)
        action = agents.uninstall_exchange(device.pk, message["action"])
        return private(
            JsonResponse({"schema": message["schema"], "action": action, "device_id": str(device.pk)})
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        ValidationError,
        PermissionDenied,
        AgentDevice.DoesNotExist,
        HTTPMessageSignaturesException,
        IntegrityError,
    ):
        return private(JsonResponse({"error": "Uninstall request unavailable"}, status=403))
    except OperationalError:
        return private(JsonResponse({"error": "Temporarily unavailable"}, status=503))


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
        response = private(JsonResponse(agents.receipt(row), status=202 if row.status == "pending" else 200))
        response["Bearings-Inventory-Check"] = "1"
        response["Bearings-MacOS-Coverage"] = "1"
        return response
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
        response = private(
            JsonResponse(
                {"error": "Report rejected; check device, signature, schema and sequence"}, status=403
            )
        )
        response["Bearings-Inventory-Check"] = "1"
        response["Bearings-MacOS-Coverage"] = "1"
        return response
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
