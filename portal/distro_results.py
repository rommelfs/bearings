"""Bounded package-check receipts, separate from findings and human assessments."""

from collections import defaultdict
from itertools import islice
from . import distro_oval, distro_sources
from .intelligence import digest

VERSION = 3
SAMPLE_LIMIT = 10
MAX_OUTCOMES = 100000
PRIORITY = {"potential": 0, "unknown": 1, "not_matched": 2, "fixed": 3}


def inputs(component, device):
    return digest(
        {
            "installation": component.installation_id,
            "version": component.version,
            "identity": component.package_identity,
            "source": component.package_source,
            "report": str(component.last_report_id),
            "os": device.os,
        }
    )


def receipt_matches_inputs(component, device, feed):
    receipt = component.distro_check
    return (
        receipt.get("version") == VERSION
        and receipt.get("generation") == str(feed.generation)
        and receipt.get("input_hash") == inputs(component, device)
    )


def has_version_conditions(node):
    return any(state.get("field") == "evr" for group in node.get("states", []) for state in group) or any(
        has_version_conditions(child) for child in node.get("children", [])
    )


def unsupported_conditions(node, os):
    if "unknown" in node:
        yield str(node["unknown"])[:160]
    for group in node.get("host_states", []):
        for state in group:
            if state.get("field") != "machine_class":
                yield "Unsupported host condition: " + str(state.get("field"))[:80]
            elif not os.get("architecture"):
                yield "Host architecture is not reported"
            elif distro_oval.condition(os["architecture"], state, "rpm") is None:
                yield "Unsupported host architecture constraint: " + str(state.get("text", ""))[:100]
    if "package" in node:
        if node.get("check") not in {"all", "at least one"}:
            yield "Unsupported package check: " + str(node.get("check"))[:80]
        if node.get("existence") not in {"at_least_one_exists", "any_exist", "none_exist"}:
            yield "Unsupported package existence condition: " + str(node.get("existence"))[:80]
        for group in node.get("states", []):
            for state in group:
                if state.get("field") not in {"evr", "arch"}:
                    yield "Unsupported package condition: " + str(state.get("field"))[:80]
                elif state.get("var_ref"):
                    yield "Version/architecture variable is not supported: " + str(state["var_ref"])[:80]
                elif (
                    state.get("field") == "arch"
                    and distro_oval.condition("_", state, node["manager"]) is None
                ):
                    yield "Unsupported package architecture constraint: " + str(state.get("text", ""))[:100]
    for child in node.get("children", []):
        yield from unsupported_conditions(child, os)


def rule_leaves(node):
    if "package" in node:
        yield node
    for child in node.get("children", []):
        yield from rule_leaves(child)


def package_leaves(node, facts):
    """Find only reported components explicitly named by this vendor definition."""
    if "package" in node:
        for name in node["package"]:
            for fact in facts.get((node["manager"], bool(node["source"]), name), []):
                yield fact["id"], node, fact
    for child in node.get("children", []):
        yield from package_leaves(child, facts)


def safe_tree(node):
    return (
        not node.get("negate")
        and node.get("operator") != "NOT"
        and all(safe_tree(c) for c in node.get("children", []))
    )


def guard_tree(node):
    if "package" in node:
        return {"constant": True}
    if "children" in node:
        return {**node, "children": [guard_tree(c) for c in node["children"]]}
    return node


def fixed_threshold(leaf, fact):
    """Prove a native '< fixed version' comparison failed, not an arbitrary false condition."""
    if (
        leaf.get("negate")
        or leaf.get("state_operator") != "AND"
        or leaf.get("check") not in {"all", "at least one"}
        or leaf.get("existence") not in {"at_least_one_exists", "any_exist"}
    ):
        return None
    thresholds = []
    for group in leaf.get("states", []):
        for state in group:
            if state.get("field") == "evr" and state.get("operation") == "less than":
                if distro_oval.condition(fact["version"], state, leaf["manager"]) is not False:
                    return None
                thresholds.append(state["text"])
            elif (
                state.get("field") != "arch"
                or distro_oval.condition(fact["architecture"], state, leaf["manager"]) is not True
            ):
                return None
    return thresholds[0] if len(thresholds) == 1 else None


class Collector:
    def __init__(self, resolver=None, components=None):
        self.results = defaultdict(dict)
        self.rules = defaultdict(set)
        self.total = 0
        self.details = {}
        self.cve_details = {}
        self.resolver = resolver
        self.components = components or {}

    def add(self, advisory, facts, result, contributors, os, complete=None):
        leaves = defaultdict(list)
        for cid, leaf, fact in package_leaves(advisory.criteria, facts):
            leaves[cid].append((leaf, fact))
        # Retain a hash of every fact used by the definition, not merely the
        # component being displayed: another package may be a required guard.
        dependencies = sorted(
            {
                (node["manager"], bool(node["source"]), name)
                for node in rule_leaves(advisory.criteria)
                for name in node["package"]
            }
        )
        context_hash = digest(
            {
                "facts": [
                    [
                        manager,
                        source,
                        name,
                        [
                            {"id": str(f["id"]), "version": f["version"], "architecture": f["architecture"]}
                            for f in sorted(
                                facts.get((manager, source, name), []), key=lambda row: str(row["id"])
                            )
                        ],
                    ]
                    for manager, source, name in dependencies
                ],
                "complete": complete,
                "os": os,
            }
        )
        missing_conditions = list(islice(unsupported_conditions(advisory.criteria, os), 16))
        safe = (
            safe_tree(advisory.criteria)
            and distro_oval.evaluate(guard_tree(advisory.criteria), {}, True, os)[0] is True
        )
        named_truths = {}
        if self.resolver and result is True and None in contributors.values():
            named_truths = distro_oval.evaluate_matches(
                advisory.criteria, facts, complete, os, version_required=False
            )[1]
        for cid, tests in leaves.items():
            self.rules[cid].add(advisory.pk)
            thresholds = [fixed_threshold(leaf, fact) for leaf, fact in tests] if safe else []
            component_result = contributors.get(cid)
            fixed = component_result is False and thresholds and all(thresholds)
            comparisons = []
            for leaf, fact in tests:
                for group in leaf.get("states", []):
                    for state in group:
                        if state.get("field") == "evr":
                            comparisons.append(
                                {
                                    "package": ", ".join(leaf["package"])[:200],
                                    "installed_version": fact["version"],
                                    "operation": state.get("operation", "equals"),
                                    "vendor_version": state.get("text", ""),
                                    "matches": distro_oval.condition(fact["version"], state, leaf["manager"]),
                                    "basis": "source package" if leaf["source"] else "binary package",
                                }
                            )
            reason = (
                "The reported version satisfies the vendor's affected-package version rule."
                if component_result is True
                else "The reported version is at or above the vendor's fixed version."
                if fixed
                else "This package does not satisfy the vendor's affected-package rule."
                if component_result is False
                else "The vendor rule checks package presence only and supplies no affected/fixed version condition. Package-version affectedness is unresolved."
                if not comparisons
                else "The vendor rule cannot be fully evaluated with the supported reported facts."
            )
            proof = {
                "schema": "bearings.package-check.v2",
                "context_hash": context_hash,
                "verdict": "affected"
                if component_result is True
                else "fixed"
                if fixed
                else "not_matched"
                if component_result is False
                else "unresolved",
                "reason": reason,
                "version_checked": bool(comparisons),
                "unresolved_conditions": missing_conditions if component_result is None else [],
                "comparisons": comparisons[:16],
                "vendor_comments": list(
                    dict.fromkeys(
                        leaf.get("vendor_comment", "") for leaf, _ in tests if leaf.get("vendor_comment")
                    )
                )[:4],
            }
            if (cid, advisory.pk) not in self.details and len(self.details) >= MAX_OUTCOMES:
                from .connectors.http import ConnectorError

                raise ConnectorError("Package proof budget exceeded; no partial checks published")
            self.details[cid, advisory.pk] = proof
            for cve in advisory.metadata["cves"]:
                cve_proof = proof
                if self.resolver and cid in self.components:
                    cve_proof = self.resolver(
                        self.components[cid],
                        cve,
                        proof,
                        component_result is None
                        and safe
                        and named_truths.get(cid) is True
                        and not comparisons
                        and not missing_conditions,
                    )
                cve_outcome = {"affected": "potential", "fixed": "fixed", "not_matched": "not_matched"}.get(
                    cve_proof["verdict"], "unknown"
                )
                if len(self.cve_details) >= MAX_OUTCOMES and (cid, advisory.pk, cve) not in self.cve_details:
                    from .connectors.http import ConnectorError

                    raise ConnectorError("Package result budget exceeded; no partial checks published")
                self.cve_details[cid, advisory.pk, cve] = cve_proof
                previous = self.results[cid].get(cve)
                if previous is not None and PRIORITY[previous["result"]] <= PRIORITY[cve_outcome]:
                    continue
                if previous is None:
                    self.total += 1
                    if self.total > MAX_OUTCOMES:
                        from .connectors.http import ConnectorError

                        raise ConnectorError("Package result budget exceeded; no partial checks published")
                self.results[cid][cve] = {
                    "cve": cve,
                    "result": cve_outcome,
                    "definition": advisory.identity,
                    "rule_sha256": advisory.content_hash,
                    "fixed_version": cve_proof["comparisons"][0]["vendor_version"]
                    if cve_outcome == "fixed" and cve_proof["comparisons"]
                    else "",
                    "compared_version": cve_proof["comparisons"][0]["installed_version"]
                    if cve_outcome == "fixed" and cve_proof["comparisons"]
                    else "",
                    "package_check": cve_proof,
                    "comparison_basis": "source package"
                    if cve_proof.get("ubuntu_status") or (fixed and tests[0][0]["source"])
                    else "binary package",
                }

    def proof(self, cid, aid, cve):
        return self.cve_details.get((cid, aid, cve), self.details.get((cid, aid), {}))

    def receipt(self, component, device, feed, checked_at):
        results = self.results[component.pk]
        counts = {key: 0 for key in PRIORITY}
        samples = {key: [] for key in PRIORITY}
        for cve in sorted(results, key=lambda c: tuple(int(x) for x in c.split("-")[1:]), reverse=True):
            row = results[cve]
            counts[row["result"]] += 1
            if len(samples[row["result"]]) < SAMPLE_LIMIT:
                samples[row["result"]].append(row)
        return {
            "version": VERSION,
            "input_hash": inputs(component, device),
            "generation": str(feed.generation),
            "feed": feed.key,
            "source_url": distro_sources.url_for(feed.key),
            "vendor_data_at": feed.last_success.isoformat(),
            "checked_at": checked_at.isoformat(),
            "reported_at": component.observed_at.isoformat(),
            "package_version": component.version,
            "rules_checked": len(self.rules[component.pk]),
            "counts": counts,
            "samples": samples,
            "sample_limit": SAMPLE_LIMIT,
            "ubuntu_status_hashes": {
                cve: proof["ubuntu_status"]["sha256"]
                for (cid, _, cve), proof in self.cve_details.items()
                if cid == component.pk and proof.get("ubuntu_status")
            },
        }
