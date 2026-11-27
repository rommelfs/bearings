"""Explain recorded coverage limits without inventing host remediation or CVE verdicts."""

from urllib.parse import urlencode
from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from .agent_freshness import recent_component
from . import distro_results
from .models import AgentReport


REASONS = {
    "vendor_version_boundary_missing": "vendor rule supplies no affected/fixed version boundary",
    "unsupported_condition": "a required rule condition cannot be decided",
    "source_metadata_missing": "reported source-package name/version is missing",
    "invalid_source_version": "reported source-package version is not a usable Debian version",
    "ubuntu_status_pending": "official Ubuntu status was not yet available at this evaluation",
    "ubuntu_status_unavailable": "official Ubuntu status retrieval failed; inspect the current lookup progress",
    "ubuntu_status_stale": "official Ubuntu status cache is stale",
    "vendor_needs_triage": "Ubuntu has not yet assessed affectedness (needs-triage)",
    "vendor_unfixed": "Ubuntu lists needed work without a released fixed version",
    "vendor_fix_pending": "Ubuntu lists a fix in preparation; released availability remains to be checked",
    "vendor_deferred": "Ubuntu has deferred the fix without a usable version boundary",
    "vendor_ignored": "Ubuntu marks the issue ignored; this is not a fixed-version statement",
    "vendor_source_not_listed": "Ubuntu does not list this exact release/source package",
    "vendor_status_unresolved": "official Ubuntu statuses are absent, unsupported or conflicting",
}


def count(summary, key):
    value = summary.get(key)
    return value if type(value) is int and value >= 0 else 0


def explain(summary):
    source = count(summary, "missing_source_metadata")
    ubuntu_source = count(summary, "ubuntu_source_gaps")
    rules = count(summary, "unsupported_conditions")
    matches = count(summary, "uncertain")
    feed = count(summary, "unindexed_definitions")
    reasons = []
    if source:
        reasons.append(
            f"{source} reported Debian packages lack source-package names/versions. Check source-package collection and obtain a fresh inventory report; update the client if needed."
        )
    if ubuntu_source:
        reasons.append(
            f"{ubuntu_source} reported Ubuntu packages lack a usable source-package name/version. Check source-package collection and obtain a fresh report; update the client if needed."
        )
    if rules:
        reasons.append(
            f"{rules} vendor definitions associated with reported package names could not be decided with supported facts."
        )
    if matches:
        reasons.append(
            f"{matches} package/definition/CVE associations remain unresolved. These are not confirmed vulnerable installations."
        )
    for code, label in REASONS.items():
        value = count(summary.get("uncertainty_reasons") or {}, code)
        if value:
            reasons.append(f"{value} unresolved associations: {label}.")
    kernel = summary.get("kernel") or {}
    kernel_state = kernel.get("state")
    if kernel_state in {"shared_host_required", "scope_required", "kernel_build_not_covered", "partial"}:
        messages = {
            "shared_host_required": "A shared container kernel was reported. Assess the hosting system using its own distribution and inventory; the guest feed cannot establish host-kernel affectedness.",
            "scope_required": "Kernel ownership is unknown. Obtain an explicit host/shared-kernel scope from a current client; unresolved detection needs operator review.",
            "kernel_build_not_covered": "The reported kernel build has no supported flavor/ABI guard in this release's feed; do not infer it is unaffected.",
            "partial": "Some running-kernel conditions remain unresolved.",
        }
        reasons.append(messages[kernel_state])
    if feed:
        reasons.append(
            f"{feed} definitions in the entire vendor feed cannot be indexed. Their relevance to this host is unknown; this feed-wide count is not a host-specific finding."
        )
    if not reasons:
        reasons.append(
            "The stored partial result does not identify which limitation caused it. No server change can be recommended from this status alone."
        )
    return {
        "actionable": bool(source or ubuntu_source),
        "title": "Supply missing source-package facts"
        if source or ubuntu_source
        else "Recorded package-check limitations",
        "reason": " ".join(reasons),
        "items": reasons,
        "guidance": "A package update or client restart is not indicated by coverage limits alone. The platform operator can inspect evaluator support; assess actual CVE/version evidence separately.",
    }


def reasons_for(receipt):
    reasons = set()
    samples = (receipt.get("samples") or {}).get("unknown", [])
    for sample in samples[:10]:
        proof = sample.get("package_check") or {}
        if proof.get("uncertainty_reason") in REASONS:
            reasons.add(REASONS[proof["uncertainty_reason"]].capitalize() + ".")
        conditions = proof.get("unresolved_conditions") or []
        if not conditions and proof.get("version_checked") is False:
            reasons.add("The vendor rule supplies no affected/fixed version boundary.")
        for condition in conditions[:16]:
            # Fixed labels only: do not echo arbitrary vendor text or CVE identities.
            if condition == "Host architecture is not reported":
                reasons.add("Host architecture is missing; check OS metadata in the client report.")
            elif condition.startswith("Unsupported package condition:"):
                field = condition.split(":", 1)[1].strip()
                labels = {
                    "signature_keyid": "Package-signature identity required by the vendor rule is not supported by the evaluator.",
                    "signaturekeyid": "Package-signature identity required by the vendor rule is not supported by the evaluator.",
                    "modularitylabel": "The RPM module label required by the vendor rule is not supported by the evaluator.",
                }
                reasons.add(
                    labels.get(field, "A required package property is not supported by the evaluator.")
                )
            elif "architecture" in condition:
                reasons.add("The vendor architecture constraint is not supported by the evaluator.")
            elif "variable" in condition:
                reasons.add("The vendor rule uses an unsupported version/architecture variable.")
            elif "object set" in condition:
                reasons.add("The vendor rule uses an unsupported inventory object set.")
            elif "OS inventory" in condition or condition.startswith("Unsupported host condition:"):
                reasons.add("The vendor rule needs host facts outside the supported inventory.")
            else:
                reasons.add("The vendor rule contains a condition unsupported by the evaluator.")
    return sorted(reasons) or [
        "The stored package proof does not specify the remaining condition. Inspect package evidence; no host change is established."
    ]


def examples(device, summary, feed):
    """At most five current scoped package examples; no findings or CVE IDs exposed."""
    if not count(summary, "uncertain") and not count(summary, "missing_source_metadata"):
        return []
    if (
        not settings.DISTRO_CVE_ENABLED
        or not feed
        or device.distro_requested
        or summary.get("generation") != str(feed.generation)
        or summary.get("evaluator_version") != distro_results.VERSION
        or AgentReport.objects.filter(device=device, status="pending").exists()
    ):
        return []
    source_missing = count(summary, "missing_source_metadata") > 0 and feed.key.startswith("debian:")
    selection = Q(distro_check__counts__unknown__gt=0)
    if source_missing:
        selection |= Q(package_source={})
    candidates = (
        device.components.filter(
            recent_component(),
            selection,
            missing_since__isnull=True,
            manager__in=["dpkg", "rpm"],
            installation__asset_id=device.asset_id,
            installation__asset__source_id=device.source_id,
            installation__product__organization_id=device.organization_id,
            package_identity__distribution=device.os.get("id"),
            package_identity__release=device.os.get("version"),
        )
        .only(
            "name",
            "version",
            "package_source",
            "package_identity",
            "distro_check",
            "installation_id",
            "last_report_id",
        )
        .order_by("name", "pk")[:6]
    )
    candidates = list(candidates)
    from .ubuntu_status import receipt_flags

    status_flags = receipt_flags(candidates)
    result = []
    for component in candidates:
        if not status_flags.get(component.pk, True):
            continue
        receipt = component.distro_check
        if not distro_results.receipt_matches_inputs(component, device, feed):
            continue
        missing = source_missing and not component.package_source
        result.append(
            {
                "name": component.name,
                "version": component.version,
                "reasons": ["Source-package name/version is missing from the report."]
                if missing
                else reasons_for(receipt),
                "url": reverse("asset", args=[device.organization.slug, device.asset_id])
                + "?"
                + urlencode({"software_q": component.name})
                + "#software",
            }
        )
        if len(result) == 5:
            break
    return result
