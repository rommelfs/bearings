"""Bounded package-check receipts, separate from findings and human assessments."""

from collections import defaultdict
from . import distro_oval, distro_sources
from .intelligence import digest

VERSION = 1
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
            elif distro_oval.condition(fact["architecture"], state, leaf["manager"]) is not True:
                return None
    return thresholds[0] if len(thresholds) == 1 else None


class Collector:
    def __init__(self):
        self.results = defaultdict(dict)
        self.rules = defaultdict(set)
        self.total = 0

    def add(self, advisory, facts, result, contributors, os):
        leaves = defaultdict(list)
        for cid, leaf, fact in package_leaves(advisory.criteria, facts):
            leaves[cid].append((leaf, fact))
        safe = (
            safe_tree(advisory.criteria)
            and distro_oval.evaluate(guard_tree(advisory.criteria), {}, True, os)[0] is True
        )
        for cid, tests in leaves.items():
            self.rules[cid].add(advisory.pk)
            thresholds = [fixed_threshold(leaf, fact) for leaf, fact in tests] if safe else []
            fixed = result is False and thresholds and all(thresholds)
            outcome = (
                ("potential" if result is True else "unknown")
                if cid in contributors
                else ("fixed" if fixed else "not_matched" if result is False else "unknown")
            )
            for cve in advisory.metadata["cves"]:
                previous = self.results[cid].get(cve)
                if previous is not None and PRIORITY[previous["result"]] <= PRIORITY[outcome]:
                    continue
                if previous is None:
                    self.total += 1
                    if self.total > MAX_OUTCOMES:
                        from .connectors.http import ConnectorError

                        raise ConnectorError("Package result budget exceeded; no partial checks published")
                self.results[cid][cve] = {
                    "cve": cve,
                    "result": outcome,
                    "definition": advisory.identity,
                    "rule_sha256": advisory.content_hash,
                    "fixed_version": thresholds[0] if fixed else "",
                    "compared_version": tests[0][1]["version"] if fixed else "",
                    "comparison_basis": "source package"
                    if fixed and tests[0][0]["source"]
                    else "binary package",
                }

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
        }
