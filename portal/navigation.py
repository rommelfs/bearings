"""Workspace orientation only; authorization remains in the destination views."""

from django.urls import reverse
from urllib.parse import urlencode


AREAS = {
    "research": ("Product & version research", "circl-research", "assess"),
    "followups": ("Company data reviews", "review-followups", ""),
    "settings": ("Company configuration", "workspace-switch", "inventory"),
    "members": ("Company members", "workspace-switch", "inventory"),
    "merges": ("Merge organizations", "company-merge", ""),
    "misp": ("My MISP", "misp", "assess"),
    "registrations": ("Registrations", "registration-applications", ""),
    "national": ("National overview", "circl-overview", ""),
    "overview": ("Infrastructure overview", "overview", ""),
    "infrastructure-status": ("Company infrastructure status", "overview", ""),
    "organizations": ("Organizations", "inventory", "inventory"),
    "national-evidence": ("Vulnerability evidence", "circl-findings", "assess"),
    "start": ("Start here", "getting-started", ""),
    "inventory": ("Hosts & software", "inventory", "inventory"),
    "clients": ("Inventory clients", "client-platforms", "inventory"),
    "review": ("Vulnerability review", "home", "assess"),
    "discovery": ("Automatic CVE discovery", "discovery", "assess"),
    "risks": ("Company risk register", "risk-register", "assess"),
    "actions": ("What needs attention?", "company-actions", "assess"),
    "issues": ("Asset issues & lifecycle", "issues", "assess"),
    "exposure": ("Exposure history", "plum", "assess"),
    "notifications": ("Notifications", "notifications", "respond"),
    "response": ("Incident coordination", "rtir", "respond"),
    "companies": ("Federated company reports", "companies", "inventory"),
    "explore": ("Explore scenarios", "demo-explore", ""),
    "administration": ("Synthetic data", "demo-data", ""),
    "platform": ("Platform settings", "admin:index", ""),
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
        "national-machines",
        "circl-coverage-records",
        "circl-map-location",
    },
    "overview": {"overview"},
    "risks": {"risk-register", "business-risk", "automatic-scenario"},
    "discovery": {"discovery", "discovery-configure", "discovery-refresh", "installation-version"},
    "start": {"getting-started"},
    "applications": {"applications", "application", "source-reference", "sso-settings", "workspace-switch"},
    "clients": {
        "client-platforms",
        "client-rollouts",
        "client-profiles",
        "linux-client-downloads",
        "windows-client-downloads",
        "macos-client-downloads",
        "agent-fleets",
        "agent-center",
        "kernel-evidence",
        "application-profiles",
    },
    "inventory": {
        "inventory",
        "organization-machines",
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
        "software-coverage",
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
        "organization-cases",
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


def workspace(request, *, show_examples=False, company=None, national=False):
    if not request.user.is_authenticated:
        return {}
    route = request.resolver_match.url_name if request.resolver_match else ""
    area = next((key for key, names in ROUTES.items() if route in names), "review")
    if company and route in {"configuration", "configuration-section", "setup-resume", "setup-section"}:
        area = "settings"
    elif company and route == "company-members":
        area = "members"
    elif national and route == "circl-research":
        area = "research"
    elif route in {"review-followups", "review-followup"}:
        area = "followups" if national else "inventory"
    elif national and route == "overview":
        area = "infrastructure-status"
    elif national and route == "inventory":
        area = "organizations"
    elif national and route in {"circl-findings", "home"}:
        area = "national-evidence"
    elif route == "index" and request.resolver_match.namespace == "admin":
        area = "platform"
    label, _, stage = AREAS[area]
    if route in {"flowintel-new", "flowintel-case"}:
        stage = "respond"
    landing = "national" if national else "overview"
    if national:
        sections = [
            ("National operations", ["research"]),
            (
                "Organizations & evidence",
                ["organizations", "infrastructure-status", "followups", "national-evidence"],
            ),
            ("Response", ["notifications", "response"]),
            ("Integrations", ["applications", "misp", "companies"]),
        ]
        administration = ["registrations"] + (
            ["platform", "merges", "administration"] if request.user.is_superuser else []
        )
        sections.append(("Platform administration", administration))
    else:
        sections = [
            ("Overview", ["actions"]),
            ("Inventory", ["inventory", "issues", "clients"]),
            ("Security", ["review", "discovery", "risks", "exposure"]),
            ("Response", ["notifications"]),
            ("My integrations", ["misp"]),
        ]
        if company:
            from .access import role_for

            company_admin = role_for(request.user, company) == "admin"
            if request.user.is_superuser or company_admin:
                admin_items = ["settings", "members"] if company_admin else ["settings"]
                sections.append(("Company administration", admin_items))
    scoped = {}
    if company:
        query = "?" + urlencode({"organization": company.slug})
        scoped = {
            "overview": reverse("overview") + query,
            "actions": reverse("company-actions") + query,
            "inventory": reverse("organization", args=[company.slug]),
            "clients": reverse("client-platforms") + query,
            "issues": reverse("issues") + query,
            "review": reverse("intelligence", args=[company.slug]),
            "discovery": reverse("discovery") + query,
            "risks": reverse("risk-register") + query,
            "exposure": reverse("plum") + query,
            "notifications": reverse("notifications")
            + "?"
            + urlencode({"organization": company.pk, "mode": "company"}),
            "settings": reverse("configuration", args=[company.slug]),
            "members": reverse("company-members", args=[company.slug]),
            "misp": reverse("misp-connections") + query,
            "start": reverse("getting-started") + query,
            "explore": reverse("demo-explore") + query,
        }

    def item_url(key):
        return scoped.get(key) or reverse(AREAS[key][1])

    sections.append(
        ("Help & examples", ["start"] + (["explore"] if show_examples or area == "explore" else []))
    )

    def item(key):
        return {"label": AREAS[key][0], "url": item_url(key), "key": key, "active": key == area}

    return {
        "workspace_home_url": item_url(landing),
        "workspace_scope_label": f"{company.name} infrastructure"
        if company
        else "National"
        if national
        else "Company workspaces",
        "workspace_area": area,
        "workspace_label": label,
        "workspace_url": item_url(area),
        "workspace_landing": item(landing),
        "workflow_stage": stage,
        "navigation_groups": [
            {
                "label": heading,
                "open": area in keys or (area == landing and index == 0),
                "items": [item(key) for key in keys],
            }
            for index, (heading, keys) in enumerate(sections)
        ],
    }
