"""Explain recorded blockers and remediation routes, without inferring CVE affectedness."""

from datetime import timedelta
import re
from urllib.parse import urlencode
from django.urls import reverse
from django.utils import timezone
from .overview_monitoring import attention_devices
from .distro_errors import diagnostic
from .distro_coverage_notes import explain


def decorate(states):
    examples = attention_devices([s["org"].pk for s in states]) if states else {}
    from .ubuntu_status import progress

    lookup_progress = progress([d.pk for devices in examples.values() for d in devices]) if examples else {}
    now = timezone.now()
    for state in states:
        org = state["org"]
        steps = []
        notes = []
        inventory = reverse("organization", args=[org.slug])
        checks = reverse("discovery") + "?" + urlencode({"organization": org.slug})
        clients = reverse("agent-center", args=[org.slug])
        reviews = reverse("intelligence", args=[org.slug])
        issues = reverse("issues") + "?" + urlencode({"organization": org.slug})

        def add(title, reason, action, url, owner, icon="issues", priority=3, **extra):
            steps.append(
                dict(
                    title=title,
                    reason=reason,
                    action=action,
                    url=url,
                    owner=owner,
                    icon=icon,
                    priority=priority,
                    **extra,
                )
            )

        if state["overdue"]:
            add(
                "Address overdue actions",
                f"{state['overdue']} recorded actions have passed their due date.",
                "Open overdue actions",
                issues + "&attention=overdue",
                "Action owner / company administrator",
                priority=0,
            )
        if state["expired_acceptance"]:
            add(
                "Revisit expired risk acceptance",
                f"{state['expired_acceptance']} recorded risk acceptances have expired.",
                "Review risk decisions",
                reverse("risk-register") + "?" + urlencode({"organization": org.slug}),
                "Risk owner",
                "risks",
                priority=0,
            )
        devices = examples.get(org.pk, [])
        if (state["package_products"] or devices) and not state["package_matching_enabled"]:
            add(
                "Review disabled distribution package checks",
                "Automatic matching is disabled by platform configuration; changing individual product mappings will not enable it.",
                "Inspect package coverage",
                checks,
                "Platform operator",
                "settings",
                priority=1,
            )
            devices = []
        elif state["package_products"] and not state["package_clients"]:
            add(
                "Connect current package inventory",
                "Packages are recorded, but no enabled client has linked package observations for these active hosts.",
                "Open Linux clients",
                clients,
                "Company / server administrator",
                "clients",
                priority=1,
            )
        for device in devices:
            summary = device.distro_summary if isinstance(device.distro_summary, dict) else {}
            status = summary.get("state")
            status = status if isinstance(status, str) else ""
            if device.expires_at <= now:
                title, reason, owner = (
                    "Renew client credentials",
                    "Device credential has expired. Re-enroll this host before expecting new inventory or package results.",
                    "Company administrator",
                )
            elif not device.last_observed_at or device.last_observed_at < now - timedelta(hours=12):
                if device.last_received_at and device.last_received_at >= now - timedelta(hours=12):
                    title, reason, owner = (
                        "Check receipt processing and report timestamps",
                        "A recent report was received, but its recorded observation is missing or older than 12 hours. Inspect processing status and the host clock/report timestamps before restarting the client.",
                        "Platform operator / server administrator",
                    )
                else:
                    title, reason, owner = (
                        "Restore server reporting",
                        "No applied observation is recorded, or the last observation is older than 12 hours. Check the client's service and outbound HTTPS; retained versions are not a fresh inventory.",
                        "Server administrator",
                    )
            elif status == "error":
                title, owner = "Repair automatic package evaluation", "Platform operator"
                match = re.fullmatch(
                    r"Evaluation deferred \(([A-Za-z][A-Za-z0-9_]{0,60})\); retained evidence needs review\.",
                    str(summary.get("message", "")),
                )
                kind = match.group(1) if match else ""
                known = {
                    "ValueError",
                    "TypeError",
                    "KeyError",
                    "AttributeError",
                    "ConnectorError",
                    "InvalidVersion",
                }
                reason = (
                    f"Evaluation stopped ({kind}); current affectedness is unavailable. Inspect evaluator diagnostics and the vendor/input conditions before retrying."
                    if kind in known
                    else "Evaluation failed; no classified cause is recorded here. The platform operator must inspect evaluator diagnostics before retrying. Previous findings remain retained."
                )
                detail = diagnostic(summary.get("error_code"))
                if detail:
                    reason = (
                        detail["message"]
                        + " "
                        + detail["next_action"]
                        + " The failed attempt published no partial evaluation; current affectedness is unavailable."
                    )
            elif (
                isinstance(summary.get("kernel"), dict)
                and type(summary["kernel"].get("counts", {}).get("matched")) is int
                and summary["kernel"]["counts"]["matched"] > 0
            ):
                title, reason, owner = (
                    "Review running-kernel version matches",
                    f"{summary['kernel']['counts']['matched']} vendor kernel definitions match the reported running kernel. Inspect the retained kernel evidence and host remediation; guest package upgrades do not prove a running-kernel fix.",
                    "Server administrator / platform operator",
                )
            elif status == "unsupported":
                title, reason, owner = (
                    "Resolve unsupported distribution coverage",
                    "The reported distribution/release has no supported automatic package check. Verify OS metadata and supported vendor coverage; do not treat packages as checked.",
                    "Platform operator / server administrator",
                )
            elif status in {"pending", "stale"}:
                title, reason, owner = (
                    "Restore vendor data coverage",
                    "Vendor data is pending or stale; no current complete package result is available. Inspect the feed refresh and its worker status.",
                    "Platform operator",
                )
            elif status == "partial":
                limit = explain(summary)
                if not limit["actionable"]:
                    notes.append(
                        {
                            **limit,
                            "host": device.asset.name,
                            "lookup_progress": lookup_progress.get(device.pk),
                            "url": clients + "?" + urlencode({"device": str(device.pk)}) + "#automatic-cves",
                            "checked_at": device.distro_checked_at,
                            "feed": summary.get("feed") if isinstance(summary.get("feed"), str) else "",
                        }
                    )
                    continue
                title, reason, owner = (
                    limit["title"],
                    limit["reason"],
                    "Server administrator / platform operator",
                )
            else:
                title, reason, owner = (
                    "Obtain a current package evaluation",
                    "No complete evaluation is recorded. Inspect incoming reports, the evaluation queue and vendor coverage.",
                    "Platform operator",
                )
            add(
                title,
                reason,
                "Open this server's check",
                clients + "?" + urlencode({"device": str(device.pk)}) + "#automatic-cves",
                owner,
                "clients",
                priority=1,
                host=device.asset.name,
                observed_at=device.last_observed_at,
                received_at=device.last_received_at,
                attempted_at=device.distro_checked_at,
            )
        if (
            state["package_products"]
            and state["package_queued"]
            and not devices
            and state["package_matching_enabled"]
        ):
            add(
                "Monitor queued package checks",
                "A check is queued; this does not prove a worker has completed it. No per-package manufacturer mapping is required. If it does not progress, ask the platform operator to inspect processing.",
                "Inspect processing and coverage",
                checks,
                "Automatic worker / platform operator",
                "discovery",
            )
        if not state["response_contacts"]:
            add(
                "Confirm a response contact",
                "No non-DPO contact currently meets all requirements: notifications opted in, email reachable, role reviewed and review not expired.",
                "Review response contacts",
                inventory + "#contacts",
                "Company administrator",
                "members",
                priority=2,
            )
        if state["source_stale"]:
            source = getattr(org, "inventory_source", None)
            owner = "Platform operator"
            if source is None:
                reason = "No authoritative inventory source is configured for this company."
            elif source.mode == "manual":
                policy = getattr(org, "inventory_review_policy", None)
                owner = "Company administrator"
                reason = (
                    "Company-reported inventory has no recorded owner review. Complete the inventory data review."
                    if not policy or not policy.last_reviewed_at
                    else "The periodic owner review of company-reported inventory is overdue. Review and confirm the retained inventory."
                )
            elif not source.instance_id:
                reason = "The inventory source has no configured NetBox instance. An operator must restore its approved connector binding."
            elif not source.instance.enabled:
                reason = (
                    "The configured NetBox instance is disabled. An operator must review its connector state."
                )
            elif not source.last_import_success:
                reason = "No successful complete inventory import is recorded. Inspect connector/import processing; existing records are not proof of a completed synchronization."
            else:
                reason = "The last successful inventory import is outside its freshness window. Inspect connector/import processing; retained data must not be treated as a fresh import."
            add(
                "Restore current inventory source",
                reason,
                "Inspect inventory source",
                inventory,
                owner,
                "inventory",
                priority=2,
            )
        if (
            not state["assets"]
            or state["without_software"]
            or state["unknown_versions"]
            or state["missing_assets"]
        ):
            add(
                "Complete inventory evidence",
                f"{state['assets']} active assets; {state['without_software']} without software; {state['unknown_versions']} unknown versions; {state['missing_assets']} missing objects retained for review. Correct the missing evidence before relying on CVE coverage.",
                "Inspect inventory and versions",
                inventory + "#inventory",
                "Server / inventory owner",
                "inventory",
                priority=2,
            )
        if state["unmapped"] or state["paused"] or state["stale_watches"] or state["watch_errors"]:
            add(
                "Review application monitoring",
                f"{state['unmapped']} non-package products without mapping; {state['paused']} paused watches; {state['stale_watches']} without a fresh complete result; {state['watch_errors']} source errors. Review paused watches deliberately; standard distribution packages need no manual manufacturer mapping.",
                "Inspect application watches",
                checks,
                "Company administrator / platform operator",
                "discovery",
            )
        if state["affected"]:
            add(
                "Review remediation for confirmed cases",
                f"{state['affected']} open reviews have a saved analyst-affected assessment. Verify current package proof, any installed fix and the next remediation action.",
                "Open confirmed affected reviews",
                reviews + "?attention=affected",
                "Server / review owner",
                "review",
                priority=0,
            )
        elif state["reviews"]:
            add(
                "Triage version evidence before scheduling updates",
                "Open review items and source severity are not confirmed vulnerable installations. Inspect installed versions and current vendor proof; reconcile retained reviews when the fix is already installed.",
                "Inspect Critical-source reviews" if state["critical"] else "Inspect open reviews",
                reviews + ("?attention=critical" if state["critical"] else "?attention=reviews"),
                "Review owner",
                "review",
                priority=4,
            )
        steps.sort(key=lambda step: step.get("priority", 3))
        grouped_notes = {}
        for note in notes:
            key = (note["feed"], note["reason"])
            grouped = grouped_notes.setdefault(key, {**note, "devices": []})
            grouped["devices"].append(
                {
                    "host": note["host"],
                    "url": note["url"],
                    "checked_at": note["checked_at"],
                    "lookup_progress": note.get("lookup_progress"),
                }
            )
        state["coverage_notes"] = list(grouped_notes.values())
        state["next_steps"] = steps[:5]
        state["other_next_steps"] = steps[5:]
        state["next_step_count"] = len(steps)
        state["device_examples_shown"] = len(devices)
