"""Carry list context through a case without accepting arbitrary redirect targets."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit
from django.urls import reverse

KEYS = {
    "workspace",
    "installation",
    "changed",
    "organization",
    "company_q",
    "kind",
    "state",
    "timing",
    "q",
    "asset",
    "attention",
    "group_issue",
    "product",
    "page",
    "review_page",
    "org_page",
    "severity",
    "sort",
    "direction",
    "host_q",
    "host_filter",
    "inventory_q",
    "inventory_page",
    "contact_page",
    "scope_page",
}


def return_url(request):
    value = request.GET.get("return_to", "")
    if len(value) > 4096 or any(char in value for char in "\\\r\n\x00"):
        return ""
    try:
        target = urlsplit(value)
    except ValueError:
        return ""
    if target.scheme or target.netloc or target.fragment:
        return ""
    allowed = {reverse("issues"), reverse("home")}
    if target.path not in allowed and not re.fullmatch(
        r"/organizations/[a-zA-Z0-9_-]+/(?:intelligence/)?", target.path
    ):
        return ""
    params = [(key, val[:180]) for key, val in parse_qsl(target.query) if key in KEYS]
    query = urlencode(params)
    return target.path + ("?" + query if query else "")


def with_return(request, url):
    target = return_url(request)
    if not target:
        return url
    path, marker, fragment = url.partition("#")
    path += ("&" if "?" in path else "?") + urlencode({"return_to": target})
    return path + (marker + fragment if marker else "")
