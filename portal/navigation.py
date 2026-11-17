"""Workspace orientation only; authorization remains in the destination views."""

from django.urls import reverse


AREAS = {
    "overview": ("Infrastructure overview", "overview", ""),
    "start": ("Start here", "getting-started", ""),
    "inventory": ("Inventory & organizations", "inventory", "inventory"),
    "review": ("Vulnerability review", "home", "assess"),
    "discovery": ("Automatic CVE discovery", "discovery", "assess"),
    "risks": ("Company risk register", "risk-register", "assess"),
    "issues": ("Asset issues & lifecycle", "issues", "assess"),
    "exposure": ("Exposure history", "plum", "assess"),
    "notifications": ("Notifications", "notifications", "respond"),
    "response": ("Incident coordination", "rtir", "respond"),
    "companies": ("Company instances", "companies", "inventory"),
    "explore": ("Explore scenarios", "demo-explore", ""),
    "administration": ("Synthetic data", "demo-data", ""),
    "platform": ("Platform administration", "admin:index", ""),
    "applications": ("Applications", "applications", ""),
}

ROUTES = {
    "overview": {"overview"},
    "risks": {"risk-register", "business-risk", "automatic-scenario"},
    "discovery": {"discovery", "discovery-configure", "discovery-refresh", "installation-version"},
    "start": {"getting-started"},
    "applications": {"applications", "application", "source-reference"},
    "inventory": {
        "inventory",
        "organization",
        "asset",
        "edit-local-asset",
        "create-contact",
        "edit-contact",
        "create-claim",
        "create-asset",
        "create-installation",
    },
    "review": {
        "home",
        "case-guide",
        "intelligence",
        "risk-catalog",
        "create-risk-link",
        "flowintel-new",
        "flowintel-case",
    },
    "issues": {"issues", "issue", "issue-new", "issue-edit", "issue-risk-add"},
    "exposure": {"plum", "plum-import", "plum-snapshot"},
    "notifications": {"notifications", "notification-batch", "outreach-policy"},
    "response": {"rtir", "rt-new", "rt-ticket"},
    "companies": {"companies"},
    "explore": {"demo-explore"},
    "administration": {"demo-data"},
}


def workspace(request):
    if not request.user.is_authenticated:
        return {}
    from .access import is_analyst

    route = request.resolver_match.url_name if request.resolver_match else ""
    area = next((key for key, names in ROUTES.items() if route in names), "review")
    label, target, stage = AREAS[area]
    if route in {"flowintel-new", "flowintel-case"}:
        stage = "respond"
    sections = [
        ("Start", ["overview", "start"]),
        ("Understand", ["inventory", "discovery", "review", "issues", "risks", "exposure"]),
        (
            "Act",
            ["notifications"]
            + (["response"] if request.user.is_superuser or is_analyst(request.user) else []),
        ),
        ("Workspace", ["applications", "companies", "explore"]),
    ]
    if request.user.is_superuser:
        sections.append(("Administration", ["platform", "administration"]))
    return {
        "workspace_area": area,
        "workspace_label": label,
        "workspace_url": reverse(target),
        "workflow_stage": stage,
        "navigation_groups": [
            {
                "label": heading,
                "items": [
                    {"label": AREAS[key][0], "url": reverse(AREAS[key][1]), "key": key, "active": key == area}
                    for key in keys
                ],
            }
            for heading, keys in sections
        ],
    }
