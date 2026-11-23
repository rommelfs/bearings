"""Separate data availability, evaluation freshness and per-package CVE decisions."""

from collections import defaultdict
from .intelligence import digest

SUMMARY_VERSION = 1

ACTIONS = {
    "vendor_needs_triage": (
        "Awaiting Ubuntu assessment",
        "Monitor the vendor assessment. This does not create one manual task per association.",
    ),
    "vendor_unfixed": (
        "Ubuntu lists work needed",
        "No released fix is established by this status. Assess exposure and mitigations, and track the vendor release.",
    ),
    "vendor_fix_pending": (
        "Ubuntu fix in preparation",
        "Check the vendor's release and update availability; pending work is not proof that this host can already install a fix.",
    ),
    "vendor_deferred": (
        "Ubuntu fix deferred",
        "Inspect the vendor's reason, support options and possible mitigations before recording a review decision.",
    ),
    "vendor_ignored": (
        "Ubuntu marks this issue ignored",
        "Read the vendor rationale and verify the deployment before assessing applicability or accepting risk. Ignored does not mean fixed.",
    ),
    "ubuntu_status_pending": (
        "Ubuntu data was pending",
        "Current lookup progress is shown separately; reassess after fresh data is evaluated.",
    ),
    "ubuntu_status_stale": (
        "Ubuntu data was stale",
        "Refresh vendor evidence and reevaluate; retained data is not a current decision.",
    ),
    "ubuntu_status_unavailable": (
        "Ubuntu lookup failed at evaluation time",
        "Compare the evaluation time with current lookup progress. Fresh data requires reevaluation.",
    ),
    "source_metadata_missing": (
        "Source package metadata missing",
        "Obtain the source package name and native version from a fresh client report.",
    ),
    "invalid_source_version": (
        "Source version unusable",
        "Inspect the reported source version; do not substitute the binary or upstream version.",
    ),
    "vendor_source_not_listed": (
        "Exact release/source not listed",
        "Inspect the official source and release identity before deciding applicability.",
    ),
}


def metrics(checks):
    outcomes = defaultdict(lambda: {"cves": set(), "packages": set(), "records": 0})
    reasons = defaultdict(lambda: {"cves": set(), "packages": set(), "records": 0})
    for cid, results in checks.results.items():
        for cve, row in results.items():
            item = outcomes[row["result"]]
            item["cves"].add(cve)
            item["packages"].add(cid)
            item["records"] += 1
            if row["result"] == "unknown":
                code = row["package_check"].get("uncertainty_reason") or "unsupported_condition"
                group = reasons[code]
                group["cves"].add(cve)
                group["packages"].add(cid)
                group["records"] += 1

    def counts(value):
        return {"cves": len(value["cves"]), "packages": len(value["packages"]), "records": value["records"]}

    return {
        "outcomes": {key: counts(value) for key, value in outcomes.items()},
        "reasons": [{"code": key, **counts(value)} for key, value in sorted(reasons.items())],
    }


def decorate_metrics(summary):
    result = dict(summary.get("decision_counts") or {})
    result["reasons"] = [
        {
            **row,
            "heading": ACTIONS.get(
                row["code"],
                (
                    "Additional vendor conditions unresolved",
                    "Inspect the supported facts and original evidence; do not infer unaffectedness.",
                ),
            )[0],
            "action": ACTIONS.get(
                row["code"],
                ("", "Inspect the supported facts and original evidence; do not infer unaffectedness."),
            )[1],
        }
        for row in result.get("reasons", [])
    ]
    return result


def state(device, lookup, feed=None):
    from django.conf import settings
    from . import agents, distro_cves, distro_sources

    summary = device.distro_summary
    changed = bool(lookup and lookup.get("changed"))
    complete = bool(lookup and lookup.get("total") and lookup["fresh"] == lookup["total"])
    if device.stale or not agents.current(device):
        key, message = "stale", "Awaiting a current inventory report; retained evaluation is historical."
    elif not settings.DISTRO_CVE_ENABLED:
        key, message = "disabled", "Automatic package evaluation is disabled by the operator."
    elif device.last_sequence != device.applied_sequence:
        key, message = (
            "report_pending",
            "A newer client report awaits processing; retained evaluation is historical.",
        )
    elif not distro_sources.key_for(device.os):
        key, message = (
            "unsupported",
            "No supported vendor definitions exist for this exact reported distribution/release.",
        )
    elif not feed or distro_cves.feed_state(feed) != "ready":
        key, message = "vendor_pending", "Awaiting current distribution vendor definitions."
    elif device.distro_requested or changed or not device.distro_checked_at:
        key = "evaluation_requested" if device.distro_requested else "evaluation_pending"
        message = ("Ubuntu data current; " if complete else "New inputs available; ") + (
            "reevaluation requested. No newer completed result yet."
            if device.distro_requested
            else "awaiting reevaluation. No newer completed result yet."
        )
    elif summary.get("state") == "error":
        key, message = "error", "The evaluation failed; no current package verdict is available."
    elif lookup and (lookup.get("pending") or lookup.get("failed")):
        key, message = (
            "lookup_pending",
            "Some Ubuntu lookups await usable data; the package assessment remains limited. Fresh data will trigger reevaluation.",
        )
    elif summary.get("generation") != str(feed.generation):
        key, message = "evaluation_pending", "Distribution definitions changed; awaiting reevaluation."
    else:
        key, message = (
            "evaluated",
            "The latest evaluation uses the current recorded inputs. Vendor clarification or host-kernel scope may still be unresolved.",
        )
    historical = key not in {"evaluated", "lookup_pending"}
    revision = digest(
        {
            "summary": summary,
            "checked": str(device.distro_checked_at),
            "phase": key,
            "os": device.os,
            "sequence": device.applied_sequence,
            "generation": str(feed.generation) if feed else "",
            "virtualization": device.asset.virtualization_type,
        }
    )
    return {
        "state": key,
        "message": message,
        "historical": historical,
        "revision": revision,
        "checked_at": device.distro_checked_at.isoformat() if device.distro_checked_at else None,
    }
