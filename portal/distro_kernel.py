"""Restricted Canonical uname/local-variable support; never execute vendor expressions."""

import re
from . import distro_oval

TRANSFORM_PATTERN = r"^([\d|\.]+-\d+)[-|\w]+$"


def expression(e, objects):
    """Recognize exactly Canonical's 0: + captured uname Ubuntu ABI expression."""
    if e.get("datatype") != "debian_evr_string" or len(e) != 1:
        return None
    concat = e[0]
    if distro_oval.local(concat.tag) != "concat" or len(concat) != 2:
        return None
    literal, capture = concat
    if (
        distro_oval.local(literal.tag) != "literal_component"
        or literal.text != "0:"
        or distro_oval.local(capture.tag) != "regex_capture"
        or capture.get("pattern") != TRANSFORM_PATTERN
        or set(capture.attrib) != {"pattern"}
        or literal.attrib
        or concat.attrib
        or len(capture) != 1
    ):
        return None
    reference = capture[0]
    obj = objects.get(reference.get("object_ref"), {})
    if (
        distro_oval.local(reference.tag) != "object_component"
        or reference.get("item_field") != "os_release"
        or set(reference.attrib) != {"item_field", "object_ref"}
        or obj != {}
    ):
        return None
    return {"kind": "ubuntu-kernel-abi", "object": reference.get("object_ref")}


def abi(kernel):
    if not isinstance(kernel, str) or len(kernel) > 120:
        return None
    value = re.fullmatch(r"([0-9]+(?:\.[0-9]+)*-[0-9]+)-[A-Za-z0-9_-]+", kernel)
    return "0:" + value[1] if value else None


def release_condition(kernel, state):
    """Safe subset of literal Ubuntu series + ABI digits + literal flavor alternatives."""
    if state.get("operation", "equals") == "equals":
        return kernel == state.get("text") if kernel else None
    pattern = state.get("text", "")
    if state.get("operation") != "pattern match" or len(pattern) > 256:
        return None
    # No vendor-controlled regex is executed. Parse literals and the one supported digit run.
    parts = pattern.split(r"\d+")
    if len(parts) != 2:
        return None
    series, flavors = parts
    series = series.replace(r"\.", ".").replace(r"\-", "-")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*-", series):
        return None
    if not (flavors.startswith("(") and flavors.endswith(")")):
        return None
    literals = [s.replace(r"\-", "-") for s in flavors[1:-1].split("|")]
    if not literals or not all(re.fullmatch(r"-[A-Za-z0-9_-]+", s) for s in literals):
        return None
    if not abi(kernel):
        return None
    # OVAL pattern match uses search semantics; preserve them for this bounded literal grammar.
    return any(re.search(re.escape(series) + r"[0-9]+" + re.escape(s), kernel) is not None for s in literals)


def evaluate(node, os):
    if os.get("kernel_scope") != "host":
        return None
    kernel = os.get("kernel", "")
    if "kernel_states" in node:
        value = abi(kernel)
        if value is None:
            return None
        if not node["kernel_states"]:
            return True
        return distro_oval.combine(
            "AND",
            [
                distro_oval.condition(value, {**s, "field": "evr"}, "dpkg")
                if s.get("field") == "value" and s.get("datatype") == "debian_evr_string"
                else None
                for group in node["kernel_states"]
                for s in group
            ],
        )
    values = []
    for group in node.get("host_states", []):
        values.append(
            distro_oval.combine(
                "AND",
                [
                    release_condition(kernel, s)
                    if s.get("field") == "os_release"
                    else distro_oval.condition(os.get("architecture", ""), s, "rpm")
                    if s.get("field") == "machine_class"
                    else None
                    for s in group
                ],
            )
        )
    return distro_oval.combine("AND", values)


def receipt(device, feed, deadline, facts=None, complete=False):
    """Account for every compiled runtime-kernel definition independently of packages."""
    import time
    from django.utils import timezone
    from .intelligence import digest
    from .models import DistroAdvisory, DistroKernelRevision
    from .connectors.http import ConnectorError

    scope = device.os.get("kernel_scope", "unknown")
    if device.asset.virtualization_type in {"lxc", "openvz", "container"}:
        scope = "shared"
    total = feed.summary.get("kernel_definitions", 0)
    result = {
        "schema": "bearings.kernel-check.v1",
        "scope": scope,
        "kernel": device.os.get("kernel", ""),
        "feed": feed.key,
        "generation": str(feed.generation),
        "checked_at": timezone.now().isoformat(),
        "input_hash": digest({"os": device.os, "virtualization": device.asset.virtualization_type}),
        "definitions": total,
        "counts": {"matched": 0, "not_matched": 0, "unresolved": 0},
        "samples": {"matched": [], "not_matched": [], "unresolved": []},
    }
    evidence = {
        "os": device.os,
        "virtualization": device.asset.virtualization_type,
        "feed_sha256": feed.content_hash,
        "source_id": str(device.source_id),
        "organization_id": device.organization_id,
        "receipt": result,
        "rules": {},
        "matches": [],
    }

    def finish():
        snapshot = {**evidence, "receipt": {k: v for k, v in result.items() if k != "checked_at"}}
        fingerprint = digest(snapshot)
        revision, _ = DistroKernelRevision.objects.get_or_create(
            device=device,
            fingerprint=fingerprint,
            defaults={"snapshot": {**snapshot, "checked_at": result["checked_at"]}},
        )
        result["evidence_revision"] = revision.pk
        return result

    if not total:
        result["state"] = "not_available"
        return result
    if scope != "host":
        result["state"] = "shared_host_required" if scope == "shared" else "scope_required"
        result["counts"]["unresolved"] = total
        return finish()
    supported = False
    seen = 0
    evidence_size = 0

    def supported_guard(node):
        return any(
            release_condition(device.os.get("kernel", ""), s) is True
            for group in node.get("host_states", [])
            for s in group
            if s.get("field") == "os_release"
        ) or any(supported_guard(c) for c in node.get("children", []))

    rows = DistroAdvisory.objects.filter(
        feed=feed,
        generation=feed.generation,
        distroadvisorypackage__manager="kernel",
        distroadvisorypackage__name="runtime",
    ).distinct()
    for advisory in rows.iterator(chunk_size=50):
        if time.monotonic() > deadline:
            raise ConnectorError("Device evaluation time budget exceeded")
        seen += 1
        supported = supported or supported_guard(advisory.criteria)
        truth, outcomes = distro_oval.evaluate_matches(advisory.criteria, facts or {}, complete, device.os)
        value = False if truth is False else outcomes.get("__runtime_kernel__")
        kind = "matched" if value is True else "not_matched" if value is False else "unresolved"
        result["counts"][kind] += 1
        if kind == "matched":
            import json

            rule_hash = digest(advisory.criteria)
            if rule_hash not in evidence["rules"]:
                evidence["rules"][rule_hash] = advisory.criteria
                evidence_size += len(json.dumps(advisory.criteria))
            entry = {
                "definition": advisory.identity,
                "cves": advisory.metadata["cves"],
                "rule_sha256": advisory.content_hash,
                "criteria_hash": rule_hash,
                "severity": advisory.metadata.get("severity", "unknown"),
                "comparisons": comparisons(advisory.criteria, device.os, facts, complete),
            }
            evidence_size += len(json.dumps(entry))
            if evidence_size > 16 * 1024 * 1024:
                raise ConnectorError("Kernel evidence budget exceeded; no partial evaluation published")
            evidence["matches"].append(entry)
        if len(result["samples"][kind]) < 10:
            result["samples"][kind].append(
                {
                    "definition": advisory.identity,
                    "cves": advisory.metadata["cves"][:10],
                    "rule_sha256": advisory.content_hash,
                }
            )
    if seen != total:
        raise ConnectorError("Kernel definition accounting incomplete")
    if not supported:
        result["state"] = "kernel_build_not_covered"
        result["counts"] = {"matched": 0, "not_matched": 0, "unresolved": total}
        result["samples"] = {"matched": [], "not_matched": [], "unresolved": []}
        evidence["rules"] = {}
        evidence["matches"] = []
    else:
        result["state"] = "partial" if result["counts"]["unresolved"] else "evaluated"
    return finish()


def comparisons(node, os, facts=None, complete=False):
    """Only positive named-kernel witnesses, never another OR branch's threshold."""
    if distro_oval.evaluate_matches(node, facts or {}, complete, os)[1].get("__runtime_kernel__") is not True:
        return []
    if "children" in node:
        return [v for child in node["children"] for v in comparisons(child, os, facts, complete)]
    return [
        {
            "installed_version": abi(os.get("kernel", "")),
            "operation": s.get("operation", "equals"),
            "vendor_version": s.get("text", ""),
            "basis": "reported running-kernel Ubuntu ABI",
        }
        for group in node.get("kernel_states", [])
        for s in group
        if s.get("field") == "value"
        and distro_oval.condition(abi(os.get("kernel", "")), {**s, "field": "evr"}, "dpkg") is True
    ]
