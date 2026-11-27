"""Small first-party pictograms: allowlisted SVG only, used with meaningful text or accessible labels."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

PATHS = {
    "software": '<path d="m12 3 9 5v9l-9 5-9-5V8l9-5ZM3 8l9 5 9-5M12 13v9M7.5 5.5l9 5"/>',
    "status-check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "status-info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "overview": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "national": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/>',
    "inventory": '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6"/>',
    "clients": '<rect x="2" y="3" width="20" height="15" rx="2"/><path d="m6 7 3 3-3 3M12 13h4M8 22h8M12 18v4"/>',
    "review": '<path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3ZM12 8v5M12 16h.01"/>',
    "issues": '<path d="m12 3 10 18H2L12 3ZM12 9v5M12 17h.01"/>',
    "research": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6M10 7v6"/>',
    "discovery": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 8-8"/><circle cx="12" cy="12" r="1"/>',
    "risks": '<path d="M5 22V3c5-3 9 3 14 0v11c-5 3-9-3-14 0"/>',
    "exposure": '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2"/>',
    "notifications": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
    "response": '<circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><path d="M12 8v5M5 16v-3h14v3"/>',
    "companies": '<rect x="5" y="3" width="14" height="19" rx="1.5"/><path d="M9 7h1M14 7h1M9 11h1M14 11h1M10 22v-6h4v6"/>',
    "settings": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
    "members": '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6M21 21v-3a6 6 0 0 0-4-5"/>',
    "followups": '<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4V2h6v2M9 10h6M9 14h4M9 18h3"/>',
    "registrations": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="10" r="2"/><path d="M5 16a3 3 0 0 1 6 0M15 9h3M15 13h3M15 17h3"/>',
    "merges": '<path d="M6 3v5c0 4 12 4 12 8v5M18 3v5c0 4-12 4-12 8v5M3 18l3 3 3-3M15 18l3 3 3-3"/>',
    "misp": '<circle cx="12" cy="12" r="3"/><circle cx="4" cy="4" r="2"/><circle cx="20" cy="4" r="2"/><circle cx="4" cy="20" r="2"/><circle cx="20" cy="20" r="2"/><path d="m6 6 4 4m4 4 4 4m-8-4-4 4m8-8 4-4"/>',
    "chart": '<path d="M3 3v18h18M6 16l4-6 4 3 6-8"/>',
    "coverage": '<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M8 9h8M8 13h5M8 17h8"/>',
    "map": '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6ZM9 3v15M15 6v15"/>',
    "send": '<path d="m3 3 19 8-8 3-3 8-8-19ZM3 3l11 11"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
}
ALIASES = {
    "actions": "issues",
    "platform": "settings",
    "applications": "overview",
    "administration": "settings",
    "explore": "map",
    "start": "map",
}


@register.simple_tag
def ui_icon(name):
    key = ALIASES.get(str(name), str(name))
    key = key if key in PATHS else "overview"
    return format_html(
        '<svg class="ui-icon" data-icon="{}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        key,
        mark_safe(PATHS[key]),  # Only fixed first-party shapes ever reach SVG markup.
    )
