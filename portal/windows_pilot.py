"""Read-only Windows 11 pilot evidence; never a patch or CVE compliance verdict."""

import hashlib
import json
import re
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import agent_protocol, agents, windows_cves
from .access import audit_operator_access, organizations_for
from .intelligence import digest
from .models import AgentDevice

RULE = "windows11-pilot/v1"
MSRC_2024 = "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2024-Oct"
MSRC_2026 = "https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2026-Nov"
END_22H2 = "https://learn.microsoft.com/en-us/lifecycle/announcements/windows-11-22h2-end-of-updates-home-pro"
# Reviewed ProductTree IDs, not CPEs copied from a particular fixed build.
PRODUCTS = {
    ("22H2", "22621"): ({"arm64": "12085", "x86_64": "12086"}, MSRC_2024),
    ("24H2", "26100"): ({"arm64": "12389", "x86_64": "12390"}, MSRC_2026),
    ("25H2", "26200"): ({"arm64": "20437", "x86_64": "20438"}, MSRC_2026),
}


def identity(component, os, *, today=None):
    """Finite pilot product catalog, independent of inventory names and update order."""
    facts = component.windows
    result = {
        "rule": RULE,
        "observed_version": component.version,
        "role": facts.get("installation_type", ""),
        "edition": facts.get("edition", ""),
        "release": facts.get("release", ""),
        "architecture": os.get("architecture", ""),
        "product": None,
        "lifecycle": {"state": "not_established"},
        "gaps": [],
    }
    build = re.fullmatch(r"([0-9]{5})\.([0-9]{1,10})", component.version)
    entry = PRODUCTS.get((result["release"], build[1])) if build else None
    eligible = (
        facts.get("kind") == "os"
        and result["role"] == "Client"
        and result["edition"] in windows_cves.CLIENT_EDITIONS
        and result["edition"] not in {"EnterpriseS", "EnterpriseSN", "IoTEnterpriseS"}
        and os.get("id") == "windows"
        and os.get("version") == component.version
        and os.get("kernel") == component.version
        and entry is not None
        and result["architecture"] in entry[0]
    )
    if not eligible:
        result["gaps"].append(
            "Role, edition, release, complete build and native architecture do not establish a reviewed pilot product"
        )
        return result
    platform = windows_cves.PLATFORMS[result["architecture"]]
    result["product"] = {
        "id": entry[0][result["architecture"]],
        "name": f"Windows 11 Version {result['release']} for {platform}",
        "reference": entry[1],
        "reviewed_on": "2026-11-25",
    }
    if result["release"] == "22H2" and result["edition"] in {
        "Core",
        "CoreN",
        "Professional",
        "ProfessionalN",
    }:
        end = date(2024, 10, 8)
        result["lifecycle"] = {
            "state": "out_of_support"
            if (today or timezone.localdate()) > end
            else "within_reviewed_support_period",
            "last_servicing_date": end.isoformat(),
            "reference": END_22H2,
        }
    if result["lifecycle"]["state"] == "out_of_support":
        result["gaps"].append(
            "This edition/release is outside its reviewed support period; plan an authorized OS upgrade"
        )
    elif result["lifecycle"]["state"] == "not_established":
        result["gaps"].append("Edition-specific lifecycle has not been reviewed for this pilot product")
    return result


def inspect(user, org_slug, device_id):
    """One authorized applied observation, bounded export without names or credentials."""
    if not user.is_active:
        raise PermissionDenied
    org = organizations_for(user).get(slug=org_slug)
    audit_operator_access(user, org)
    device = AgentDevice.objects.select_related("asset", "source", "organization").get(
        pk=device_id, organization=org
    )
    # Reject corrupt bindings before reading report bytes or foreign identity fields.
    if (
        device.asset.organization_id != org.pk
        or device.source.organization_id != org.pk
        or device.asset.source_id != device.source_id
    ):
        raise PermissionDenied
    components = list(
        device.components.filter(manager="win-reg", windows__kind="os").select_related(
            "last_report", "installation__product"
        )[:2]
    )
    if len(components) != 1:
        raise ValueError("Exactly one Windows OS observation is required")
    component = components[0]
    report = component.last_report
    if (
        report.device_id != device.pk
        or report.public_key != device.public_key
        or (
            component.installation_id
            and (
                component.installation.asset_id != device.asset_id
                or component.installation.product.organization_id != org.pk
            )
        )
    ):
        raise PermissionDenied
    raw = bytes(report.body)
    if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != report.body_hash:
        raise ValueError("Retained report integrity check failed")
    data = json.loads(raw)
    agent_protocol.report_data(data)
    observed = [c for c in data["components"] if c["manager"] == "win-reg" and c["windows"]["kind"] == "os"]
    if (
        len(observed) != 1
        or observed[0]["key"] != component.key
        or observed[0]["windows"] != component.windows
        or observed[0]["version"] != component.version
        or (component.installation_id and component.installation.version != component.version)
        or data["report_id"] != str(report.pk)
        or data["sequence"] != report.sequence
        or report.observed_at != component.observed_at
        or parse_datetime(data["observed_at"]) != report.observed_at
    ):
        raise ValueError("Projection and retained report do not agree")
    result = identity(component, data["os"])
    result["observation"] = {
        "report": str(report.pk),
        "sequence": report.sequence,
        "observed_at": report.observed_at.isoformat(),
        "body_sha256": report.body_hash,
        "current": bool(
            agents.current(device)
            and not device.stale
            and not component.stale
            and not component.missing_since
            and not device.asset.missing_since
            and report.status == "applied"
            and report.sequence == device.applied_sequence == device.last_sequence
            and report.observed_at == device.last_observed_at
        ),
    }
    if not result["observation"]["current"]:
        result["gaps"].append(
            "Observation is retained, stale, revoked, expired or not the latest applied report"
        )
    if not component.installation_id or component.inventory_excluded:
        result["gaps"].append(
            "OS observation has no active installation binding or is excluded from projection"
        )
    mapping = windows_cves.resolve(component, data["os"])
    result["mapping_rule"] = mapping["rule"]
    result["servicing_channel"] = mapping.get("servicing_channel", "") or "unknown"
    result["update_line"] = mapping.get("update_line", "") or "unknown"
    result["gaps"].extend(mapping["gaps"])
    updates = data["os"].get("windows_update")
    result["windows_update"] = None
    if updates:
        # Only this exact report; never promote retained last-success rows.
        result["windows_update"] = {
            "cache_last_search_at": updates["cache_last_search_at"],
            "reboot": updates["reboot"],
            "groups": [
                {
                    "kind": key,
                    "status": updates[key]["status"],
                    "total": updates[key]["total"],
                    "truncated": updates[key]["truncated"],
                    "kbs": sorted({kb for row in updates[key]["updates"] for kb in row["kbs"]}),
                }
                for key in ("installed", "pending")
            ],
        }
        if any(updates[k]["status"] != "ok" for k in ("installed", "pending")):
            result["gaps"].append("Windows Update cache queries are incomplete or failed")
        cache_at = parse_datetime(updates["cache_last_search_at"])
        if not cache_at or cache_at < timezone.now() - timedelta(hours=24):
            result["gaps"].append("Windows Update cache search age is unknown or exceeds 24 hours")
        if updates["reboot"] != "not_observed":
            result["gaps"].append("Restart requirement is present or unknown")
    else:
        result["gaps"].append("This report contains no Windows Update cache evidence")
    result["gaps"].append(
        "KB presence and a product identity do not prove CVE remediation; per-advisory update-line evidence remains required"
    )
    result["gaps"] = list(dict.fromkeys(result["gaps"]))
    result["cve_compliance"] = "not_established"
    result["fingerprint"] = digest(result)
    return result
