"""Explain scoped review previews without inferring affectedness or exploitation."""

from urllib.parse import urlsplit


def review_explanation(finding):
    analyst = finding.analyst_applicability
    automatic = finding.applicability
    rule = finding.rule
    basis = {
        "manual-cve-review/v1": "CVE selected for review against this installation",
        "distro-oval-review/v1": "Distribution vendor package/version rule (OVAL)",
        "vendor-product-review/v1": "Configured vendor/product mapping and supported version rules",
    }.get(rule, "Saved review evidence; inspect the original review")
    reason = "Affected version or required configuration facts have not been established."
    payload = finding.record.payload
    distro = payload.get("bearings_distro", {}) if isinstance(payload, dict) else {}
    if rule == "distro-oval-review/v1" and isinstance(distro, dict):
        from .distro_results import has_version_conditions

        if distro.get("schema") == "bearings.distro-oval.v1" and not has_version_conditions(
            distro.get("criteria", {})
        ):
            basis = "Vendor package presence rule; no affected/fixed version condition"
            reason = "The vendor lists this package for investigation but supplies no version condition. Package affectedness is unresolved."
    action = (
        "Monitor vendor clarification or verify the bundled dependency evidence"
        if basis == "Vendor package presence rule; no affected/fixed version condition"
        else "Review the installed version, matching evidence and vendor fixes"
    )
    if analyst == "affected":
        reason = "An analyst has recorded this installation as affected."
        action = "Plan and verify remediation, or record an appropriate mitigation"
    elif analyst == "potential":
        reason = "An analyst has recorded possible affectedness; confirmation is still required."
    elif analyst == "unknown":
        reason = "An analyst has recorded affectedness as uncertain; more evidence is needed."
    elif (
        automatic == "potential"
        and basis != "Vendor package presence rule; no affected/fixed version condition"
    ):
        reason = "The saved automatic check indicates a potential match for this installation."
    if automatic == "not_affected":
        reason = "The saved automatic check says not affected, but the review is still open. Reconcile the saved assessment."
        action = "Compare the current evidence with the saved assessment and reconcile the review"
        if analyst == "affected":
            reason = "The analyst assessment says affected while the saved automatic check says not affected. These results need reconciliation."
    elif not finding.installation.version and analyst != "affected":
        reason = "The installed version is missing, so version-specific affectedness cannot be established."
        action = "Record the installed version, then review the matching evidence"
    source = "Recorded advisory"
    try:
        parsed = urlsplit(finding.record.source)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            source = parsed.hostname[:120]
    except ValueError:
        pass
    return {
        "reason": reason,
        "next_action": action,
        "product": finding.installation.product.name,
        "version": finding.installation.version or "Not reported",
        "assessment": {
            "affected": "Affected (analyst assessment)",
            "potential": "Possibly affected (analyst assessment)",
            "unknown": "Uncertain (analyst assessment)",
        }.get(analyst, "Not assessed"),
        "evaluated_at": finding.evaluated_at,
        "automatic": {"potential": "Potential match", "not_affected": "Not affected by recorded check"}.get(
            automatic, "Unresolved"
        )
        if automatic in {"potential", "not_affected"} or rule != "manual-cve-review/v1"
        else "No automatic version check recorded",
        "basis": basis,
        "source": source,
        "severity": finding.record.source_severity.title()
        if finding.record.source_severity != "unknown"
        else "Not supplied",
    }
