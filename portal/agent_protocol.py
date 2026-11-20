"""Strict Linux observation contract and RFC 9421/9530 verification; no session authentication."""

import base64
import hashlib
import hmac
import json
import re
import uuid
from datetime import timedelta
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from http_message_signatures import HTTPMessageVerifier, HTTPSignatureKeyResolver, algorithms

MAX_BYTES = 1_000_000
MAX_COMPONENTS = 5000
TAG = "bearings.agent.v1"
COVERED = ("@method", "@path", "@authority", "content-digest", "content-type", "x-bearings-key")


def identifier(value):
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("Use a canonical UUID")
    parsed = uuid.UUID(value)
    if str(parsed) != value:
        raise ValueError("Use a canonical UUID")
    return parsed


def public_key(value):
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32 or base64.b64encode(raw).decode() != value:
            raise ValueError
        return Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Use a base64-encoded 32-byte Ed25519 public key") from exc


class Resolver(HTTPSignatureKeyResolver):
    def __init__(self, identity, key):
        self.identity, self.key = identity, public_key(key)

    def resolve_public_key(self, key_id):
        if key_id != self.identity:
            raise ValueError("Wrong signing identity")
        return self.key


def verify(request, raw, identity, key):
    if (
        request.GET
        or request.headers.get("Content-Encoding")
        or request.headers.get("Content-Type") != "application/json"
    ):
        raise ValueError("Unsupported envelope")
    if len(raw) > MAX_BYTES or not raw:
        raise ValueError("Invalid size")
    digest = "sha-256=:" + base64.b64encode(hashlib.sha256(raw).digest()).decode() + ":"
    if not hmac.compare_digest(digest, request.headers.get("Content-Digest", "")):
        raise ValueError("Body digest differs")
    if request.headers.get("X-Bearings-Key") != identity:
        raise ValueError("Wrong key header")
    for header in ("Signature", "Signature-Input"):
        if len(request.headers.get(header, "")) > 2048:
            raise ValueError("Oversized signature")
    if len(request.build_absolute_uri()) > 2048:
        raise ValueError("Target exceeds the reference profile")
    msg = SimpleNamespace(method=request.method, url=request.build_absolute_uri(), headers=request.headers)
    results = HTTPMessageVerifier(
        signature_algorithm=algorithms.ED25519, key_resolver=Resolver(identity, key)
    ).verify(msg, max_age=timedelta(minutes=5), expect_tag=TAG, expect_label="bearings")
    if len(results) != 1:
        raise ValueError("One signature required")
    result = results[0]
    if set(result.covered_components) != {f'"{v}"' for v in (*COVERED, "@signature-params")}:
        raise ValueError("Incomplete signature coverage")
    params = result.parameters
    if set(params) != {"created", "expires", "keyid", "alg", "nonce", "tag"}:
        raise ValueError("Unexpected signature parameters")
    now = timezone.now().timestamp()
    if not (
        now - 300 <= params["created"] <= now + 30
        and params["created"] < params["expires"] <= params["created"] + 300
        and params["expires"] >= now
    ):
        raise ValueError("Signature outside delivery window")
    identifier(params["nonce"])
    return result


def decode(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out

    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")),
        )
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 8:
                raise ValueError("JSON nesting exceeds the reference profile")
            if isinstance(value, dict):
                pending.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                pending.extend((child, depth + 1) for child in value)
        return result
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the reference profile") from exc


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("Unexpected fields")


def text(value, length, pattern=None):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= length
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("Invalid text")
    if pattern and not re.fullmatch(pattern, value):
        raise ValueError("Invalid identifier")


def package_scope(name, scope):
    return (
        scope == "system-packages"
        or scope == "nginx-packages"
        and (name == "nginx" or name.startswith(("nginx-", "libnginx-mod-")))
    )


def report_data(data):
    exact(
        data,
        (
            "schema",
            "report_id",
            "sequence",
            "observed_at",
            "scope",
            "complete",
            "os",
            "components",
            "services",
        ),
    )
    if data["schema"] != TAG or type(data["sequence"]) is not int or not 1 <= data["sequence"] <= 2**63 - 1:
        raise ValueError("Invalid version or sequence")
    identifier(data["report_id"])
    observed = parse_datetime(data["observed_at"])
    if not observed or timezone.is_naive(observed) or observed > timezone.now() + timedelta(minutes=5):
        raise ValueError("Invalid observation time")
    if (
        data["scope"] not in ("system-packages", "nginx-packages", "selected-packages", "configured-binaries")
        or type(data["complete"]) is not bool
    ):
        raise ValueError("Invalid coverage")
    if data["scope"] in ("selected-packages", "configured-binaries") and data["complete"]:
        raise ValueError("Selected packages cannot assert completeness")
    exact(data["os"], ("id", "version", "architecture", "kernel", "reboot_hint"))
    for field in ("id", "version", "architecture", "kernel"):
        text(data["os"][field], 120)
    if data["os"]["reboot_hint"] not in ("present", "not_observed", "unknown"):
        raise ValueError("Invalid reboot hint")
    components = data["components"]
    if not isinstance(components, list) or len(components) > MAX_COMPONENTS or not components:
        raise ValueError("Use 1–5000 package observations")
    keys = set()
    managers = set()
    for c in components:
        if not isinstance(c, dict):
            raise ValueError("Invalid component")
        binary = c.get("manager") == "binary"
        fields = ("key", "manager", "name", "version", "architecture")
        exact(c, (*fields, "binary") if binary else fields)
        if c["manager"] not in ("dpkg", "rpm", "binary"):
            raise ValueError("Unsupported collector")
        text(c["name"], 128, r"[A-Za-z0-9][A-Za-z0-9+_.-]*")
        text(c["architecture"], 64, r"[A-Za-z0-9][A-Za-z0-9_.-]*")
        text(c["version"], 120)
        base = f"{c['manager']}:{c['name']}:{c['architecture']}"
        allowed = {base}
        if c["manager"] == "rpm":
            allowed.add(base + "@" + c["version"])
        if binary:
            if data["scope"] != "configured-binaries" or len(components) > 16:
                raise ValueError("Binary observations require a separate bounded scope")
            text(c["key"], 255, r"binary:[a-z0-9][a-z0-9._-]{0,63}:" + re.escape(c["architecture"]))
            exact(c["binary"], ("path", "sha256"))
            path = c["binary"]["path"]
            text(path, 1024)
            from pathlib import PurePosixPath

            if (
                not path.startswith("/")
                or path.startswith("//")
                or str(PurePosixPath(path)) != path
                or ".." in PurePosixPath(path).parts
            ):
                raise ValueError("Use an absolute normalized binary path")
            text(c["binary"]["sha256"], 64, r"[0-9a-f]{64}")
            allowed = {c["key"]}
        elif data["scope"] == "configured-binaries":
            raise ValueError("Package observations cannot claim binary coverage")
        if c["key"] not in allowed or len(c["key"]) > 255 or c["key"] in keys:
            raise ValueError("Duplicate or invalid package identity")
        if data["scope"] == "nginx-packages" and not package_scope(c["name"], data["scope"]):
            raise ValueError("Out-of-scope package")
        keys.add(c["key"])
        managers.add(c["manager"])
    if len(managers) != 1:
        raise ValueError("One package database per snapshot")
    if not isinstance(data["services"], list) or len(data["services"]) > 1:
        raise ValueError("Unsupported runtime observations")
    if data["scope"] == "configured-binaries" and data["services"]:
        raise ValueError("Configured binary versions do not assert runtime coverage")
    for s in data["services"]:
        exact(s, ("name", "state", "coverage"))
        if (
            s["name"] != "nginx"
            or s["state"] not in ("executable_matches", "different_executable", "not_running", "unknown")
            or s["coverage"] not in ("main_process_only", "cgroup_processes", "unavailable")
        ):
            raise ValueError("Invalid service observation")
        if s["state"] == "executable_matches" and s["coverage"] == "unavailable":
            raise ValueError("Runtime coverage missing")
    return observed


def host_claim(value):
    """Local hostname and interface addresses are declarations, never identity or authority proofs."""
    import ipaddress

    exact(value, ("hostname", "addresses"))
    text(value["hostname"], 180, r"[A-Za-z0-9][A-Za-z0-9_.-]{0,179}")
    if not isinstance(value["addresses"], list) or len(value["addresses"]) > 64:
        raise ValueError("Use at most 64 configured interface addresses")
    seen = set()
    for entry in value["addresses"]:
        exact(entry, ("interface", "address"))
        text(entry["interface"], 64, r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}")
        text(entry["address"], 64)
        address = ipaddress.ip_interface(entry["address"])
        if (
            address.ip.is_loopback
            or address.ip.is_link_local
            or address.ip.is_multicast
            or address.ip.is_unspecified
        ):
            raise ValueError("Only configured unicast non-loopback/link-local addresses are supported")
        if str(address) != entry["address"] or (entry["interface"], str(address)) in seen:
            raise ValueError("Duplicate or noncanonical address declaration")
        seen.add((entry["interface"], str(address)))
    return value
