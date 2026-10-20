"""Scoped historical exposure evidence. Window absence never establishes port closure."""

import ipaddress
import json
import math
from datetime import datetime, timezone as utc
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from .access import audit, can_edit, can_operator_review, is_analyst, organizations_for, require
from .asset_context import asset_context
from .connectors.plum import infoip
from .models import Asset, AssetIssue, ExposureReview, InfrastructureClaim, PlumInstance, PlumSnapshot
from .notifications import digest
from .scope import matches, normalize

MAX_IPS = 2000
MAX_REPORTS = 10000
MAX_PORTS = 4096


def instant(value):
    try:
        if type(value) in {int, float} and math.isfinite(value):
            result = datetime.fromtimestamp(value, tz=utc.utc)
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError()
        if timezone.is_naive(result) or result > timezone.now():
            raise ValueError()
        return result.astimezone(utc.utc)
    except (ValueError, OverflowError, OSError):
        raise ValidationError("Use valid, timezone-aware non-future observation timestamps") from None


def visible_snapshots(actor):
    qs = (
        PlumSnapshot.objects.filter(organization__in=organizations_for(actor))
        .filter(
            Q(asset__isnull=True)
            | Q(
                asset__organization_id=F("organization_id"),
                asset__source__organization_id=F("organization_id"),
            )
        )
        .filter(
            scope_claim__organization_id=F("organization_id"),
            scope_claim__status="verified",
            scope_claim__valid_from__lte=F("window_start"),
            scope_claim__kind__in=["ip", "network", "range"],
            scope_claim__kind=F("proof_kind"),
            scope_claim__value=F("proof_value"),
            scope_claim__network_context=F("proof_context"),
            scope_claim__valid_from=F("proof_from"),
        )
        .filter(
            Q(scope_claim__valid_until__isnull=True, proof_until__isnull=True)
            | Q(scope_claim__valid_until=F("proof_until"))
        )
        .filter(Q(scope_claim__valid_until__isnull=True) | Q(scope_claim__valid_until__gt=F("window_stop")))
        .select_related("source", "organization", "asset__source__instance", "scope_claim")
    )
    if not actor.is_superuser:
        policy = Q(source__organizations=F("organization_id"))
        if is_analyst(actor):
            policy |= Q(organization__operator_visibility=True)
        qs = qs.filter(policy).distinct()
    return qs


def source_allowed(actor, org, source):
    return (
        actor.is_active
        and organizations_for(actor).filter(pk=org.pk).exists()
        and (can_edit(actor, org) or can_operator_review(actor, org))
        and (can_operator_review(actor, org) or source.organizations.filter(pk=org.pk).exists())
    )


def verified_claim(org, ip, start, stop):
    for claim in InfrastructureClaim.objects.filter(
        organization=org, status="verified", kind__in=["ip", "network", "range"]
    ).order_by("pk"):
        if matches(claim, ip, start, org.pk, claim.network_context) and matches(
            claim, ip, stop, org.pk, claim.network_context
        ):
            return claim
    raise ValidationError(
        "A currently verified customer IP/network assignment must cover the entire requested window"
    )


def mapped_asset(org, ip, chosen=None):
    if chosen:
        candidates = [chosen]
    else:
        candidates = (
            Asset.objects.filter(organization=org, source__organization=org)
            .exclude(object_type="ipam.prefix")
            .select_related("source__instance")
        )
    found = []
    for asset in candidates:
        if asset.organization_id != org.pk or asset.source.organization_id != org.pk:
            raise ValidationError("Observation asset belongs to another organization")
        for address in asset_context(asset)["addresses"]:
            try:
                if str(ipaddress.ip_interface(address["prefix"]).ip) == ip:
                    found.append(asset)
                    break
            except ValueError:
                continue
    if chosen and not found:
        raise ValidationError(
            "The selected asset has no matching authoritative inventory IP; NAT mappings are not inferred"
        )
    machines = [
        asset for asset in found if asset.object_type in {"dcim.device", "virtualization.virtualmachine"}
    ]
    matches_ = machines or found
    return matches_[0] if len(matches_) == 1 else None


def normalize_result(source, result, ip=None, start=None, stop=None):
    if result is None:
        if ip is None or start is None or stop is None:
            raise ValidationError("A 404 observation requires the queried IP and window")
        data = {"ip": ip, "start": start, "stop": stop, "report_count": 0, "ports": []}
        state = "not_indexed"
    else:
        data = result.get("result") if isinstance(result, dict) else None
        state = "indexed"
    if not isinstance(data, dict):
        raise ValidationError("Expected a Plum InfoIP JSON result")
    try:
        address = ipaddress.ip_address(data.get("ip"))
    except (ValueError, TypeError):
        raise ValidationError("Expected one valid observation IP, not a range") from None
    if not source.fixture and (not address.is_global or address.is_multicast):
        raise ValidationError("Live Plum observations require public unicast IPs")
    begin, end = instant(data.get("start")), instant(data.get("stop"))
    if begin > end:
        raise ValidationError("Observation window is reversed")
    if ip and str(address) != str(ipaddress.ip_address(ip)):
        raise ValidationError("Plum response IP does not match the requested IP")
    if start and begin != instant(start) or stop and end != instant(stop):
        raise ValidationError("Plum response window does not match the request")
    count, ports = data.get("report_count"), data.get("ports")
    if (
        type(count) is not int
        or not 0 <= count <= 1_000_000_000
        or not isinstance(ports, list)
        or len(ports) > MAX_PORTS
    ):
        raise ValidationError("Invalid or oversized observation count/port list")
    if count == 0 and ports:
        raise ValidationError("Ports cannot be asserted without any reports")
    rows, seen = [], set()
    for row in ports:
        if (
            not isinstance(row, dict)
            or type(row.get("port")) is not int
            or not 0 <= row["port"] <= 65535
            or row.get("protocol") not in (None, "tcp", "udp")
        ):
            raise ValidationError("Invalid protocol/port observation")
        host = row.get("hostname", "")
        if not isinstance(host, str) or len(host) > 253:
            raise ValidationError("Invalid requested hostname")
        if host:
            host = normalize("domain", host)
        key = (row["port"], row.get("protocol"), host)
        if key in seen:
            raise ValidationError("Duplicate protocol/port/hostname entry")
        seen.add(key)
        first, last = instant(row.get("first_seen")), instant(row.get("last_seen"))
        if first > last or not begin <= last <= end:
            raise ValidationError("Port timestamp is outside the declared positive-observation window")
        tags = row.get("tags", [])
        if (
            not isinstance(tags, list)
            or len(tags) > 100
            or any(not isinstance(tag, str) or len(tag) > 250 for tag in tags)
        ):
            raise ValidationError("Invalid bounded report-level tags")
        port_state = row.get("observation_state", "open_observed")
        if port_state not in ("open_observed", "reported", "closed_reported", "filtered"):
            raise ValidationError("Unsupported port evidence state")
        rows.append(
            {
                "port": row["port"],
                "protocol": row.get("protocol"),
                "hostname": host,
                "first_seen": first.isoformat() if first >= begin else None,
                "first_before_window": first < begin,
                "last_seen": last.isoformat(),
                "tags": sorted(set(tags)),
                "observation_state": port_state,
                "reports": row.get("reports", [])[:100] if isinstance(row.get("reports", []), list) else [],
            }
        )
    return str(address), begin, end, state, count, rows


@transaction.atomic
def ingest(actor, org, source, result, *, asset=None, ip=None, start=None, stop=None):
    source = PlumInstance.objects.get(pk=source.pk)
    source.full_clean()
    require(source.enabled and source_allowed(actor, org, source))
    address, begin, end, state, count, ports = normalize_result(source, result, ip, start, stop)
    claim = verified_claim(org, address, begin, end)
    # Lock scope and revalidate so concurrent revocation cannot commit a newly disclosed projection.
    claim = InfrastructureClaim.objects.select_for_update().get(pk=claim.pk)
    if not (
        matches(claim, address, begin, org.pk, claim.network_context)
        and matches(claim, address, end, org.pk, claim.network_context)
    ):
        raise ValidationError("Network assignment changed during import")
    target = mapped_asset(org, address, asset)
    proof = {
        "claim": claim.pk,
        "kind": claim.kind,
        "value": claim.value,
        "context": claim.network_context,
        "from": claim.valid_from.isoformat(),
        "until": claim.valid_until.isoformat() if claim.valid_until else None,
    }
    data = {
        "ip": address,
        "start": begin.isoformat(),
        "stop": end.isoformat(),
        "state": state,
        "count": count,
        "ports": ports,
        "asset": str(target.pk) if target else None,
        "proof": proof,
    }
    raw_hash = digest(
        result
        if result is not None
        else {"http_status": 404, "ip": address, "window": [begin.isoformat(), end.isoformat()]}
    )
    row, created = PlumSnapshot.objects.get_or_create(
        source=source,
        organization=org,
        fingerprint=digest(data),
        defaults={
            "asset": target,
            "scope_claim": claim,
            "proof_kind": claim.kind,
            "proof_value": claim.value,
            "proof_context": claim.network_context,
            "proof_from": claim.valid_from,
            "proof_until": claim.valid_until,
            "ip": address,
            "window_start": begin,
            "window_stop": end,
            "state": state,
            "report_count": count,
            "ports": ports,
            "source_digest": raw_hash,
            "imported_by": actor,
        },
    )
    audit(actor, org, "plum.observation_imported", row.pk, created=created, source=str(source.pk))
    return row


def fetch(actor, org, source, ip, start, stop, asset=None):
    require(source_allowed(actor, org, source))
    begin, end = instant(start), instant(stop)
    if begin > end:
        raise ValidationError("Observation window is reversed")
    verified_claim(org, ip, begin, end)
    result = infoip(source, ip, begin, end)
    return ingest(
        actor, org, source, result, asset=asset, ip=ip, start=begin.isoformat(), stop=end.isoformat()
    )


def export_results(payload):
    """Normalize the reviewed full-export envelope; never follow document URLs or execute search queries."""
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("results"), dict)
        or not isinstance(payload.get("time_range"), dict)
    ):
        raise ValidationError("Expected a Plum full JSON export with results and time_range")
    if len(payload["results"]) > MAX_IPS:
        raise ValidationError(
            "Export exceeds 2,000 observed IPs; partition it by verified customer network/time"
        )
    begin, end = instant(payload["time_range"].get("from_ts")), instant(payload["time_range"].get("to_ts"))
    total = 0
    for ip, reports in payload["results"].items():
        if not isinstance(reports, list):
            raise ValidationError("Invalid export reports")
        total += len(reports)
        if total > MAX_REPORTS:
            raise ValidationError("Export exceeds 10,000 reports; split the export")
        ports, selected = {}, 0
        for entry in reports:
            if (
                not isinstance(entry, dict)
                or entry.get("warning")
                or not isinstance(entry.get("document"), dict)
            ):
                raise ValidationError("Incomplete exported report; last-known data retained")
            uid = entry.get("uid")
            if not isinstance(uid, str) or not uid or len(uid) > 250:
                raise ValidationError("Missing bounded source report identity")
            first, last = instant(entry.get("first_seen")), instant(entry.get("last_seen"))
            if first > last:
                raise ValidationError("Reversed report observation interval")
            # Full export overlaps windows; only last_seen-in-window proves a positive observation here.
            if not begin <= last <= end:
                continue
            selected += 1
            document = entry["document"]
            body = document.get("body")
            if not isinstance(body, dict) or not isinstance(body.get("ports"), list):
                raise ValidationError("Unsupported export scan document schema")
            if len(body["ports"]) > 4096:
                raise ValidationError("Export report exceeds 4096 ports")
            if body.get("addr") and str(body["addr"]) != str(ip):
                raise ValidationError("Export IP and report IP disagree")
            hostnames = body.get("hostnames", [])
            if not isinstance(hostnames, list) or len(hostnames) > 100:
                raise ValidationError("Invalid hostname context")
            requested = sorted(
                {
                    normalize("domain", h["name"])
                    for h in hostnames
                    if isinstance(h, dict) and str(h.get("type", "")).lower() == "user" and h.get("name")
                }
            ) or [""]
            for raw in body["ports"]:
                if not isinstance(raw, dict) or not str(raw.get("portid", "")).isdecimal():
                    raise ValidationError("Unsupported exported port")
                proto = raw.get("protocol")
                if proto not in (None, "tcp", "udp"):
                    raise ValidationError("Unsupported exported protocol")
                raw_state = raw.get("state")
                state = {
                    "open": "open_observed",
                    "closed": "closed_reported",
                    "filtered": "filtered",
                    None: "reported",
                }.get(raw_state)
                if state is None:
                    raise ValidationError("Unsupported exported port state; retain explicit uncertainty")
                for host in requested:
                    key = (int(raw["portid"]), proto, host)
                    existing = ports.get(key)
                    candidate = {
                        "port": key[0],
                        "protocol": proto,
                        "hostname": host,
                        "first_seen": first.isoformat(),
                        "last_seen": last.isoformat(),
                        "tags": [],
                        "observation_state": state,
                        "reports": [uid],
                    }
                    if not existing or instant(existing["last_seen"]) < last:
                        ports[key] = candidate
                    elif instant(existing["last_seen"]) == last:
                        if existing["observation_state"] != state:
                            raise ValidationError("Conflicting scan states at the same timestamp")
                        existing["reports"] = sorted(set(existing["reports"] + [uid]))[:100]
                    if len(ports) > MAX_PORTS:
                        raise ValidationError("Exported IP has too many port/hostname observations")
        yield {
            "result": {
                "ip": ip,
                "start": begin.isoformat(),
                "stop": end.isoformat(),
                "report_count": selected,
                "ports": list(ports.values()),
            }
        }


@transaction.atomic
def import_export(actor, org, source, payload):
    rows = list(export_results(payload))
    if not rows:
        raise ValidationError("Export contains no IP records")
    return [ingest(actor, org, source, row) for row in rows]


def compare(current, baseline=None):
    if baseline and (current.organization_id, current.source_id, current.ip, current.asset_id) != (
        baseline.organization_id,
        baseline.source_id,
        baseline.ip,
        baseline.asset_id,
    ):
        raise ValidationError("Compare only the same customer/source/IP/asset context")
    if baseline and baseline.window_stop >= current.window_stop:
        raise ValidationError("Baseline must end before the current window")

    def key(row):
        return (row["port"], row["protocol"] or "unknown", row["hostname"])

    now = {key(row): row for row in current.ports}
    before = {key(row): row for row in baseline.ports} if baseline else {}
    changes = []
    for identity in sorted(now.keys() | before.keys()):
        row = now.get(identity) or before[identity]
        if identity not in now:
            state = "not_observed"
        elif now[identity]["observation_state"] == "closed_reported":
            state = "closed_reported"
        elif now[identity]["observation_state"] == "filtered":
            state = "filtered"
        elif identity[1] == "unknown":
            state = "unknown_protocol"
        elif not baseline:
            state = "observed"
        elif identity not in before:
            state = "newly_observed"
        elif before[identity]["observation_state"] != now[identity]["observation_state"]:
            state = "changed_evidence"
        else:
            state = "still_observed"
        changes.append({**row, "change": state})
    return changes


@transaction.atomic
def create_review(actor, observation, port, protocol, hostname, reason):
    from .issues import save_issue

    observation = visible_snapshots(actor).get(pk=observation.pk)
    require(can_edit(actor, observation.organization) or can_operator_review(actor, observation.organization))
    if not observation.asset_id:
        raise ValidationError(
            "Resolve the inventory mapping before creating an asset issue; no asset is inferred"
        )
    matches_ = [
        row
        for row in observation.ports
        if (row["port"], row["protocol"] or "unknown", row["hostname"]) == (port, protocol, hostname)
    ]
    if len(matches_) != 1:
        raise ValidationError("Choose a port observation from this snapshot")
    identity = digest(
        [
            str(observation.source_id),
            str(observation.organization_id),
            str(observation.asset_id),
            observation.ip,
            port,
            protocol,
            hostname,
        ]
    )
    observation.asset = Asset.objects.select_for_update().get(pk=observation.asset_id)
    if observation.asset.organization_id != observation.organization_id:
        raise ValidationError("Asset assignment changed")
    existing = ExposureReview.objects.filter(identity=identity).first()
    if existing:
        return existing.issue
    row = matches_[0]
    issue = save_issue(
        actor,
        AssetIssue(organization=observation.organization),
        {
            "asset": observation.asset,
            "kind": "exposure",
            "title": f"Observed service {observation.ip} · {port}/{protocol}",
            "source_label": observation.source.name + " / Plum Island",
            "source_url": observation.source.base_url + "/api/v1/infoip/" + observation.ip,
            "observed_at": instant(row["last_seen"]),
            "evidence_text": json.dumps(
                {
                    "observation": str(observation.pk),
                    "window": [observation.window_start.isoformat(), observation.window_stop.isoformat()],
                    "port": row,
                    "source_digest": observation.source_digest,
                    "coverage": "Historical evidence; complete scan coverage not asserted",
                },
                indent=2,
            ),
            "consequence": "Review whether this service and its exposure are intended. Misconfiguration, service failure or possible compromise need independent evidence.",
            "next_action": "Validate ownership, intended exposure and current service state before notifying or changing systems.",
        },
        reason,
    )
    ExposureReview.objects.create(
        issue=issue, observation=observation, identity=identity, port=port, protocol=protocol
    )
    return issue
