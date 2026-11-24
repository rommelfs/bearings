"""Curated Windows identities and bounded vendor version rules; no patch attestation."""

import json
import re
from urllib.parse import urlsplit

from django.core.exceptions import ObjectDoesNotExist

# Bump RULE whenever mapping or evaluation semantics change: it is part of saved inputs.
RULE = "windows-vendor-rules/v3"
WINDOWS_RELEASES = "https://learn.microsoft.com/en-us/windows/release-health/"
HOTPATCH = "https://learn.microsoft.com/en-us/windows/deployment/windows-autopatch/manage/windows-autopatch-hotpatch-updates"
ESU = "https://learn.microsoft.com/en-us/windows/whats-new/enable-extended-security-updates"

# Registry declarations are evidence, not authenticated publisher signatures.
# WebView2 deliberately has no shared edge_chromium identity: that CPE does not
# distinguish the runtime from the browser. Office/Adobe need channel evidence.
PROGRAMS = (
    (
        "edge",
        r"Microsoft Edge",
        {"microsoft corporation"},
        "microsoft",
        "edge_chromium",
        "https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security",
        (4,),
    ),
    (
        "chrome",
        r"Google Chrome",
        {"google llc", "google inc."},
        "google",
        "chrome",
        "https://chromereleases.googleblog.com/",
        (4,),
    ),
    (
        "firefox-esr",
        r"Mozilla Firefox ESR(?: \([^)]+\))?",
        {"mozilla"},
        "mozilla",
        "firefox_esr",
        "https://www.mozilla.org/en-US/security/known-vulnerabilities/firefox-esr/",
        (2, 3),
    ),
    (
        "firefox",
        r"Mozilla Firefox(?: \([^)]+\))?",
        {"mozilla"},
        "mozilla",
        "firefox",
        "https://www.mozilla.org/en-US/security/known-vulnerabilities/firefox/",
        (2, 3),
    ),
    (
        "7zip",
        r"7-Zip(?: [0-9]+\.[0-9]+)?(?: \((?:x64|x86|arm64|x64 edition)\))?",
        {"igor pavlov"},
        "7-zip",
        "7-zip",
        "https://www.7-zip.org/history.txt",
        (2,),
    ),
)
CNA_PRODUCTS = {
    "edge": ({"microsoft"}, {"microsoft edge", "microsoft edge (chromium-based)"}),
    "chrome": ({"google", "google llc"}, {"chrome", "google chrome"}),
    "firefox-esr": ({"mozilla", "mozilla foundation"}, {"firefox esr"}),
    "firefox": ({"mozilla", "mozilla foundation"}, {"firefox"}),
    "7zip": ({"7-zip", "igor pavlov"}, {"7-zip"}),
}
VENDOR_HOSTS = {
    "microsoft": {"msrc.microsoft.com"},
    "google": {"chromereleases.googleblog.com"},
    "mozilla": {"www.mozilla.org", "mozilla.org"},
    "7-zip": {"www.7-zip.org", "7-zip.org"},
}
# Product family is derived from release/build/edition together, never ProductName
# (Windows 11 can retain a Windows 10 ProductName). Server 2025 shares 26100.
CLIENTS = {
    "10240": ("10", "1507"),
    "14393": ("10", "1607"),
    "17763": ("10", "1809"),
    "19044": ("10", "21H2"),
    "19045": ("10", "22H2"),
    "22000": ("11", "21H2"),
    "22621": ("11", "22H2"),
    "22631": ("11", "23H2"),
    "26100": ("11", "24H2"),
    "26200": ("11", "25H2"),
}
SERVERS = {"14393": "2016", "17763": "2019", "20348": "2022", "26100": "2025"}
SERVER_RELEASES = {"14393": "1607", "17763": "1809", "20348": "21H2", "26100": "24H2"}
CLIENT_EDITIONS = {
    "Core",
    "CoreN",
    "Professional",
    "ProfessionalN",
    "Education",
    "EducationN",
    "Enterprise",
    "EnterpriseN",
    "EnterpriseS",
    "EnterpriseSN",
    "IoTEnterpriseS",
}
SERVER_EDITIONS = {"ServerStandard", "ServerDatacenter", "ServerStandardEval", "ServerDatacenterEval"}
PLATFORMS = {"x86_64": "x64-based Systems", "arm64": "ARM64-based Systems", "x86": "32-bit Systems"}


def cpe(vendor, product, part="a"):
    return f"cpe:2.3:{part}:{vendor}:{product}:*:*:*:*:*:*:*:*"


def resolve(component, os):
    """Pure mapping, including explicit coverage gaps, from one report's facts."""
    w = component.windows
    result = {
        "rule": RULE,
        "observed_version": component.version,
        "cpe": "",
        "gaps": [],
        "vendor": "",
        "product_key": "",
        "references": [],
        "kind": w.get("kind"),
    }
    if w.get("kind") == "os":
        result["references"] = [WINDOWS_RELEASES, HOTPATCH, ESU]
        result.update(
            edition=w.get("edition", ""),
            release=w.get("release", ""),
            architecture=os.get("architecture", ""),
            installation_type=w.get("installation_type", ""),
            servicing_channel=w.get("servicing_channel", ""),
            update_line=w.get("update_line", ""),
        )
        build = component.version.split(".")[0]
        role, edition = w.get("installation_type"), w.get("edition")
        if role == "Client" and edition in CLIENT_EDITIONS and build in CLIENTS:
            family, release = CLIENTS[build]
            if w.get("release") != release:
                result["gaps"].append("Release and build disagree or release is missing")
            else:
                result.update(
                    vendor="microsoft",
                    product_key=f"windows_{family}_{release.lower()}",
                    msrc_product=f"Windows {family} Version {release}",
                )
        elif role in {"Server", "Server Core"} and edition in SERVER_EDITIONS and build in SERVERS:
            result.update(
                vendor="microsoft",
                product_key=f"windows_server_{SERVERS[build]}",
                msrc_product=f"Windows Server {SERVERS[build]}"
                + (" (Server Core installation)" if role == "Server Core" else ""),
            )
        else:
            result["gaps"].append("System role, edition and build do not establish a curated MSRC product")
        if role in {"Server", "Server Core"} and (
            w.get("release") != SERVER_RELEASES.get(build) or os.get("architecture") != "x86_64"
        ):
            result["gaps"].append(
                "Server release/architecture is missing or outside the curated product rule"
            )
        if (
            role == "Client"
            and build in CLIENTS
            and CLIENTS[build][0] == "11"
            and os.get("architecture") == "x86"
        ):
            result["gaps"].append("Windows 11 has no curated 32-bit OS product")
        if result["product_key"]:
            result["cpe"] = cpe("microsoft", result["product_key"], "o")
        if os.get("architecture") not in PLATFORMS:
            result["gaps"].append("Unsupported or missing native OS architecture")
        # No ordering between hotpatch and regular cumulative update revisions.
        # ESU eligibility is not proof of an installed fix. Explicitly remain open
        # until per-advisory baseline/entitlement rules are implemented.
        if w.get("update_line") != "regular":
            result["gaps"].append(
                "Update line missing or hotpatch/ESU baseline and eligibility require review"
            )
        expected = (
            "ltsc"
            if edition in {"EnterpriseS", "EnterpriseSN", "IoTEnterpriseS"}
            or role in {"Server", "Server Core"}
            else "gac"
        )
        if w.get("servicing_channel") != expected:
            result["gaps"].append("Servicing channel is missing or inconsistent with edition/system role")
        # LTSC product applicability needs dedicated lifecycle/advisory mapping.
        if expected == "ltsc":
            result["gaps"].append("LTSC product/update-line applicability requires a dedicated vendor rule")
        return result
    name, publisher = component.name, w.get("publisher", "").casefold()
    for key, pattern, publishers, vendor, product, reference, widths in PROGRAMS:
        if not re.fullmatch(pattern, name, re.IGNORECASE):
            continue
        result.update(
            vendor=vendor,
            product_key=product,
            cpe=cpe(vendor, product),
            references=[reference],
            version_widths=list(widths),
            catalog_product=key,
        )
        if publisher not in publishers:
            result["gaps"].append("Publisher declaration is missing or does not match the curated publisher")
        if key == "firefox":
            result["gaps"].append("Registry name does not distinguish Firefox release from ESR")
        return result
    if "webview2" in name.casefold():
        gap = "WebView2 runtime requires its own vendor product rule; shared Edge CPE is ambiguous"
    elif re.search(r"office|microsoft 365", name, re.I):
        gap = "Office requires exact suite, MSI/Click-to-Run, release and update channel evidence"
    elif re.search(r"adobe.*(?:acrobat|reader)", name, re.I):
        gap = "Acrobat/Reader requires exact product and Classic/Continuous track evidence"
    else:
        gap = "No curated Windows product identity; product names alone do not establish applicability"
    result["gaps"].append(gap)
    return result


def context(installation):
    """Return evidence only from the bound installation, tenant, asset and source."""
    try:
        component = installation.agent_component
    except ObjectDoesNotExist:
        return None
    if component.manager != "win-reg":
        return None
    device = component.device
    from .agents import current

    if (
        device.organization_id != installation.product.organization_id
        or installation.asset_id != device.asset_id
        or installation.asset.organization_id != device.organization_id
        or installation.asset.source_id != device.source_id
        or device.source.organization_id != device.organization_id
        or component.last_report.device_id != device.pk
    ):
        return {
            "rule": RULE,
            "observed_version": installation.version,
            "cpe": "",
            "vendor": "",
            "product_key": "",
            "references": [],
            "kind": "unknown",
            "gaps": ["Observation is outside the current source/tenant binding"],
        }
    # Application rules need no host OS fields. Avoid loading the full fleet
    # report once per application; it may contain thousands of registrations.
    report_os = (
        json.loads(bytes(component.last_report.body))["os"] if component.windows.get("kind") == "os" else {}
    )
    result = resolve(component, report_os)
    if component.windows.get("kind") == "os" and report_os.get("windows_update"):
        result["windows_update"] = report_os["windows_update"]
    result.update(
        component=component.pk,
        report=str(component.last_report_id),
        observed_at=component.observed_at.isoformat(),
        registry=component.windows,
    )
    if (
        not current(device)
        or component.stale
        or component.missing_since
        or device.stale
        or device.organization_id != installation.product.organization_id
        or installation.asset_id != device.asset_id
        or component.version != installation.version
        or installation.asset.organization_id != device.organization_id
        or installation.asset.source_id != device.source_id
    ):
        result["gaps"].append(
            "Observation is stale, absent, inactive or outside the current source/tenant binding"
        )
    return result


def product_suggestions(product):
    """Retain registry identity; conflicting hosts/releases require explicit review."""
    from .models import Installation

    mappings = [
        context(i)
        for i in Installation.objects.filter(
            product=product,
            asset__organization_id=product.organization_id,
            asset__source__organization_id=product.organization_id,
            asset__lifecycle="active",
        )
        .select_related(
            "asset",
            "product",
            "agent_component__device__asset",
            "agent_component__device__source",
            "agent_component__device__organization",
            "agent_component__last_report",
        )
        .defer("agent_component__last_report__body")[:101]
    ]
    if len(mappings) > 100 or not mappings or any(not m or m["gaps"] for m in mappings):
        return []
    identities = {(m["vendor"], m["product_key"]) for m in mappings}
    if len(identities) != 1:
        return []
    vendor, key = identities.pop()
    return [
        {"vendor": vendor, "product_key": key, "reason": RULE + "; curated registry publisher/product rule"}
    ]


def numeric(value, widths):
    if not isinstance(value, str) or len(value) > 120 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", value):
        return None
    parts = value.split(".")
    if len(parts) not in widths:
        return None
    return tuple(int(p) for p in parts) + (0,) * (4 - len(parts))


def vendor_reference(cna, vendor):
    refs = cna.get("references", [])
    if not isinstance(refs, list):
        return ""
    for ref in refs:
        url = ref.get("url") if isinstance(ref, dict) else None
        if (
            not isinstance(url, str)
            or len(url) > 2048
            or url != url.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in url)
        ):
            continue
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme == "https"
                and parsed.hostname in VENDOR_HOSTS.get(vendor, set())
                and not parsed.username
                and not parsed.password
                and parsed.port in {None, 443}
            ):
                return url
        except ValueError:
            continue
    return ""


def evaluate(watch, installation, payload, mapping):
    """Evaluate only manufacturer-linked numeric rules for the exact mapped product."""
    prefix = (
        f"{RULE}; observed version {installation.version or 'unknown'}; "
        f"product {mapping.get('msrc_product') or mapping.get('cpe') or 'unresolved'}. "
    )
    if mapping.get("references"):
        prefix += "Mapping references: " + ", ".join(mapping["references"]) + ". "
    if mapping["gaps"]:
        return "unknown", prefix + "; ".join(mapping["gaps"]) + "."
    if installation.build or installation.edition:
        return "unknown", prefix + "Manually maintained build/edition qualifiers require review."
    if (watch.vendor, watch.product_key) != (mapping["vendor"], mapping["product_key"]):
        return "unknown", prefix + "Saved monitoring identity differs from observed product; review mapping."
    if payload.get("cveMetadata", {}).get("state") == "REJECTED":
        return "unknown", prefix + "CVE rejected; retained review requires reconciliation."
    containers = payload.get("containers", {})
    cna = containers.get("cna", {}) if isinstance(containers, dict) else {}
    if not isinstance(cna, dict):
        return "unknown", prefix + "Unsupported CNA evidence."
    reference = vendor_reference(cna, mapping["vendor"])
    if not reference:
        return "unknown", prefix + "Manufacturer advisory reference missing."
    prefix += f"Manufacturer evidence: {reference}. "
    version = installation.version
    if mapping["kind"] == "os":
        version = "10.0." + version
    widths = (4,) if mapping["kind"] == "os" else tuple(mapping["version_widths"])
    observed = numeric(version, widths)
    if observed is None:
        return "unknown", prefix + "Observed version is missing or unsupported by the product version rule."
    affected = cna.get("affected", [])
    if not isinstance(affected, list):
        return "unknown", prefix + "Unsupported affected-product evidence."
    statuses, proofs, unsupported = set(), [], False
    matched_rules = 0
    for item in affected:
        if not isinstance(item, dict):
            unsupported = True
            continue
        if mapping["kind"] == "os":
            same = (
                isinstance(item.get("vendor"), str)
                and isinstance(item.get("product"), str)
                and item["vendor"].casefold() == "microsoft"
                and item.get("product", "").casefold() == mapping["msrc_product"].casefold()
            )
        else:
            vendors, names = CNA_PRODUCTS[mapping["catalog_product"]]
            same = (
                isinstance(item.get("vendor"), str)
                and isinstance(item.get("product"), str)
                and item["vendor"].casefold() in vendors
                and item["product"].casefold() in names
            )
            cpes = item.get("cpes", [])
            # A shared CPE cannot turn a WebView2 advisory into an Edge browser rule.
            # Qualified CPE constraints are never stripped to force a match.
            if cpes and (not isinstance(cpes, list) or mapping["cpe"] not in cpes):
                same = False

        if not same:
            continue
        if any(item.get(k) for k in ("modules", "programRoutines", "programFiles")):
            unsupported = True
            continue
        platforms = item.get("platforms")
        if mapping["kind"] == "os":
            if not isinstance(platforms, list) or PLATFORMS[mapping["architecture"]] not in platforms:
                unsupported = True
                continue
        elif platforms and (not isinstance(platforms, list) or "Windows" not in platforms):
            unsupported = True
            continue
        versions = item.get("versions")
        if not isinstance(versions, list) or not versions:
            unsupported = True
            continue
        for entry in versions:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("status"), str)
                or entry["status"]
                not in {
                    "affected",
                    "unaffected",
                    "unknown",
                }
            ):
                unsupported = True
                continue
            low = numeric(entry.get("version"), widths)
            has_upper = "lessThan" in entry or "lessThanOrEqual" in entry
            upper = entry.get("lessThan", entry.get("lessThanOrEqual"))
            high = numeric(upper, widths) if has_upper else low
            if (
                entry.get("changes")
                or low is None
                or high is None
                or low > high
                or "lessThan" in entry
                and "lessThanOrEqual" in entry
                or has_upper
                and entry.get("versionType") not in ("custom", "semver")
                or has_upper
                and entry.get("versionType") == "semver"
                and (len(entry["version"].split(".")) != 3 or len(upper.split(".")) != 3)
            ):
                unsupported = True
                continue
            # Never compare across Windows build branches or Firefox ESR majors.
            if mapping["kind"] == "os" and not (observed[:3] == low[:3] == high[:3]):
                unsupported = True
                continue
            if mapping.get("catalog_product") == "firefox-esr" and not (observed[0] == low[0] == high[0]):
                unsupported = True
                continue
            matches = (
                observed == low
                if not has_upper
                else low <= observed and (observed < high if entry.get("lessThan") else observed <= high)
            )
            if matches:
                statuses.add(entry["status"])
                matched_rules += 1
                if len(proofs) < 10:
                    proof = {"version": entry["version"], "status": entry["status"]}
                    if has_upper:
                        proof["lessThan" if "lessThan" in entry else "lessThanOrEqual"] = upper
                        proof["versionType"] = entry["versionType"]
                    proofs.append(json.dumps(proof, sort_keys=True))
    if not unsupported and set(statuses) == {"affected"}:
        return "potential", (
            prefix
            + "Affected-version rule: "
            + "; ".join(proofs)
            + f". {matched_rules} matching rules; at most ten shown; full advisory retained. "
            + "Local applicability requires review."
        )
    return (
        "unknown",
        prefix
        + "No unambiguous supported affected-version rule; missing evidence or nonmatching rules do not establish a fixed or safe installation.",
    )
