"""Outbound links for public CVE identifiers without organization context."""

import re

from django import template
from django.utils.html import format_html

register = template.Library()
CVE = re.compile(r"cve-[0-9]{4}-[0-9]{4,}", re.ASCII | re.IGNORECASE)


@register.simple_tag
def cve_lookup(identifier):
    if not isinstance(identifier, str) or len(identifier) > 120 or not CVE.fullmatch(identifier):
        return ""
    label = f"Open {identifier.upper()} in CIRCL Vulnerability-Lookup (new tab)"
    return format_html(
        '<a class="cve-lookup" href="https://vulnerability.circl.lu/vuln/{}" '
        'target="_blank" rel="noopener noreferrer" aria-label="{}" title="{}">CIRCL ↗</a>',
        identifier.lower(),
        label,
        label,
    )
