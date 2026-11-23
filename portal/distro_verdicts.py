"""Package-version verdicts are separate from local exploitability and human workflow."""


def decorate_package_verdict(finding):
    try:
        match = finding.distro_match
    except finding.__class__.distro_match.RelatedObjectDoesNotExist:
        finding.package_verdict = None
        return
    if match.inputs_changed:
        finding.package_verdict = {
            "heading": "Awaiting current package evaluation",
            "reason": "Inventory, vendor rules, cache freshness or evaluation logic changed. The retained result is historical until reevaluated.",
            "comparisons": [],
            "vendor_comments": [],
            "current": False,
        }
        return
    proof = match.snapshot.get("package_check", {})
    finding.package_verdict = {
        **proof,
        "update": update_context(match, proof),
        "heading": {
            "affected": "Affected package version — vendor rule matched",
            "fixed": "Installed package version includes the vendor fix",
            "not_matched": "Not affected under this vendor rule",
            "unresolved": "Package affectedness unresolved",
        }.get(proof.get("verdict"), "Package affectedness unresolved"),
        "current": True,
        "ubuntu_status_refresh_error": bool(match.ubuntu_status_id and match.ubuntu_status.error),
        "evaluated_at": match.evaluated_at,
        "feed": match.snapshot.get("feed"),
        "package": match.component.name,
        "version": match.snapshot.get("version"),
    }


def update_context(match, proof):
    """Explain a vendor-listed fix; do not infer repository/entitlement availability."""
    import re
    import shlex

    result = {"targets": [], "esm_apps": False, "package_context": "", "check_command": ""}
    if proof.get("verdict") != "affected":
        return result
    comments = proof.get("vendor_comments", [])
    # Only expose a target explicitly called fixed by the vendor, paired with
    # this component's satisfied strict version predicate. No arbitrary upper
    # bound, sibling-package description or free-text command becomes advice.
    for comparison in proof.get("comparisons", []):
        bound = comparison.get("vendor_version", "")
        if not bound or comparison.get("operation") != "less than" or comparison.get("matches") is not True:
            continue
        notes = [note for note in comments if f"has been fixed (note: '{bound}')" in note]
        if notes:
            target = {
                "version": bound,
                "basis": comparison.get("basis", "package"),
                "installed": comparison.get("installed_version", ""),
            }
            if target not in result["targets"]:
                result["targets"].append(target)
            if match.snapshot.get("feed", "").startswith("ubuntu:") and any(
                "esm-apps/" in note for note in notes
            ):
                result["esm_apps"] = True
    name = match.component.name
    if match.component.manager == "dpkg" and re.fullmatch(r"[a-z0-9][a-z0-9+.-]{0,127}", name):
        result["check_command"] = "apt-cache policy " + shlex.quote(name)
    # Audited Ubuntu packaging fact, not a vulnerability-matching heuristic.
    # Ubuntu's CVE tracker documents bundled urllib3 in python-pip from jammy.
    # Keep this hint limited to these releases/packages and urllib3 advisories.
    description = str(match.advisory.metadata.get("description", ""))
    if (
        match.snapshot.get("feed") in {"ubuntu:22.04", "ubuntu:24.04", "ubuntu:26.04"}
        and name in {"python3-pip", "python3-pip-whl"}
        and "urllib3" in description.lower()
    ):
        result["package_context"] = (
            "Ubuntu's python-pip packages contain a bundled copy of urllib3. This rule checks that copy through the pip package version. Updating the separate python3-urllib3 package does not establish that pip's bundled copy is fixed."
        )
    return result
