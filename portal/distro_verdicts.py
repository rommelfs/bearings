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


def vendor_fix_targets(proof, feed):
    """Pair a satisfied strict version boundary with an explicit vendor fix note."""
    targets = []
    comparisons = proof.get("comparisons")
    comments = proof.get("vendor_comments")
    if not isinstance(comparisons, list) or not isinstance(comments, list):
        return targets
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            continue
        bound = comparison.get("vendor_version")
        if (
            not isinstance(bound, str)
            or not bound
            or comparison.get("operation") != "less than"
            or comparison.get("matches") is not True
        ):
            continue
        notes = [
            note for note in comments if isinstance(note, str) and f"has been fixed (note: '{bound}')" in note
        ]
        if not notes:
            continue
        channels = []
        if feed.startswith("ubuntu:"):
            for pocket, label in (
                ("esm-apps", "Ubuntu ESM Apps / Ubuntu Pro"),
                ("esm-infra", "Ubuntu ESM Infra / Ubuntu Pro"),
            ):
                if any(" in " + pocket + "/" in note for note in notes):
                    channels.append(label)
        target = {
            "version": bound,
            "basis": comparison.get("basis") or "package",
            "installed": comparison.get("installed_version") or "",
            "channels": channels,
        }
        if target not in targets:
            targets.append(target)
    return targets


def update_context(match, proof):
    """Explain a vendor-listed fix and keep host availability unverified."""
    import re
    import shlex

    result = {
        "targets": [],
        "esm_apps": False,
        "esm_infra": False,
        "channels": [],
        "package_context": "",
        "check_command": "",
    }
    if proof.get("verdict") != "affected":
        return result
    targets = vendor_fix_targets(proof, match.snapshot.get("feed", ""))
    result["targets"] = targets
    result["channels"] = list(dict.fromkeys(channel for target in targets for channel in target["channels"]))
    result["esm_apps"] = "Ubuntu ESM Apps / Ubuntu Pro" in result["channels"]
    result["esm_infra"] = "Ubuntu ESM Infra / Ubuntu Pro" in result["channels"]
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
