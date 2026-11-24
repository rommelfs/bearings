"""Bounded batch publication inside the caller's device/source/feed transaction.

Only evaluator-owned fields are updated. Finding locks precede match locks, as
in human review. Constructed records retain source revisions and issue snapshots.
"""

import hashlib
import json
import time
import uuid
from functools import reduce
from operator import or_
from django.db.models import Q
from django.utils import timezone
from .connectors.http import ConnectorError
from .intelligence import digest
from .issues import data_for
from .models import (
    SourceRecord,
    SourceRecordRevision,
    Finding,
    DistroMatch,
    DistroMatchRevision,
    AssetIssue,
    IssueRevision,
)
from .presentation import vulnerability_summary

BATCH_SIZE = 200


def exact_pairs(fields, pairs):
    return reduce(or_, (Q(**dict(zip(fields, pair, strict=True))) for pair in pairs))


def lock_findings(device):
    from .distro_cves import RULE

    # Human risk linking locks Finding then SourceRecord. Lock the whole host's
    # existing review set first, including later batches that may share a record.
    list(
        Finding.objects.filter(organization=device.organization, installation__asset=device.asset, rule=RULE)
        .order_by("pk")
        .select_for_update(of=("self",))
        .values_list("pk", flat=True)
    )


def publish_many(device, feed, rows, deadline):
    from .distro_cves import RULE, match_proof, payload
    from .distro_sources import url_for

    def checkpoint():
        if time.monotonic() > deadline:
            raise ConnectorError("Device publication time budget exceeded")

    # The caller already locks/revalidates these bindings. Seed related objects
    # so model clean() can validate the entire constructed chain without FK reads.
    device.asset.source = device.source
    lock_findings(device)
    for offset in range(0, len(rows), BATCH_SIZE):
        checkpoint()
        batch = rows[offset : offset + BATCH_SIZE]
        wanted = {}
        for component, advisory, cve, _, _ in batch:
            if (
                component.device_id != device.pk
                or not component.installation_id
                or component.installation.asset_id != device.asset_id
                or component.installation.product.organization_id != device.organization_id
                or advisory.feed_id != feed.pk
            ):
                raise ConnectorError("Invalid evaluator publication binding")
            component.installation.asset = device.asset
            source = url_for(feed.key) + "#" + advisory.identity
            if len(source) > 250:
                raise ConnectorError("Definition source identity too long")
            wanted[source, cve] = payload(advisory, cve, feed)
        query = exact_pairs(("source", "external_id"), wanted)
        SourceRecord.objects.bulk_create(
            [
                SourceRecord(
                    organization=device.organization,
                    source=source,
                    external_id=cve,
                    payload=data,
                    shareable=True,
                    source_severity=vulnerability_summary(data)["severity"].lower(),
                )
                for (source, cve), data in wanted.items()
            ],
            ignore_conflicts=True,
            batch_size=BATCH_SIZE,
        )
        records = {
            (r.source, r.external_id): r
            for r in SourceRecord.objects.filter(query, organization=device.organization)
            .select_for_update(no_key=True)
            .order_by("pk")
        }
        revisions = {}
        changed_records = []
        for key, data in wanted.items():
            record = records[key]
            # Capture the prior payload before replacing it, including legacy rows
            # that did not already have an immutable revision.
            revisions[record.pk, digest(record.payload)] = record.payload
            revisions[record.pk, digest(data)] = data
            if record.payload != data:
                record.payload = data
                record.source_severity = vulnerability_summary(data)["severity"].lower()
                record.ingested_at = timezone.now()
                changed_records.append(record)
        SourceRecordRevision.objects.bulk_create(
            [
                SourceRecordRevision(record_id=pk, content_hash=sha, payload=data)
                for (pk, sha), data in revisions.items()
            ],
            ignore_conflicts=True,
            batch_size=BATCH_SIZE,
        )
        SourceRecord.objects.bulk_update(
            changed_records, ["payload", "source_severity", "ingested_at"], batch_size=BATCH_SIZE
        )
        evidence = {
            (r.record_id, r.content_hash): r
            for r in SourceRecordRevision.objects.filter(
                exact_pairs(("record_id", "content_hash"), revisions)
            )
        }
        checkpoint()
        items = {}
        for component, advisory, cve, result, proof in batch:
            record = records[url_for(feed.key) + "#" + advisory.identity, cve]
            items[component.installation_id, record.pk] = (component, advisory, record, result, proof)
        Finding.objects.bulk_create(
            [
                Finding(
                    organization=device.organization,
                    installation=component.installation,
                    record=record,
                    rule=RULE,
                    applicability=result,
                    explanation="Automatic distribution package rule; verify source/runtime and review evidence.",
                )
                for component, _, record, result, _ in items.values()
            ],
            ignore_conflicts=True,
            batch_size=BATCH_SIZE,
        )
        findings = {
            (f.installation_id, f.record_id): f
            for f in Finding.objects.filter(
                exact_pairs(("installation_id", "record_id"), items),
                organization=device.organization,
                rule=RULE,
            )
            .select_for_update(of=("self",))
            .order_by("pk")
        }
        new_matches = []
        for key, finding in findings.items():
            component, advisory, record, result, _ = items[key]
            finding.installation = component.installation
            finding.record = record
            finding.organization = device.organization
            new_matches.append(
                DistroMatch(
                    finding=finding,
                    component=component,
                    advisory=advisory,
                    result=result,
                    evidence_revision=evidence[record.pk, digest(record.payload)],
                    input_hash="",
                    snapshot={},
                )
            )
        DistroMatch.objects.bulk_create(new_matches, ignore_conflicts=True, batch_size=BATCH_SIZE)
        matches = {
            m.finding_id: m
            for m in DistroMatch.objects.filter(finding_id__in=[f.pk for f in findings.values()])
            .select_for_update()
            .order_by("pk")
        }
        history, changed_findings = [], []
        now = timezone.now()
        for key, finding in findings.items():
            component, advisory, record, result, proof = items[key]
            match = matches[finding.pk]
            if match.component_id != component.pk or match.advisory_id != advisory.pk:
                raise ConnectorError("Invalid evaluator publication binding")
            snapshot, fingerprint = match_proof(component, feed, advisory, result, proof)
            match.snapshot = snapshot
            match.evaluated_at = now
            match.evidence_revision = evidence[record.pk, digest(record.payload)]
            match.ubuntu_status_id = (proof or {}).get("ubuntu_status", {}).get("cve")
            finding.evaluated_at = now
            if fingerprint != match.input_hash:
                match.input_hash = fingerprint
                match.result = result
                match.review_required = True
                history.append(DistroMatchRevision(match=match, fingerprint=fingerprint, snapshot=snapshot))
                finding.applicability = (
                    result if result in {"potential", "unknown", "not_affected"} else "unknown"
                )
                reason = (proof or {}).get(
                    "reason", "The available package evidence does not establish affectedness."
                )
                finding.explanation = f"{feed.key} vendor OVAL: {result}. Reported package version {snapshot['version']}. {reason} Human assessment and workflow are unchanged."
            changed_findings.append(finding)
        DistroMatch.objects.bulk_update(
            list(matches.values()),
            [
                "snapshot",
                "evaluated_at",
                "evidence_revision",
                "ubuntu_status",
                "input_hash",
                "result",
                "review_required",
            ],
            batch_size=BATCH_SIZE,
        )
        DistroMatchRevision.objects.bulk_create(history, ignore_conflicts=True, batch_size=BATCH_SIZE)
        Finding.objects.bulk_update(
            changed_findings, ["evaluated_at", "applicability", "explanation"], batch_size=BATCH_SIZE
        )
        checkpoint()
        existing = set(AssetIssue.objects.filter(finding_id__in=matches).values_list("finding_id", flat=True))
        issues = []
        for finding in findings.values():
            if finding.pk in existing:
                continue
            finding.full_clean(
                exclude=["organization", "installation", "record"],
                validate_unique=False,
                validate_constraints=False,
            )
            issue = AssetIssue(
                id=None,
                finding=finding,
                organization=device.organization,
                asset=device.asset,
                installation=finding.installation,
                kind="vulnerability",
                title=finding.record.external_id,
                source_label=finding.record.source,
                evidence_text="Linked vulnerability evidence. Open the original review for the current assessment.",
                observed_at=finding.observed_at or finding.evaluated_at,
                owner_team=device.asset.responsible_team,
            )
            issue.full_clean(
                exclude=["id", "finding", "organization", "asset", "installation"],
                validate_unique=False,
                validate_constraints=False,
            )
            # This is a new projection, not a repoint of an existing UUID.
            # Validate before assigning identity to avoid clean()'s old-row lookup.
            issue.pk = uuid.uuid4()
            issues.append(issue)
        AssetIssue.objects.bulk_create(issues, ignore_conflicts=True, batch_size=BATCH_SIZE)
        # UUID PKs survive ignore_conflicts: only snapshot rows actually inserted.
        inserted = set(AssetIssue.objects.filter(pk__in=[i.pk for i in issues]).values_list("pk", flat=True))
        snapshots = []
        for issue in issues:
            if issue.pk in inserted:
                data = data_for(issue)
                sha = hashlib.sha256(
                    json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                snapshots.append(IssueRevision(issue=issue, digest=sha, snapshot=data))
        IssueRevision.objects.bulk_create(snapshots, ignore_conflicts=True, batch_size=BATCH_SIZE)
        checkpoint()
