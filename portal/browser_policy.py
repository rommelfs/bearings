"""Strict browser origins for CSP; these helpers perform no network requests."""

import re
import ipaddress
from urllib.parse import urlsplit


def browser_base(value):
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        raise ValueError("Invalid application browser address")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port == 0
        or not re.fullmatch(r"[a-zA-Z0-9.\-:\[\]]+", parsed.netloc)
    ):
        raise ValueError("Applications require credential-free HTTPS browser addresses")
    return parsed.geturl().rstrip("/")


def origin(value):
    parsed = urlsplit(browser_base(value))
    if parsed.path not in {"", "/"}:
        raise ValueError("Configure an exact HTTPS origin without a path")
    host = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Browsers normalize short/hex/octal IPv4 spellings that urllib does not.
        # Reject them so they cannot bypass same-origin frame isolation checks.
        last = host.rstrip(".").rsplit(".", 1)[-1]
        if last.isdigit() or re.fullmatch(r"0[xX][0-9a-fA-F]+", last):
            raise ValueError("Use canonical IP addresses for browser origins") from None
    else:
        host = f"[{address.compressed}]" if address.version == 6 else str(address)
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"https://{host}{port}"
