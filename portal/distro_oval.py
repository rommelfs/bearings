"""Bounded OVAL subset. Unknown conditions stay unknown, never guessed true."""

import re
import time
from functools import lru_cache
from defusedxml.ElementTree import iterparse
from univers.debian import compare_versions
from univers.rpm import compare_rpm_versions
from .connectors.http import ConnectorError

CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}")
COMPILER_VERSION = 2


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
            objects[pk] = {local(x.tag): field(x) for x in e}
        elif tag.endswith("_state"):
            states[pk] = (
                [dict(field(x), field=local(x.tag)) for x in e]
                if e.get("operator", "AND") == "AND"
                else [{"field": "unsupported state operator"}]
            )
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
        if not packages:
            stats["unindexed_definitions"] += 1
            continue
        stats["definitions"] += 1
        yield {
            "id": e.get("id"),
            "metadata": {"title": title, "description": description, "severity": severity, "cves": cves},
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
    if op == "equals":
        return value == wanted
    if op == "not equal":
        return value != wanted
    # Finite architecture alternatives only; never execute vendor regex/commands.
    if op == "pattern match" and re.fullmatch(r"[A-Za-z0-9_.|^$-]{1,256}", wanted):
        return value in wanted.strip("^$").split("|")
    return None


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
                    [
                        condition(
                            f["version"]
                            if s["field"] == "evr"
                            else f["architecture"]
                            if s["field"] == "arch"
                            else "",
                            s,
                            node["manager"],
                        )
                        for s in group
                    ],
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
