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
        "heading": {
            "affected": "Affected package version — vendor rule matched",
            "fixed": "Installed package version includes the vendor fix",
            "not_matched": "Not affected under this vendor rule",
            "unresolved": "Package affectedness unresolved",
        }.get(proof.get("verdict"), "Package affectedness unresolved"),
        "current": True,
        "evaluated_at": match.evaluated_at,
        "feed": match.snapshot.get("feed"),
        "package": match.component.name,
        "version": match.snapshot.get("version"),
    }
