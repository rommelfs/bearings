"""Bounded, source-owned Windows Update cache observations; no patch verdicts."""

from copy import deepcopy
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

MAX_UPDATES = 250
SOURCE = "windows-update-agent-cache"
STATES = {"ok", "partial", "error", "unavailable", "timeout"}


def validate(value, observed_at):
    from .agent_protocol import exact, identifier, text

    exact(value, ("source", "cache_last_search_at", "reboot", "installed", "pending"))
    if (
        value["source"] != SOURCE
        or not isinstance(value["reboot"], str)
        or value["reboot"] not in {"present", "not_observed", "unknown"}
    ):
        raise ValueError("Unsupported Windows Update evidence")
    cache_date = value["cache_last_search_at"]
    if not isinstance(cache_date, str) or len(cache_date) > 40:
        raise ValueError("Invalid Windows Update cache date")
    if cache_date:
        parsed = parse_datetime(cache_date)
        if not parsed or timezone.is_naive(parsed) or parsed > observed_at + timedelta(minutes=5):
            raise ValueError("Invalid Windows Update cache time")
    for name in ("installed", "pending"):
        group = value[name]
        exact(group, ("status", "total", "truncated", "updates"))
        state, count, rows = group["status"], group["total"], group["updates"]
        if (
            not isinstance(state, str)
            or state not in STATES
            or type(group["truncated"]) is not bool
            or not isinstance(rows, list)
            or len(rows) > MAX_UPDATES
        ):
            raise ValueError("Invalid Windows Update coverage")
        if state in {"ok", "partial"}:
            if (
                type(count) is not int
                or not len(rows) <= count <= 100000
                or group["truncated"] != (count > len(rows))
                or state == "ok"
                and group["truncated"]
            ):
                raise ValueError("Inconsistent Windows Update counts")
        elif count is not None or rows or group["truncated"]:
            raise ValueError("Failed Windows Update queries cannot report an empty success")
        seen = set()
        for row in rows:
            exact(row, ("id", "revision", "title", "kbs", "hidden"))
            identifier(row["id"])
            if type(row["revision"]) is not int or not 1 <= row["revision"] <= 2**31 - 1:
                raise ValueError("Invalid Windows Update revision")
            key = (row["id"], row["revision"])
            if key in seen:
                raise ValueError("Duplicate Windows Update identity")
            seen.add(key)
            if row["title"] != "":
                text(row["title"], 240)
            if type(row["hidden"]) is not bool or not isinstance(row["kbs"], list) or len(row["kbs"]) > 16:
                raise ValueError("Invalid Windows Update metadata")
            for kb in row["kbs"]:
                text(kb, 11, r"KB[0-9]{4,9}")
            if len(set(row["kbs"])) != len(row["kbs"]):
                raise ValueError("Duplicate KB identifier")


def merge_os(previous, current, observed_at):
    """Caller holds the existing source/device locks. Client cannot supply retained receipts."""
    current = deepcopy(current)
    old = previous.get("windows_update", {})
    if "windows_update" not in current:
        if old:
            current["windows_update"] = {**deepcopy(old), "included": False}
        return current
    raw = current["windows_update"]
    retained = deepcopy(old.get("last_success", {}))
    if raw["reboot"] != "unknown":
        retained["reboot"] = {
            "observed_at": observed_at.isoformat(),
            "build": current["version"],
            "data": raw["reboot"],
        }
    for name in ("installed", "pending"):
        if raw[name]["status"] == "ok":
            retained[name] = {
                "observed_at": observed_at.isoformat(),
                "build": current["version"],
                "data": deepcopy(raw[name]),
            }
    current["windows_update"] = {
        **raw,
        "observed_at": observed_at.isoformat(),
        "build": current["version"],
        "included": True,
        "last_success": retained,
    }
    return current


def presentation(device):
    """Use only a previously authorized device. Never refresh old evidence by rendering."""
    from .agents import current

    receipt = deepcopy(device.os.get("windows_update", {}))
    if not receipt:
        return {}
    observed = parse_datetime(receipt["observed_at"])
    receipt["historical"] = (
        not current(device)
        or not receipt.get("included")
        or not device.enabled
        or device.stale
        or device.expires_at <= timezone.now()
        or not observed
        or observed < timezone.now() - timedelta(hours=12)
        or receipt.get("build") != device.os.get("version")
    )
    receipt["groups"] = [
        {"name": name, **receipt[name], "last_success": receipt.get("last_success", {}).get(name)}
        for name in ("pending", "installed")
    ]
    cache_at = parse_datetime(receipt.get("cache_last_search_at", ""))
    receipt["cache_outdated"] = not cache_at or cache_at < timezone.now() - timedelta(hours=24)
    receipt["backlog"] = backlog_summary(receipt)
    return receipt


def backlog_summary(receipt):
    pending = receipt["pending"]
    current = pending["status"] in {"ok", "partial"}
    retained = (
        receipt.get("last_success", {}).get("pending")
        if not current or pending["status"] == "partial" and not pending["total"]
        else None
    )
    evidence = retained["data"] if retained else pending
    count = evidence["total"]
    historical = bool(retained or receipt["historical"] or receipt["cache_outdated"])
    if count:
        label = f"{count} pending update" + ("s" if count != 1 else "")
        if historical:
            label += " last recorded"
        detail = (
            "Review the last known Windows Update cache entries."
            if historical
            else "Windows Update Agent reported these entries in its local cache."
        )
        if evidence["status"] == "partial":
            detail += " The result is partial."
        return {"label": label, "detail": detail, "attention": True}
    if current and not historical and pending["status"] == "ok":
        return {
            "label": "No pending entries in the Windows cache",
            "detail": "Coverage is limited to the update entries reported by Windows.",
            "attention": False,
        }
    return {
        "label": "Windows update backlog unknown",
        "detail": "A current, complete cache observation is unavailable.",
        "attention": False,
    }
