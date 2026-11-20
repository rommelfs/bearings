"""Workspace orientation only; authorization remains in the destination views."""

from django.urls import reverse


AREAS = {
    "merges": ("Merge organizations", "company-merge", ""),
    "misp": ("My MISP", "misp", "assess"),
    "registrations": ("Registrations", "registration-applications", ""),
    "national": ("National overview", "circl-overview", ""),
    "overview": ("Infrastructure overview", "overview", ""),
    "start": ("Start here", "getting-started", ""),
    "inventory": ("Inventory & organizations", "inventory", "inventory"),
    "review": ("Vulnerability review", "home", "assess"),
    "discovery": ("Automatic CVE discovery", "discovery", "assess"),
    "risks": ("Company risk register", "risk-register", "assess"),
    "actions": ("What needs attention?", "company-actions", "assess"),
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
    "merges": {"company-merge"},
    "misp": {"misp", "misp-event", "misp-connections", "misp-legacy", "misp-event-legacy"},
    "actions": {"company-actions", "company-action"},
    "registrations": {
        "registration-applications",
        "registration-application",
        "service-mail",
        "service-mail-message",
    },
    "national": {
        "review-followups",
        "review-followup",
        "circl-overview",
        "circl-research",
        "circl-findings",
        "circl-map-location",
    },
    "overview": {"overview"},
    "risks": {"risk-register", "business-risk", "automatic-scenario"},
    "discovery": {"discovery", "discovery-configure", "discovery-refresh", "installation-version"},
    "start": {"getting-started"},
    "applications": {"applications", "application", "source-reference", "sso-settings", "workspace-switch"},
    "inventory": {
        "inventory",
        "company-members",
        "company-join",
        "organization",
        "company-address",
        "company-start",
        "csv-upload",
        "csv-preview",
        "csv-template",
        "configuration",
        "configuration-section",
        "setup-resume",
        "setup-section",
        "asset",
        "edit-local-asset",
        "inventory-review",
        "create-contact",
        "edit-contact",
        "create-claim",
        "correct-scope",
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

    operator = request.user.is_superuser or is_analyst(request.user)
    route = request.resolver_match.url_name if request.resolver_match else ""
    area = next((key for key, names in ROUTES.items() if route in names), "review")
    label, target, stage = AREAS[area]
    if route in {"flowintel-new", "flowintel-case"}:
        stage = "respond"
    sections = [
        ("Start", (["national"] if operator else []) + ["overview", "start"]),
        ("Understand", ["actions", "inventory", "discovery", "review", "issues", "risks", "exposure"]),
        (
            "Act",
            ["notifications"] + (["response"] if operator else []),
        ),
        (
            "Workspace",
            ["applications", "misp", "companies", "explore"] + (["registrations"] if operator else []),
        ),
    ]
    if request.user.is_superuser:
        sections.append(("Administration", ["platform", "merges", "administration"]))
    return {
        "workspace_home_url": reverse("circl-overview" if operator else "overview"),
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
