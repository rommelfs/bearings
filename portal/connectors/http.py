"""Operator-configured destinations only. No redirects or caller-controlled URLs."""

import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit
import httpx
from django.conf import settings


class ConnectorError(Exception):
    pass


def validate_base(url):
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        raise ConnectorError("Invalid operator connector URL") from None
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.query
        or p.fragment
        or port == 0
    ):
        raise ConnectorError("Operator must configure a credential-free HTTPS base URL with a valid port")
    return p


def approved_base(url, allow_private=False, *, proxy_dns=None):
    p = validate_base(url)
    try:
        literal = ipaddress.ip_address(p.hostname)
    except ValueError:
        literal = None
    if literal and not literal.is_global and not allow_private:
        raise ConnectorError("Private connector destinations require explicit operator approval")
    if proxy_dns is None:
        proxy_dns = settings.CONNECTOR_PROXY_DNS
    if proxy_dns:
        if p.hostname.lower() not in settings.CONNECTOR_ALLOWED_HOSTS:
            raise ConnectorError("Connector hostname is not explicitly approved by the operator")
        if not (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")):
            raise ConnectorError("Proxy DNS mode requires an approved HTTPS proxy")
        # The operator's egress proxy performs DNS and enforces destination policy.
        return url.rstrip("/")
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ConnectorError("Connector DNS resolution failed") from None
    if not addresses or (
        not allow_private and any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    ):
        raise ConnectorError("Private connector destinations require explicit operator approval")
    return url.rstrip("/")


def request_json(method, url, **kwargs):
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            with client.stream(method, url, **kwargs) as response:
                if response.status_code >= 300:
                    raise ConnectorError(f"Upstream HTTP {response.status_code}; no data removed")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ConnectorError("Upstream response exceeds 2 MB limit")
                    chunks.append(chunk)
                data = json.loads(b"".join(chunks))
                if not isinstance(data, dict):
                    raise ConnectorError("Expected an upstream JSON object")
                return data
    except (httpx.HTTPError, ValueError):
        raise ConnectorError(
            "Connector transport or JSON failure; retry after checking service health"
        ) from None
