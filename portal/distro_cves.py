"""Shared vendor caches; scoped local evaluations, retained evidence and unchanged human decisions."""

import json
import uuid
import time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from django.conf import settings
from django.db import transaction, connection, OperationalError
from django.db.models import Q
from django.utils import timezone
from . import agents, distro_oval, distro_sources
from .connectors.http import ConnectorError
from .intelligence import digest, snapshot_evidence
from .issues import ensure_vulnerability_issue
from .models import (
    AgentDevice,
    InventorySource,
    DistroFeed,
    DistroAdvisory,
    DistroAdvisoryPackage,
    DistroMatch,
    DistroMatchRevision,
    SourceRecord,
    Finding,
)

RULE = "distro-oval-review/v1"


def compile_cache(path, key):
    """Compile before taking database locks; a failed/incomplete parse publishes nothing."""
    distro, release = key.split(":")
    with TemporaryDirectory(prefix="bearings-oval-normalized-") as tmp:
        out = Path(tmp) / "rules.jsonl"
        count = size = 0
        stats = {}
        with out.open("w") as stream:
            for row in distro_oval.compile_feed(path, distro, release, stats=stats):
                count += 1
                if count > 100000 or not row["id"] or len(row["id"]) > 200:
                    raise ConnectorError("Vendor definition limit/identity invalid")
                raw = json.dumps(row, separators=(",", ":"))
                size += len(raw)
                if len(raw) > 1024 * 1024 or size > 384 * 1024 * 1024:
                    raise ConnectorError("Normalized feed limit exceeded")
                stream.write(raw + "\n")
        if not count:
            raise ConnectorError("Empty/unrecognized vendor feed")
        yield out, count, stats


def refresh(pk):
    now = timezone.now()
    lease = uuid.uuid4()
    with transaction.atomic():
        f = DistroFeed.objects.select_for_update().get(pk=pk)
        current_compiler = f.summary.get("compiler_version") == distro_oval.COMPILER_VERSION
        if (
            not f.enabled
            or (f.lease_until and f.lease_until > now)
            or (
                f.last_attempt
                and f.last_attempt > now - timedelta(minutes=15)
                and (current_compiler or f.error)
            )
            or (current_compiler and f.last_success and f.last_success > now - timedelta(hours=6))
        ):
            return False
        f.lease_id = lease
        f.lease_until = now + timedelta(minutes=10)
        f.last_attempt = now
        f.save(update_fields=["lease_id", "lease_until", "last_attempt"])
        key = f.key
    try:
        with distro_sources.download(key) as (path, sha):
            if f.content_hash == sha and f.generation and current_compiler:
                with transaction.atomic():
                    f = DistroFeed.objects.select_for_update().get(pk=pk)
                    if f.lease_id != lease or not f.enabled:
                        raise ConnectorError("Feed policy changed")
                    f.last_success = timezone.now()
                    f.error = ""
                    f.lease_id = f.lease_until = None
                    f.save(update_fields=["last_success", "error", "lease_id", "lease_until"])
                return True
            for compiled, count, stats in compile_cache(path, key):
                generation = uuid.uuid4()
                with transaction.atomic():
                    f = DistroFeed.objects.select_for_update().get(pk=pk)
                    if f.lease_id != lease or not f.enabled or f.lease_until < timezone.now():
                        raise ConnectorError("Feed policy/lease changed")
                    DistroAdvisoryPackage.objects.filter(feed=f).delete()
                    with compiled.open() as stream:
                        batch = []
                        for line in stream:
                            batch.append(json.loads(line))
                            if len(batch) >= 250:
                                store_batch(f, generation, batch)
                                batch = []
                        if batch:
                            store_batch(f, generation, batch)
                    f.generation = generation
                    f.content_hash = sha
                    f.last_success = timezone.now()
                    f.error = ""
                    f.summary = stats
                    f.lease_id = f.lease_until = None
                    f.save()
                    distro, release = key.split(":")
                    versions = Q(os__version=release)
                    if distro != "ubuntu":
                        versions |= Q(os__version__startswith=release + ".")
                    AgentDevice.objects.filter(versions, os__id=distro, enabled=True).update(
                        distro_requested=True
                    )
        return True
    except Exception as exc:
        # No response/body/credentials enter logs; preserve the last complete generation.
        DistroFeed.objects.filter(pk=pk, lease_id=lease).update(
            error="Vendor refresh failed (" + type(exc).__name__ + "); last complete cache retained",
            lease_id=None,
            lease_until=None,
        )
        return False


def store_batch(feed, generation, batch):
    # Bulk upsert stable definition identities; old evidence snapshots remain immutable.
    advisories = DistroAdvisory.objects.bulk_create(
        [
            DistroAdvisory(
                feed=feed,
                identity=r["id"],
                generation=generation,
                metadata=r["metadata"],
                criteria=r["criteria"],
                content_hash=digest(r),
            )
            for r in batch
        ],
        update_conflicts=True,
        unique_fields=["feed", "identity"],
        update_fields=["generation", "metadata", "criteria", "content_hash"],
        batch_size=250,
    )
    rows = []
    for a, r in zip(advisories, batch):
        rows.extend(DistroAdvisoryPackage(feed=feed, advisory=a, manager=m, name=n) for m, n in r["packages"])
    DistroAdvisoryPackage.objects.bulk_create(rows, batch_size=1000)


def feed_state(feed):
    if not feed or not feed.enabled or not feed.generation:
        return "pending"
    if feed.summary.get("compiler_version") != distro_oval.COMPILER_VERSION:
        return "pending"
    if not feed.last_success or feed.last_success < timezone.now() - timedelta(hours=12):
        return "stale"
    return "ready"


@transaction.atomic
def evaluate_device(pk):
    device = (
        AgentDevice.objects.select_for_update(of=("self",), nowait=True)
        .select_related("asset", "organization", "source")
        .get(pk=pk)
    )
    if not agents.current(device) or device.stale:
        return None
    InventorySource.objects.select_for_update(nowait=True).get(pk=device.source_id)
    device.asset.refresh_from_db()
    if not agents.current(device):
        return None
    key = distro_sources.key_for(device.os)
    feed = DistroFeed.objects.filter(key=key).first() if key else None
    state = feed_state(feed) if key else "unsupported"
    if state != "ready":
        device.distro_summary = {
            "state": state,
            "feed": key or "",
            "message": "Vendor cache not ready/stale or distribution release unsupported; coverage is unknown.",
        }
        device.distro_requested = False
        device.distro_checked_at = timezone.now()
        device.save(update_fields=["distro_summary", "distro_requested", "distro_checked_at"])
        return device.distro_summary
    # Hold cache generation stable only during local evaluation, never network I/O.
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM portal_distrofeed WHERE id = %s FOR SHARE NOWAIT", [feed.pk])
        feed.refresh_from_db()
    else:
        feed = DistroFeed.objects.get(pk=feed.pk)
    if feed_state(feed) != "ready":
        return None
    components = list(
        device.components.select_related("installation__product").filter(
            observed_at__gte=timezone.now() - timedelta(hours=12), missing_since__isnull=True
        )
    )
    facts = defaultdict(list)
    by_id = {}
    source_missing = 0
    for c in components:
        if (
            not c.installation_id
            or c.installation.asset_id != device.asset_id
            or c.installation.product.organization_id != device.organization_id
        ):
            continue
        if c.package_identity.get("distribution") != device.os.get("id") or c.package_identity.get(
            "release"
        ) != device.os.get("version"):
            continue
        by_id[c.pk] = c
        value = {"id": c.pk, "version": c.version, "architecture": c.architecture}
        facts[(c.manager, False, c.name)].append(value)
        source = c.package_source
        if source:
            facts[(c.manager, True, source["name"])].append({**value, "version": source["version"]})
        elif key.startswith("debian:"):
            source_missing += 1
    complete = bool(device.last_complete_at and device.last_complete_at == device.last_observed_at)
    names = Q(manager="dpkg", name__in=[n for m, src, n in facts if m == "dpkg"]) | Q(
        manager="rpm", name__in=[n for m, src, n in facts if m == "rpm"]
    )
    ids = (
        DistroAdvisoryPackage.objects.filter(names, feed=feed)
        .values_list("advisory_id", flat=True)
        .distinct()
    )
    advisories = DistroAdvisory.objects.filter(pk__in=ids, feed=feed, generation=feed.generation)
    if advisories.count() > 30000:
        raise ConnectorError("Device advisory evaluation budget exceeded")
    found = {}
    evaluated = {}
    rules = 0
    unknown = 0
    deadline = time.monotonic() + 120
    for advisory in advisories.iterator(chunk_size=200):
        if time.monotonic() > deadline:
            raise ConnectorError("Device evaluation time budget exceeded")
        result, contributors = distro_oval.evaluate(
            advisory.criteria,
            facts,
            {"binary": complete, "source": complete and not source_missing},
            device.os,
        )
        evaluated[advisory.pk] = result
        rules += 1
        if result is None:
            unknown += 1
        if result is False:
            continue
        for cid in contributors:
            if cid not in by_id:
                continue
            for cve in advisory.metadata["cves"]:
                found[(cid, advisory.pk, cve)] = (
                    by_id[cid],
                    advisory,
                    "potential" if result is True else "unknown",
                )
        if len(found) > 2000:
            raise ConnectorError("Device CVE result budget exceeded; no partial evaluation published")
    for (cid, aid, cve), (component, advisory, result) in found.items():
        if time.monotonic() > deadline:
            raise ConnectorError("Device publication time budget exceeded")
        publish(device, feed, component, advisory, cve, result)
    # A changed package can update automated evidence; never close a human workflow.
    old = DistroMatch.objects.filter(component__device=device).select_related(
        "finding__record", "advisory", "component__installation"
    )
    for match in old:
        ident = (match.component_id, match.advisory_id, match.finding.record.external_id)
        if ident in found and match.component.installation_id == match.finding.installation_id:
            continue
        if (
            match.component_id not in by_id
            or match.component.installation_id != match.finding.installation_id
        ):
            result = "not_observed"
        elif match.advisory.generation != feed.generation or match.advisory.feed_id != feed.pk:
            result = "unknown"
        elif evaluated.get(match.advisory_id, "absent") is False:
            result = "not_affected"
        else:
            result = "unknown"
        component = by_id.get(match.component_id)
        if (
            component
            and component.installation_id == match.finding.installation_id
            and match.advisory.feed_id == feed.pk
            and match.advisory.generation == feed.generation
        ):
            publish(device, feed, component, match.advisory, match.finding.record.external_id, result)
        else:
            update_match(match, component, feed, result)
    summary = {
        "state": "partial"
        if source_missing or unknown or feed.summary.get("unindexed_definitions", 0)
        else "ready",
        "unindexed_definitions": feed.summary.get("unindexed_definitions", 0),
        "feed": key,
        "generation": str(feed.generation),
        "source_url": distro_sources.url_for(key),
        "packages": len(by_id),
        "rules_checked": rules,
        "potential": sum(v[2] == "potential" for v in found.values()),
        "uncertain": sum(v[2] == "unknown" for v in found.values()),
        "unsupported_conditions": unknown,
        "missing_source_metadata": source_missing,
        "message": "Vendor package-rule matches; official repository/signature, running code and remediation are not attested. No matching rule is not proof of safety.",
    }
    device.distro_summary = summary
    device.distro_requested = False
    device.distro_checked_at = timezone.now()
    device.save(update_fields=["distro_summary", "distro_requested", "distro_checked_at"])
    return summary


def payload(advisory, cve, feed):
    return {
        "cveMetadata": {"cveId": cve},
        "containers": {
            "cna": {
                "title": advisory.metadata["title"],
                "descriptions": [{"lang": "en", "value": advisory.metadata["description"]}],
            }
        },
        "bearings_distro": {
            "schema": "bearings.distro-oval.v1",
            "feed": feed.key,
            "definition": advisory.identity,
            "severity": advisory.metadata["severity"],
            "criteria": advisory.criteria,
            "definition_sha256": advisory.content_hash,
        },
    }


def publish(device, feed, component, advisory, cve, result):
    source = distro_sources.url_for(feed.key) + "#" + advisory.identity
    if len(source) > 250:
        raise ConnectorError("Definition source identity too long")
    data = payload(advisory, cve, feed)
    record, created = SourceRecord.objects.get_or_create(
        organization=device.organization,
        source=source,
        external_id=cve,
        defaults={"payload": data, "shareable": True},
    )
    if not created and record.payload != data:
        snapshot_evidence(record)
        record.payload = data
        record.ingested_at = timezone.now()
        record.save(update_fields=["payload", "ingested_at"])
    revision = snapshot_evidence(record)
    finding, _ = Finding.objects.get_or_create(
        organization=device.organization,
        installation=component.installation,
        record=record,
        rule=RULE,
        defaults={
            "applicability": result,
            "explanation": "Automatic distribution package rule; verify source/runtime and review evidence.",
        },
    )
    match, _ = DistroMatch.objects.get_or_create(
        finding=finding,
        defaults={
            "component": component,
            "advisory": advisory,
            "result": result,
            "evidence_revision": revision,
            "input_hash": "",
            "snapshot": {},
        },
    )
    match.evidence_revision = revision
    update_match(match, component, feed, result)
    ensure_vulnerability_issue(finding)


def update_match(match, component, feed, result):
    # Human review locks Finding first; use the same order to avoid a review/evaluation deadlock.
    revision = match.evidence_revision
    finding = Finding.objects.select_for_update().get(pk=match.finding_id)
    match = DistroMatch.objects.select_for_update().get(pk=match.pk)
    match.finding = finding
    match.evidence_revision = revision
    snapshot = {
        "feed": feed.key,
        "generation": str(feed.generation),
        "result": result,
        "version": component.version if component else "",
        "package": component.package_identity if component else {},
        "source_package": component.package_source if component else {},
        "rule_sha256": match.advisory.content_hash,
    }
    fingerprint = digest({k: v for k, v in snapshot.items() if k != "generation"})
    if fingerprint == match.input_hash:
        return
    match.result = result
    match.input_hash = fingerprint
    match.snapshot = snapshot
    match.review_required = True
    match.evaluated_at = timezone.now()
    match.save()
    DistroMatchRevision.objects.get_or_create(
        match=match, fingerprint=fingerprint, defaults={"snapshot": snapshot}
    )
    finding = match.finding
    finding.applicability = result if result in {"potential", "unknown", "not_affected"} else "unknown"
    finding.explanation = f"{feed.key} vendor OVAL: {result}. Reported package version {snapshot['version']}; source package {snapshot['source_package']}. Exact native Debian/RPM comparison; unsupported conditions remain unknown. Package origin/runtime and remediation are not attested. Human assessment and workflow are unchanged."
    finding.evaluated_at = timezone.now()
    finding.save(update_fields=["applicability", "explanation", "evaluated_at"])


def run(limit=5):
    if not settings.DISTRO_CVE_ENABLED:
        return 0
    pending = list(
        AgentDevice.objects.filter(
            enabled=True,
            distro_requested=True,
            last_observed_at__gte=timezone.now() - timedelta(hours=12),
            expires_at__gt=timezone.now(),
            organization__merged_into__isnull=True,
        ).order_by("pk")[:limit]
    )
    for d in pending:
        key = distro_sources.key_for(d.os)
        if key:
            DistroFeed.objects.get_or_create(key=key)
    # One vendor cache per invocation; unchanged complete caches are shared by every company.
    old_compiler = Q(summary__compiler_version__isnull=True) | ~Q(
        summary__compiler_version=distro_oval.COMPILER_VERSION
    )
    for f in (
        DistroFeed.objects.filter(enabled=True)
        .filter(
            Q(last_attempt__isnull=True)
            | Q(last_attempt__lt=timezone.now() - timedelta(minutes=15))
            | (old_compiler & Q(error=""))
        )
        .filter(
            Q(last_success__isnull=True)
            | Q(last_success__lt=timezone.now() - timedelta(hours=6))
            | old_compiler
        )
        .order_by("last_attempt", "pk")[:1]
    ):
        refresh(f.pk)
    total = 0
    for d in pending:
        try:
            with transaction.atomic():
                evaluate_device(d.pk)
            total += 1
        except OperationalError:
            continue  # Busy source/device/cache: retain pending input for the next invocation.
        except Exception as exc:
            AgentDevice.objects.filter(pk=d.pk).update(
                distro_requested=False,
                distro_checked_at=timezone.now(),
                distro_summary={
                    "state": "error",
                    "message": "Evaluation deferred ("
                    + type(exc).__name__
                    + "); retained evidence needs review.",
                },
            )
    # Retry coverage failures independently of inventory cadence, without spinning on a failed source.
    AgentDevice.objects.filter(
        enabled=True,
        distro_requested=False,
        distro_checked_at__lt=timezone.now() - timedelta(minutes=15),
        distro_summary__state__in=["pending", "stale", "error"],
    ).update(distro_requested=True)
    return total


def coverage(device):
    summary = dict(device.distro_summary)
    summary.setdefault("state", "pending")
    key = distro_sources.key_for(device.os)
    if not key:
        summary.update(
            state="unsupported",
            message="No supported vendor feed for this exact distribution/release; coverage is unknown.",
        )
    else:
        feed = DistroFeed.objects.filter(key=key).first()
        if feed:
            summary["last_feed_success"] = feed.last_success
            summary["feed_error"] = feed.error
            if feed_state(feed) != "ready":
                summary["state"] = feed_state(feed)
    summary["queued"] = device.distro_requested
    summary["checked_at"] = device.distro_checked_at
    if device.stale or not agents.current(device):
        summary["state"] = "stale"
    return summary
