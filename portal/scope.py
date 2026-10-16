"""Pure matching rules. A match is a relationship, never proof of compromise."""

import ipaddress
import re
from django.core.exceptions import ValidationError


def normalize(kind, value):
    value = value.strip()
    try:
        if kind == "ip":
            return str(ipaddress.ip_address(value))
        if kind == "network":
            return str(ipaddress.ip_network(value, strict=True))
        if kind == "range":
            start, end = (ipaddress.ip_address(x.strip()) for x in value.split("-"))
            if start.version != end.version or int(start) > int(end):
                raise ValueError()
            return f"{start}-{end}"
        if kind == "domain":
            value = value.rstrip(".").encode("idna").decode().lower()
            if (
                len(value) > 253
                or "." not in value
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in value.split("."))
            ):
                raise ValueError()
            return value
    except (ValueError, UnicodeError):
        raise ValidationError("Enter a valid address, strict prefix, ordered range, or DNS name")
    raise ValidationError("Unsupported claim type")


def matches(claim, indicator, at, organization_id=None, network_context=""):
    if claim.status != "verified" or at < claim.valid_from or (claim.valid_until and at >= claim.valid_until):
        return False
    try:
        if claim.kind == "domain":
            host = normalize("domain", indicator)
            return host == claim.value or host.endswith("." + claim.value)
        address = ipaddress.ip_address(indicator)
        if not address.is_global and (
            organization_id != claim.organization_id or network_context != claim.network_context
        ):
            return False
        if claim.kind == "ip":
            return address == ipaddress.ip_address(claim.value)
        if claim.kind == "network":
            return address in ipaddress.ip_network(claim.value)
        start, end = map(ipaddress.ip_address, claim.value.split("-"))
        return address.version == start.version and int(start) <= int(address) <= int(end)
    except (ValueError, ValidationError):
        return False
