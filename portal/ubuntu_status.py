"""Public CVE/release/source-package status; exact native comparison, never name guesses."""

import re
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q, F, Exists, OuterRef
from django.utils import timezone
from .agent_freshness import recent_device
from .connectors.http import ConnectorError, UpstreamHTTPError, approved_base, request_json
from .models import UbuntuCVEStatus, AgentDevice, UbuntuStatusUse
from .intelligence import digest
from . import distro_oval, distro_sources

TTL = timedelta(hours=12)
STATUSES = {"released", "not-affected", "needed", "needs-triage", "pending", "ignored", "deferred", "dne"}


def url(cve):
    if len(cve) > 120 or not distro_oval.CVE.fullmatch(cve):
        raise ConnectorError("Invalid public CVE identity")
    return "https://ubuntu.com/security/cves/" + cve + ".json"


def normalize(data, cve):
    if (
        not isinstance(data, dict)
        or data.get("id") != cve
        or not isinstance(data.get("packages"), list)
        or len(data["packages"]) > 1000
    ):
        raise ConnectorError("Ubuntu status schema/identity invalid")
    result = {}
    for package in data["packages"]:
        source = package.get("name", "")
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9+.-]{0,127}", source)
            or not isinstance(package.get("statuses"), list)
            or len(package["statuses"]) > 200
        ):
            raise ConnectorError("Ubuntu source/release status invalid")
        for row in package["statuses"]:
            release = row.get("release_codename")
            if release not in distro_sources.UBUNTU.values():
                continue
            status = str(row.get("status", "")).lower()
            value = {
                "status": status if status in STATUSES else "unsupported",
                "description": str(row.get("description", ""))[:600],
                "pocket": str(row.get("pocket") or "")[:60],
            }
            result.setdefault(release, {}).setdefault(source, []).append(value)
    return result


def fresh(row):
    return bool(row and row.last_success and row.last_success >= timezone.now() - TTL and row.content_hash)


def enqueue(cves):
    UbuntuCVEStatus.objects.bulk_create(
        [UbuntuCVEStatus(cve=c) for c in sorted(set(cves)) if len(c) <= 120 and distro_oval.CVE.fullmatch(c)],
        ignore_conflicts=True,
        batch_size=500,
    )


def refresh_due(limit=16):
    """Sixteen leased items, four concurrent requests, shared 45-second batch budget."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import httpx
    import time

    if not settings.DISTRO_CVE_ENABLED or not settings.UBUNTU_STATUS_FETCH_ENABLED:
        return
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            UbuntuCVEStatus.objects.filter(
                Q(last_success__isnull=True) | Q(last_success__lt=now - timedelta(hours=6)),
            )
            .filter(Q(last_attempt__isnull=True) | Q(last_attempt__lt=now - timedelta(minutes=15)))
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now))
            .select_for_update(skip_locked=True)
            .only("cve", "last_attempt", "lease_until")
            .order_by(F("last_attempt").asc(nulls_first=True), "cve")[: min(max(limit, 1), 16)]
        )
        for row in rows:
            row.previous_attempt = row.last_attempt
            row.last_attempt = now
            row.lease_until = now + timedelta(minutes=2)
        UbuntuCVEStatus.objects.bulk_update(rows, ["last_attempt", "lease_until"])

    batch_deadline = time.monotonic() + 45

    def fetch(row):
        remaining = batch_deadline - time.monotonic()
        if remaining < 1:
            return row, None, None  # Not attempted: restore its queue position, no false failure.
        try:
            target = url(row.cve)
            approved_base(target, proxy_dns=settings.CONNECTOR_PROXY_DNS)
            payload = normalize(
                request_json(
                    "GET",
                    target,
                    deadline=batch_deadline,
                    timeout=httpx.Timeout(min(40, remaining), connect=min(10, remaining)),
                ),
                row.cve,
            )
            return row, payload, ""
        except Exception as exc:
            known = {
                "Connector hostname is not explicitly approved by the operator",
                "Proxy DNS mode requires an approved HTTPS proxy",
                "Connector DNS resolution failed",
                "Private connector destinations require explicit operator approval",
                "Connector response time budget exceeded",
                "Upstream response exceeds 2 MB limit",
                "Expected an upstream JSON object",
                "Ubuntu status schema/identity invalid",
                "Ubuntu source/release status invalid",
            }
            category = getattr(exc, "reason_code", "")
            transport = {
                "timeout": "HTTPS timeout",
                "transport": "HTTPS transport failure",
                "invalid_json": "Invalid JSON response",
            }
            reason = (
                ("HTTP " + str(exc.status_code))
                if isinstance(exc, UpstreamHTTPError)
                else transport[category]
                if isinstance(exc, ConnectorError) and category in transport
                else str(exc)
                if isinstance(exc, ConnectorError) and str(exc) in known
                else type(exc).__name__
            )
            return (
                row,
                None,
                "Ubuntu status refresh failed (" + reason + "); previous evidence retained",
            )

    if rows:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for future in as_completed([pool.submit(fetch, row) for row in rows]):
                row, payload, error = future.result()
                values = {"lease_until": None}
                if error is None:
                    values["last_attempt"] = row.previous_attempt
                else:
                    values["error"] = error
                if payload is not None:
                    values.update(payload=payload, content_hash=digest(payload), last_success=timezone.now())
                UbuntuCVEStatus.objects.filter(pk=row.pk, lease_until=row.lease_until).update(**values)
    changed = UbuntuStatusUse.objects.filter(device_id=OuterRef("pk")).filter(
        (~Q(content_hash=F("status__content_hash")) & Q(status__last_success__gte=timezone.now() - TTL))
        | Q(status__last_success__lt=timezone.now() - TTL, content_hash__gt="")
    )
    AgentDevice.objects.filter(
        recent_device(),
        enabled=True,
        os__id="ubuntu",
        distro_requested=False,
        distro_checked_at__lt=timezone.now() - timedelta(minutes=2),
        expires_at__gt=timezone.now(),
    ).filter(Exists(changed)).update(distro_requested=True)


def lookup(advisories, release):
    cves = set()
    for items in advisories.values_list("metadata__cves", flat=True):
        cves.update(items)
        if len(cves) > 100000:
            raise ConnectorError("Ubuntu status lookup budget exceeded")
    import json

    result = {}
    size = 0
    for row in (
        UbuntuCVEStatus.objects.filter(cve__in=cves)
        .only("cve", "payload", "content_hash", "last_success", "error")
        .iterator(chunk_size=10)
    ):
        size += len(json.dumps(row.payload))
        if size > 32 * 1024 * 1024:
            raise ConnectorError("Ubuntu status lookup budget exceeded")
        result[row.cve] = row
    return result


class Resolver:
    def __init__(self, device, release, rows):
        self.device, self.release, self.rows = device, release, rows
        self.pending = set()
        self.seen = set()

    def __call__(self, component, cve, proof, allowed):
        if not allowed:
            return proof
        source = component.package_source
        result = dict(proof)
        result["uncertainty_reason"] = "source_metadata_missing"
        if not source.get("name") or not source.get("version"):
            return result
        if not re.fullmatch(r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+:~_-]{0,119}", source["version"]):
            result["uncertainty_reason"] = "invalid_source_version"
            return result
        self.seen.add(cve)
        row = self.rows.get(cve)
        if not fresh(row):
            self.pending.add(cve)
            result["uncertainty_reason"] = (
                "ubuntu_status_unavailable"
                if row and row.error
                else "ubuntu_status_pending"
                if not row or not row.last_success
                else "ubuntu_status_stale"
            )
            return result
        candidates = row.payload.get(self.release, {}).get(source["name"], [])
        evidence = {
            "cve": cve,
            "source": url(cve),
            "sha256": row.content_hash,
            "release": self.release,
            "source_package": source["name"],
            "source_version": source["version"],
            "checked_at": row.last_success.isoformat(),
            "statuses": candidates,
        }
        result["ubuntu_status"] = evidence
        result["uncertainty_reason"] = "vendor_status_unresolved"
        labels = {
            "needs-triage": "vendor_needs_triage",
            "needed": "vendor_unfixed",
            "pending": "vendor_fix_pending",
            "deferred": "vendor_deferred",
            "ignored": "vendor_ignored",
        }
        if not candidates:
            result["uncertainty_reason"] = "vendor_source_not_listed"
        elif len(candidates) == 1:
            result["uncertainty_reason"] = labels.get(candidates[0]["status"], "vendor_status_unresolved")
        # Multiple pockets/statuses must agree; conflicting or absent facts stay unknown.
        decisions = []
        for entry in candidates:
            status = entry["status"]
            bound = entry["description"]
            if status == "not-affected":
                decisions.append(("not_matched", None, entry))
            elif status == "released" and re.fullmatch(r"[0-9][A-Za-z0-9.+:~_-]{0,119}", bound):
                try:
                    older = distro_oval.compare("dpkg", source["version"], bound) < 0
                except (ValueError, TypeError, AssertionError):
                    return result
                decisions.append(("affected" if older else "fixed", older, entry))
            else:
                return result
        if not decisions or len({x[0] for x in decisions}) != 1:
            return result
        verdict = decisions[0][0]
        result["verdict"] = verdict
        result.pop("uncertainty_reason", None)
        result["reason"] = (
            "Canonical Ubuntu status for this exact release/source package: "
            + verdict
            + ". Repository access, running code and remediation are not attested."
        )
        if verdict in {"affected", "fixed"}:
            result["version_checked"] = True
            result["comparisons"] = [
                {
                    "package": source["name"],
                    "installed_version": source["version"],
                    "operation": "less than",
                    "vendor_version": entry["description"],
                    "matches": older,
                    "basis": "source package",
                }
                for _, older, entry in decisions
            ]
            result["vendor_comments"] = [
                f"{source['name']} source package in {entry['pocket']}/{self.release} is affected and has been fixed (note: '{entry['description']}')."
                for _, _, entry in decisions
            ]
        return result


def proof_current(proof, row):
    evidence = proof.get("ubuntu_status") or {}
    return not evidence or bool(
        fresh(row) and row.cve == evidence.get("cve") and row.content_hash == evidence.get("sha256")
    )


def receipt_flags(components):
    hashes = {
        cve: sha for c in components for cve, sha in c.distro_check.get("ubuntu_status_hashes", {}).items()
    }
    rows = (
        {
            r.cve: r
            for r in UbuntuCVEStatus.objects.filter(cve__in=hashes).only(
                "cve", "content_hash", "last_success"
            )
        }
        if hashes
        else {}
    )
    return {
        c.pk: all(
            fresh(rows.get(cve)) and rows[cve].content_hash == sha
            for cve, sha in c.distro_check.get("ubuntu_status_hashes", {}).items()
        )
        for c in components
    }


def bind(device, resolver):
    enqueue(resolver.seen)
    rows = [
        UbuntuStatusUse(
            device=device,
            status_id=cve,
            content_hash=(resolver.rows[cve].content_hash if fresh(resolver.rows.get(cve)) else ""),
        )
        for cve in resolver.seen
    ]
    UbuntuStatusUse.objects.bulk_create(
        rows,
        update_conflicts=True,
        update_fields=["content_hash"],
        unique_fields=["device", "status"],
        batch_size=500,
    )
    UbuntuStatusUse.objects.filter(device=device).exclude(status_id__in=resolver.seen).delete()


def progress(device_ids):
    """Live lookup progress for the caller's scoped devices, not a vulnerability count."""
    from django.db.models import Count, Max

    current = Q(status__last_success__gte=timezone.now() - TTL) & ~Q(status__content_hash="")
    rows = (
        UbuntuStatusUse.objects.filter(
            device_id__in=device_ids,
            device__organization_id=F("device__asset__organization_id"),
            device__source_id=F("device__asset__source_id"),
        )
        .filter(device__organization_id=F("device__source__organization_id"))
        .values("device_id", "status__error")
        .annotate(
            total=Count("status_id"),
            fresh=Count("status_id", filter=current),
            changed=Count(
                "status_id",
                filter=(current & ~Q(content_hash=F("status__content_hash")))
                | (~current & ~Q(content_hash="")),
            ),
            pending=Count("status_id", filter=~current & Q(status__error="")),
            failed=Count("status_id", filter=~current & ~Q(status__error="")),
            refresh_errors=Count("status_id", filter=current & ~Q(status__error="")),
            last_attempt=Max("status__last_attempt"),
            last_success=Max("status__last_success"),
        )
    )
    result = {}
    for row in rows:
        item = result.setdefault(
            row["device_id"],
            {
                "total": 0,
                "fresh": 0,
                "pending": 0,
                "failed": 0,
                "refresh_errors": 0,
                "changed": 0,
                "errors": [],
            },
        )
        for key in ("total", "fresh", "pending", "failed", "refresh_errors", "changed"):
            item[key] += row[key]
        if row["failed"] or row["refresh_errors"]:
            item["errors"].append(
                {"count": row["failed"] + row["refresh_errors"], "reason": row["status__error"]}
            )
        for key in ("last_attempt", "last_success"):
            value = row[key]
            if value and (not item.get(key) or value > item[key]):
                item[key] = value
    for device_id, item in result.items():
        item["device_id"] = str(device_id)
    return result
