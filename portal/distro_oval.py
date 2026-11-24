"""Bounded OVAL subset. Unknown conditions stay unknown, never guessed true."""

import re
import math
import time
from functools import lru_cache
from defusedxml.ElementTree import iterparse
from univers.debian import compare_versions
from univers.rpm import compare_rpm_versions
from .connectors.http import ConnectorError

CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}")
COMPILER_VERSION = 4


def local(tag):
    return tag.rsplit("}", 1)[-1]


def entities(path, deadline):
    count = 0
    for _, e in iterparse(path, events=["end"], forbid_dtd=True):
        count += 1
        if count % 1000 == 0 and (count > 6000000 or time.monotonic() > deadline):
            raise ConnectorError("OVAL parse budget exceeded")
        tag = local(e.tag)
        if tag == "definition" or tag.endswith(("_object", "_state", "_test", "_variable")):
            yield tag, e
            e.clear()


def field(e):
    return {"text": (e.text or "").strip(), **e.attrib}


def compile_feed(path, distro, release, deadline=None, stats=None):
    """Two streaming passes: reference tables first, then complete definitions."""
    stats = stats if stats is not None else {}
    stats.update(
        definitions=0, unindexed_definitions=0, vendor_definitions=0, compiler_version=COMPILER_VERSION
    )
    deadline = deadline or time.monotonic() + 120
    tests, objects, states, variables, inventories = {}, {}, {}, {}, {}
    local_variables = {}
    object_types = {}
    seen_ids = set()
    for tag, e in entities(path, deadline):
        pk = e.get("id")
        if not pk or len(pk) > 200 or pk in seen_ids:
            raise ConnectorError("Duplicate/invalid OVAL identity")
        seen_ids.add(pk)
        if tag.endswith("_test"):
            tests[pk] = {
                "tag": tag,
                "attrs": dict(e.attrib),
                "objects": [x.get("object_ref") for x in e if local(x.tag) == "object"],
                "states": [x.get("state_ref") for x in e if local(x.tag) == "state"],
            }
        elif tag.endswith("_object"):
            object_types[pk] = tag
            objects[pk] = {local(x.tag): field(x) for x in e}
        elif tag.endswith("_state"):
            states[pk] = (
                [dict(field(x), field=local(x.tag)) for x in e]
                if e.get("operator", "AND") == "AND"
                else [{"field": "unsupported state operator"}]
            )
        elif tag == "local_variable":
            # Retain only a bounded expression shape; no evaluation of arbitrary functions.
            from copy import deepcopy

            if sum(1 for _ in e.iter()) <= 16:
                local_variables[pk] = deepcopy(e)
        elif tag == "constant_variable":
            variables[pk] = [(x.text or "").strip() for x in e if local(x.tag) == "value"]
        elif tag == "definition" and e.get("class") == "inventory":
            inventories[pk] = next(
                (tree(x) for x in e if local(x.tag) == "criteria"), {"unknown": "missing inventory criteria"}
            )

    def test(pk):
        t = tests.get(pk, {})
        if len(t.get("objects", [])) != 1:
            return {"unknown": "unsupported object set"}
        if t["objects"][0] not in objects:
            return {"unknown": "missing object reference"}
        obj = objects.get(t["objects"][0], {})
        ss = [states.get(s, [{"field": "unsupported"}]) for s in t["states"]]
        tag = t["tag"]
        if tag in {"dpkginfo_test", "rpminfo_test"}:
            n = obj.get("name", {})
            names = variables.get(n.get("var_ref"), []) if n.get("var_ref") else [n.get("text", "")]
            if (
                n.get("operation", "equals") != "equals"
                or set(obj) - {"name"}
                or not names
                or len(names) > 2048
                or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+_.-]{0,127}", n) for n in names)
            ):
                return {"unknown": "unsupported package object"}
            return {
                "package": names,
                "manager": "dpkg" if tag == "dpkginfo_test" else "rpm",
                "source": distro == "debian",
                "states": ss,
                "state_operator": t["attrs"].get("state_operator", "AND"),
                "check": t["attrs"].get("check", "all"),
                "existence": t["attrs"].get("check_existence", "at_least_one_exists"),
            }
        if tag == "variable_test":
            from . import distro_kernel

            variable = local_variables.get(obj.get("var_ref", {}).get("text"))
            expr = distro_kernel.expression(variable, objects) if variable is not None else None
            if (
                expr
                and object_types.get(expr["object"]) == "uname_object"
                and set(obj) == {"var_ref"}
                and set(obj["var_ref"]) == {"text"}
                and t["attrs"].get("check", "all") in {"all", "at least one"}
                and t["attrs"].get("check_existence", "all_exist") in {"all_exist", "at_least_one_exists"}
                and t["attrs"].get("state_operator", "AND") == "AND"
                and all(ss)
            ):
                return {"kernel_states": ss}
        guards_supported = t["attrs"].get("check", "all") in {"all", "at least one"} and t["attrs"].get(
            "check_existence", "at_least_one_exists"
        ) in {"at_least_one_exists", "any_exist"}
        if (
            tag == "family_test"
            and not obj
            and guards_supported
            and ss
            and all(ss)
            and all(
                s.get("field") == "family"
                and s.get("text") == "unix"
                and s.get("operation", "equals") == "equals"
                for group in ss
                for s in group
            )
        ):
            return {"constant": True}
        # Interpret only recognized OS-file/subexpression guards, not arbitrary text/regex.
        filepath = obj.get("filepath", {}).get("text") or obj.get("path", {}).get("text", "") + "/" + obj.get(
            "filename", {}
        ).get("text", "")
        if tag == "textfilecontent54_test" and filepath in {"/etc/lsb-release", "/etc/debian_version"}:
            expected_pattern = {
                "/etc/lsb-release": r"^[\s\S]*DISTRIB_CODENAME=([a-z]+)$",
                "/etc/debian_version": r"(\d+)\.\d",
            }[filepath]
            if (
                obj.get("pattern", {}).get("text") != expected_pattern
                or obj.get("pattern", {}).get("operation") != "pattern match"
                or obj.get("instance", {}).get("text") != "1"
                or any(
                    v.get("var_ref") or (n != "pattern" and v.get("operation", "equals") != "equals")
                    for n, v in obj.items()
                )
                or set(obj) - {"filepath", "path", "filename", "pattern", "instance"}
            ):
                return {"unknown": "unsupported OS inventory object"}
            wanted = {
                "ubuntu": {"20.04": "focal", "22.04": "jammy", "24.04": "noble", "26.04": "resolute"}.get(
                    release
                ),
                "debian": release,
            }.get(distro)
            if (
                guards_supported
                and ss
                and all(ss)
                and all(
                    s.get("field") == "subexpression"
                    and s.get("operation", "equals") == "equals"
                    and s.get("text") == wanted
                    for group in ss
                    for s in group
                )
            ):
                return {"constant": True}
        if tag == "uname_test" and guards_supported and not ss:
            return {"constant": True}  # OVAL's architecture-independent uname object
        if tag == "uname_test" and guards_supported and t["attrs"].get("state_operator", "AND") == "AND":
            return {"host_states": ss}
        # RHEL release/signature/module-stream verification requires facts not reported by old clients.
        return {"unknown": "unsupported " + tag}

    def expand(node, depth=0, seen=()):
        if depth > 32:
            return {"unknown": "criteria depth"}
        if "test" in node:
            result = test(node["test"])
        elif "extend" in node:
            pk = node["extend"]
            result = (
                expand(inventories[pk], depth + 1, (*seen, pk))
                if pk in inventories and pk not in seen
                else {"unknown": "unsupported extension"}
            )
        elif "children" in node:
            result = {
                "operator": node["operator"],
                "children": [expand(x, depth + 1, seen) for x in node["children"]],
            }
        else:
            result = node
        if "package" in result and node.get("comment"):
            result = {**result, "vendor_comment": node["comment"][:600]}
        if node.get("negate"):
            result = {"operator": "NOT", "children": [result]}
        return result

    for tag, e in entities(path, deadline):
        if tag != "definition" or e.get("class") not in {"vulnerability", "patch"}:
            continue
        meta = next((x for x in e if local(x.tag) == "metadata"), None)
        if meta is None:
            continue
        cves = sorted(
            {
                x.get("ref_id", "")
                for x in meta.iter()
                if local(x.tag) == "reference" and CVE.fullmatch(x.get("ref_id", ""))
            }
        )
        if any(len(cve) > 120 for cve in cves):
            raise ConnectorError("Vendor CVE identity limit exceeded")
        if not cves:
            continue
        stats["vendor_definitions"] += 1
        if len(cves) > 4096:
            raise ConnectorError("Too many CVEs in one definition")
        title = next(((x.text or "").strip() for x in meta if local(x.tag) == "title"), "")[:300]
        description = next(((x.text or "").strip() for x in meta if local(x.tag) == "description"), "")[:5000]
        severity = next(
            ((x.text or "").strip().lower() for x in meta.iter() if local(x.tag) == "severity"), "unknown"
        )
        severity = {"moderate": "medium", "important": "high"}.get(severity, severity)
        scores = {}
        for item in meta.iter():
            cve_id = (item.text or "").strip()
            vector = item.get("cvss_vector", "")
            if local(item.tag) != "cve" or cve_id not in cves:
                continue
            version = next((v for v in ("4.0", "3.1", "3.0") if vector.startswith("CVSS:" + v + "/")), None)
            try:
                score = float(item.get("cvss_score", ""))
            except ValueError:
                continue
            if version and math.isfinite(score) and 0 <= score <= 10:
                scores[cve_id] = {"version": version, "baseScore": score}
        criteria = expand(
            next((tree(x) for x in e if local(x.tag) == "criteria"), {"unknown": "no criteria"})
        )
        packages = set()

        def collect(n):
            if "package" in n:
                packages.update((n["manager"], name) for name in n["package"])
            for child in n.get("children", []):
                collect(child)

        collect(criteria)

        def kernel_rule(n):
            return (
                "kernel_states" in n
                or any(s.get("field") == "os_release" for g in n.get("host_states", []) for s in g)
                or any(kernel_rule(c) for c in n.get("children", []))
            )

        if kernel_rule(criteria):
            packages.add(("kernel", "runtime"))
            stats["kernel_definitions"] = stats.get("kernel_definitions", 0) + 1
        if not packages:
            stats["unindexed_definitions"] += 1
            continue
        stats["definitions"] += 1
        yield {
            "id": e.get("id"),
            "metadata": {
                "title": title,
                "description": description,
                "severity": severity,
                "cves": cves,
                "cvss": scores,
            },
            "criteria": criteria,
            "packages": sorted(packages),
        }


def tree(e, depth=0):
    if depth > 32:
        return {"unknown": "criteria depth"}
    tag = local(e.tag)
    if tag == "criteria":
        n = {"operator": e.get("operator", "AND"), "children": [tree(x, depth + 1) for x in e]}
    elif tag == "criterion":
        n = {"test": e.get("test_ref")}
    elif tag == "extend_definition":
        n = {"extend": e.get("definition_ref")}
    else:
        n = {"unknown": "unsupported criteria"}
    if tag == "criterion" and e.get("comment"):
        n["comment"] = e.get("comment")[:600]
    if e.get("negate", "false") not in {"false", "0", "true", "1"}:
        return {"unknown": "invalid negation"}
    if e.get("negate") in {"true", "1"}:
        n["negate"] = True
    return n


@lru_cache(maxsize=20000)
def compare(manager, a, b):
    if not a or not b or len(a) > 120 or len(b) > 120:
        raise ValueError("Invalid version")
    return compare_versions(a, b) if manager == "dpkg" else compare_rpm_versions(a, b)


def condition(value, rule, manager):
    if rule.get("var_ref") or rule.get("field") not in {"evr", "arch", "machine_class"}:
        return None
    op = rule.get("operation", "equals")
    wanted = rule.get("text", "")
    if rule["field"] == "evr":
        if manager == "dpkg" and (
            not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+:~_-]*", value)
        ):
            return None
        try:
            c = compare(manager, value, wanted)
        except (ValueError, TypeError, AssertionError):
            return None
        return {
            "less than": c < 0,
            "less than or equal": c <= 0,
            "equals": c == 0,
            "not equal": c != 0,
            "greater than": c > 0,
            "greater than or equal": c >= 0,
        }.get(op)
    if not isinstance(value, str) or not value or value == "unknown":
        return None
    if op == "equals":
        return value == wanted
    if op == "not equal":
        return value != wanted
    # Only fully anchored literal architecture alternatives have exact semantics
    # here. Unsupported patterns must not turn into a false/unaffected result.
    if op == "pattern match" and len(wanted) <= 256 and wanted.startswith("^") and wanted.endswith("$"):
        literal = wanted[1:-1]
        if literal.startswith("(?:") and literal.endswith(")"):
            literal = literal[3:-1]
        elif literal.startswith("(") and literal.endswith(")"):
            literal = literal[1:-1]
        elif "|" in literal:
            return None
        tokens = literal.split("|")
        if all(re.fullmatch(r"[A-Za-z0-9_-]+", token) for token in tokens):
            return value in tokens

    return None


def package_condition(fact, state, manager):
    field_name = state.get("field")
    if field_name not in {"evr", "arch"}:
        return None
    return condition(fact["version"] if field_name == "evr" else fact["architecture"], state, manager)


def combine(op, values):
    if op == "AND":
        return False if False in values else None if None in values else bool(values)
    if op == "OR":
        return True if True in values else None if None in values else False
    if op == "NOT" and len(values) == 1:
        return None if values[0] is None else not values[0]
    return None


def evaluate(node, facts, complete, os):
    """Return three-valued definition result and potentially contributing component IDs."""
    if "unknown" in node:
        return None, set()
    if "constant" in node:
        return node["constant"], set()
    if "children" in node:
        parts = [evaluate(n, facts, complete, os) for n in node["children"]]
        result = combine(node["operator"], [p[0] for p in parts])
        ids = set().union(*(ids for v, ids in parts if v is not False)) if result is not False else set()
        # Negated vulnerable package predicates do not identify a vulnerable installation.
        if node["operator"] == "NOT":
            ids = set()
        return result, ids
    if "kernel_states" in node or any(
        s.get("field") == "os_release" for g in node.get("host_states", []) for s in g
    ):
        from .distro_kernel import evaluate as evaluate_kernel

        return evaluate_kernel(node, os), set()
    if "host_states" in node:
        values = []
        for group in node["host_states"]:
            values.append(
                combine(
                    "AND",
                    [
                        condition(os.get("architecture", ""), s, "rpm")
                        if s.get("field") == "machine_class"
                        else None
                        for s in group
                    ],
                )
            )
        return combine("AND", values), set()
    if "package" not in node:
        return None, set()
    matches = []
    for name in node["package"]:
        matches.extend(facts.get((node["manager"], bool(node["source"]), name), []))
    exists = node["existence"]
    if not matches:
        coverage = (
            complete.get("source" if node["source"] else "binary", False)
            if isinstance(complete, dict)
            else complete
        )
        return (True if exists == "none_exist" else False, set()) if coverage else (None, set())
    if exists == "none_exist":
        return False, set()
    if exists not in {"at_least_one_exists", "any_exist"}:
        return None, set()
    results = []
    ids = set()
    for f in matches:
        groups = []
        for group in node["states"]:
            groups.append(
                combine(
                    "AND",
                    [package_condition(f, s, node["manager"]) for s in group],
                )
            )
        result = combine(node["state_operator"], groups) if groups else True
        results.append(result)
        # Vendor unresolved-CVE definitions may use package existence without a fixed version.
        if result is not False:
            ids.add(f["id"])
    op = {"at least one": "OR", "all": "AND", "only one": "unsupported", "none satisfy": "unsupported"}.get(
        node["check"], "unsupported"
    )
    result = combine(op, results)
    return result, ids if result is not False else set()


def version_proof(leaf, fact):
    """A true package-presence/architecture test is not an affected-version proof."""
    groups = []
    for group in leaf.get("states", []):
        values = [package_condition(fact, state, leaf["manager"]) for state in group]
        groups.append(combine("AND", values) is True and any(s.get("field") == "evr" for s in group))
    return any(groups)


def evaluate_matches(node, facts, complete, os, version_required=True):
    """Keep OVAL truth separate from each positively named component's version proof.

    An OR witness for package A cannot prove package B vulnerable. Existence-only
    matches stay unresolved even when OVAL's Boolean definition evaluates true.
    """
    if "children" in node:
        parts = [evaluate_matches(child, facts, complete, os, version_required) for child in node["children"]]
        truth = combine(node["operator"], [p[0] for p in parts])
        if node["operator"] == "NOT":
            return truth, {}
        ids = set().union(*(set(p[1]) for p in parts))
        outcomes = {}
        for cid in ids:
            values = [p[1][cid] for p in parts if cid in p[1]]
            if node["operator"] == "AND":
                outcomes[cid] = (
                    False
                    if truth is False or all(value is False for value in values)
                    else True
                    if truth is True and True in values
                    else None
                )
            elif node["operator"] == "OR":
                # Use only branches naming this component, including their guards.
                unknown_branch = any(value is None and not matches for value, matches in parts)
                outcomes[cid] = (
                    True if True in values else None if None in values or unknown_branch else False
                )
            else:
                outcomes[cid] = None
        return truth, outcomes
    truth, _ = evaluate(node, facts, complete, os)
    if "kernel_states" in node:
        versioned = any(
            s.get("field") == "value" and s.get("datatype") == "debian_evr_string"
            for g in node["kernel_states"]
            for s in g
        )
        return truth, {
            "__runtime_kernel__": False
            if truth is False
            else True
            if truth is True and (not version_required or versioned)
            else None
        }
    if "package" not in node:
        return truth, {}
    outcomes = {}
    for name in node["package"]:
        key = (node["manager"], bool(node["source"]), name)
        for fact in facts.get(key, []):
            own_truth, _ = evaluate(node, {key: [fact]}, complete, os)
            outcomes[fact["id"]] = (
                False
                if truth is False or own_truth is False
                else True
                if truth is True and own_truth is True and (not version_required or version_proof(node, fact))
                else None
            )
    return truth, outcomes
