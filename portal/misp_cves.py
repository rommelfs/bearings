"""Version decisions for the published MISP advisory formats we can compare."""

import re

RULE = "misp-vendor-versions/v1"
GITHUB = "a0819718-46f1-4df5-94e2-005712e83aaa"
CIRCL = "5a6e4751-2f3f-4070-9419-94fb35b644e8"
RELEASE = r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}"
GHSA = re.compile(
    r"https://github\.com/MISP/MISP/security/advisories/GHSA-(?:[a-z0-9]{4}-){2}[a-z0-9]{4}", re.I | re.ASCII
)
COMMIT = re.compile(r"https://github\.com/MISP/MISP/commit/[a-f0-9]{40}", re.I | re.ASCII)
QUALIFIERS = ("platforms", "modules", "programRoutines", "programFiles")


def is_misp(watch):
    return (watch.vendor.casefold(), watch.product_key.casefold()) == ("misp", "misp")


def evaluate(watch, installation, cna, entries, semver):
    if not is_misp(watch) or installation.build or installation.edition or not entries:
        return None
    if not re.fullmatch(RELEASE, installation.version):
        return None
    provider = cna.get("providerMetadata")
    references = cna.get("references")
    if not isinstance(provider, dict) or not isinstance(references, list):
        return None
    urls = [r.get("url") for r in references if isinstance(r, dict) and isinstance(r.get("url"), str)]
    github = provider.get("orgId") == GITHUB and any(GHSA.fullmatch(url) for url in urls)
    circl = provider.get("orgId") == CIRCL and any(
        GHSA.fullmatch(url) or COMMIT.fullmatch(url) for url in urls
    )
    if not (github or circl):
        return None

    ranges = []
    for entry in entries:
        if (
            str(entry.get("vendor", "")).casefold() != "misp"
            or str(entry.get("product", "")).casefold() != "misp"
            or any(entry.get(key) for key in QUALIFIERS)
            or entry.get("defaultStatus") not in (None, "unaffected")
            or (circl and entry.get("defaultStatus") != "unaffected")
        ):
            return None
        versions = entry.get("versions")
        if not isinstance(versions, list) or not versions:
            return None
        for rule in versions:
            if not isinstance(rule, dict) or rule.get("status") != "affected" or rule.get("changes"):
                return None
            start = rule.get("version")
            if github:
                if not isinstance(start, str) or rule.get("lessThan") or rule.get("lessThanOrEqual"):
                    return None
                match = re.fullmatch(r"(<=?)\s*(" + RELEASE + ")", start)
                if not match:
                    return None
                operator, bound = match.groups()
                ranges.append(((0, 0, 0), semver(bound), operator == "<="))
            else:
                exclusive = rule.get("lessThan")
                inclusive = rule.get("lessThanOrEqual")
                bound = exclusive or inclusive
                if (
                    rule.get("versionType") != "semver"
                    or bool(exclusive) == bool(inclusive)
                    or not isinstance(start, str)
                    or not isinstance(bound, str)
                    or (start != "0" and not re.fullmatch(RELEASE, start))
                    or not re.fullmatch(RELEASE, bound)
                ):
                    return None
                low = (0, 0, 0) if start == "0" else semver(start)
                high = semver(bound)
                if low > high:
                    return None
                ranges.append((low, high, bool(inclusive)))

    version = semver(installation.version)
    if any(
        low <= version and (version < high or inclusive and version == high)
        for low, high, inclusive in ranges
    ):
        return "potential", "The installed MISP release matches a published affected-version range."
    return "not_affected", "The installed MISP release is outside the published affected-version ranges."
