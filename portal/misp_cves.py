"""Version decisions for the published MISP advisory formats we can compare."""

import re

RULE = "misp-vendor-versions/v3"
COMPATIBLE_PROOFS = (RULE, "misp-vendor-versions/v2", "misp-vendor-versions/v1")
GITHUB = "a0819718-46f1-4df5-94e2-005712e83aaa"
CIRCL = "5a6e4751-2f3f-4070-9419-94fb35b644e8"
MITRE = "8254265b-2729-46b6-b9e3-3dfca2d5bfca"
RELEASE = r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}"
GHSA = re.compile(
    r"https://github\.com/MISP/MISP/security/advisories/GHSA-(?:[a-z0-9]{4}-){2}[a-z0-9]{4}", re.I | re.ASCII
)
COMMIT = re.compile(r"https://github\.com/MISP/MISP/commit/[a-f0-9]{40}", re.I | re.ASCII)
PATCH_COMMIT = re.compile(r"https://github\.com/MISP/MISP/commit/[a-f0-9]{7,40}(?:\.patch)?", re.I | re.ASCII)
REPOSITORY = "https://github.com/misp/misp"
BOUND = re.compile(r"(<=?)\s*(" + RELEASE + r")", re.ASCII)
BEFORE = re.compile(
    r"(?:An issue was discovered in )?MISP before (" + RELEASE + r")(?=\s|[.,;)](?![\w.])|$)",
    re.I | re.ASCII,
)
COMPARE = re.compile(
    r"https://github\.com/MISP/MISP/compare/v(" + RELEASE + r")\.\.\.v(" + RELEASE + r")",
    re.I | re.ASCII,
)
OUTSIDE = ("not_affected", "The installed MISP release is outside the published affected-version ranges.")


def legacy_mitre_exclusion(cna, urls, version, semver):
    # Legacy MITRE records sometimes omit all structured product data. Require
    # the CNA's explicit fixed release and the same target in a MISP tag comparison.
    if cna.get("affected") != [
        {"vendor": "n/a", "product": "n/a", "versions": [{"version": "n/a", "status": "affected"}]}
    ]:
        return None
    descriptions = cna.get("descriptions")
    if not isinstance(descriptions, list):
        return None
    english = [
        item.get("value") for item in descriptions if isinstance(item, dict) and item.get("lang") == "en"
    ]
    if len(english) != 1 or not isinstance(english[0], str):
        return None
    before = BEFORE.match(english[0])
    comparisons = [match.groups() for url in urls if (match := COMPARE.fullmatch(url))]
    if not before or len(comparisons) != 1:
        return None
    previous, fixed = comparisons[0]
    if before[1] == fixed and semver(previous) < semver(fixed) <= version:
        return OUTSIDE
    return None


def structured_range(rule, semver, *, circl_patch=False):
    start = rule.get("version")
    if not isinstance(start, str):
        return None
    exclusive, inclusive = rule.get("lessThan"), rule.get("lessThanOrEqual")
    if not (exclusive or inclusive):
        if exclusive is not None or inclusive is not None or rule.get("versionType") not in (None, "semver"):
            return None
        return (semver(start), semver(start), True) if re.fullmatch(RELEASE, start) else None
    bound = exclusive or inclusive
    if (
        rule.get("versionType") != "semver"
        or (exclusive is not None and inclusive is not None)
        or not isinstance(bound, str)
        or not re.fullmatch(RELEASE, bound)
    ):
        return None
    if circl_patch and (comparison := BOUND.fullmatch(start)):
        if comparison.groups() != ("<=" if inclusive else "<", bound):
            return None
        start = "0"
    if start == "0" or (circl_patch and start == "unspecified"):
        low = (0, 0, 0)
    elif re.fullmatch(RELEASE, start):
        low = semver(start)
    else:
        return None
    high = semver(bound)
    return (low, high, bool(inclusive)) if low <= high else None


def is_misp(watch):
    return (watch.vendor.casefold(), watch.product_key.casefold()) == ("misp", "misp")


def evaluate(watch, installation, cna, entries, semver):
    if not is_misp(watch) or not isinstance(cna, dict) or installation.build or installation.edition:
        return None
    if not re.fullmatch(RELEASE, installation.version):
        return None
    provider = cna.get("providerMetadata")
    references = cna.get("references")
    if not isinstance(provider, dict) or not isinstance(references, list):
        return None
    version = semver(installation.version)
    urls = [r.get("url") for r in references if isinstance(r, dict) and isinstance(r.get("url"), str)]
    mitre = provider.get("orgId") == MITRE
    if not entries:
        return legacy_mitre_exclusion(cna, urls, version, semver) if mitre else None
    github = provider.get("orgId") == GITHUB and any(GHSA.fullmatch(url) for url in urls)
    circl = provider.get("orgId") == CIRCL and any(
        GHSA.fullmatch(url) or COMMIT.fullmatch(url) for url in urls
    )
    circl_patch = provider.get("orgId") == CIRCL and any(
        isinstance(ref, dict)
        and "patch" in (ref.get("tags") if isinstance(ref.get("tags"), list) else [])
        and isinstance(ref.get("url"), str)
        and PATCH_COMMIT.fullmatch(ref["url"])
        for ref in references
    )
    if not (github or circl or circl_patch or mitre):
        return None

    ranges = []
    upper_bounds_without_default = []
    for entry in entries:
        repo = entry.get("repo")
        repo_patch = circl_patch and isinstance(repo, str) and repo.casefold() == REPOSITORY
        default = entry.get("defaultStatus")
        if (
            str(entry.get("vendor", "")).casefold() != "misp"
            or str(entry.get("product", "")).casefold() != "misp"
            or entry.get("platforms")
            or (
                any(entry.get(key) for key in ("modules", "programFiles", "programRoutines"))
                and not repo_patch
            )
            or default not in (None, "unaffected")
            or (mitre and default != "unaffected")
        ):
            return None
        if not github and default is None and not repo_patch:
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
                match = BOUND.fullmatch(start)
                if not match:
                    return None
                operator, bound = match.groups()
                ranges.append(((0, 0, 0), semver(bound), operator == "<="))
            else:
                interval = structured_range(rule, semver, circl_patch=repo_patch)
                if interval is None:
                    return None
                ranges.append(interval)
                if default is None:
                    has_upper_bound = rule.get("lessThan") or rule.get("lessThanOrEqual")
                    upper_bounds_without_default.append(interval[1:] if has_upper_bound else (None, False))

    if any(
        low <= version and (version < high or inclusive and version == high)
        for low, high, inclusive in ranges
    ):
        return "potential", "The installed MISP release matches a published affected-version range."
    if any(
        high is None or version < high or inclusive and version == high
        for high, inclusive in upper_bounds_without_default
    ):
        return None
    return OUTSIDE
