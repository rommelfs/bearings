"""Scheduled public CVE discovery; automated evidence never overrides analyst decisions."""

import re
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .access import audit
from . import misp_cves
from .connectors.http import ConnectorError
from .connectors.vulnerability_lookup import product_records, development_heartbeat
from .intelligence import digest, snapshot_evidence
from .models import DiscoveryMatch, DiscoveryRevision, Finding, Installation, ProductWatch, SourceRecord
from .issues import ensure_vulnerability_issue

RULE = "vendor-product-review/v1"
ERROR = "CVE discovery failed or exceeded its bounds; last complete evidence retained. Check the configured source and product keys."


def same_product(watch, affected):
    if not isinstance(affected, dict):
        return False
    # A public index hit alone is weak evidence. Confirm a structured identifier
    # or exact declared vendor/product identity before evaluating its versions.
    if (
        isinstance(affected.get("vendor"), str)
        and isinstance(affected.get("product"), str)
        and affected["vendor"].casefold() == watch.vendor.casefold()
        and affected["product"].casefold() == watch.product_key.casefold()
    ):
        return True
    identifier = watch.product.identifier
    if identifier.startswith("pkg:") and identifier == affected.get("packageURL"):
        return True
    if not identifier.startswith("cpe:2.3:") or "\\" in identifier:
        return False
    identity = identifier.split(":")
    if (
        len(identity) != 13
        or identity[3:5] != [watch.vendor, watch.product_key]
        or any(v in {"*", "-", ""} for v in identity[2:5])
    ):
        return False
    cpes = affected.get("cpes", [])
    return isinstance(cpes, list) and any(
        isinstance(cpe, str)
        and "\\" not in cpe
        and len(cpe.split(":")) == 13
        and cpe.split(":")[2:5] == identity[2:5]
        for cpe in cpes
    )


def semver(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        return None
    return tuple(int(part) for part in value.split("."))


def version_status(version, entry):
    """Only exact custom versions or plain release SemVer intervals are supported."""
    if not isinstance(entry, dict) or entry.get("status") not in {"affected", "unaffected", "unknown"}:
        return None
    if entry.get("changes"):
        return None
    start = entry.get("version")
    if not isinstance(start, str):
        return None
    if not entry.get("lessThan") and not entry.get("lessThanOrEqual"):
        return entry["status"] if version == start and start not in {"*", "-", "0"} else None
    if entry.get("versionType") != "semver" or (entry.get("lessThan") and entry.get("lessThanOrEqual")):
        return None
    current, low = semver(version), semver(start)
    limit = entry.get("lessThan") or entry.get("lessThanOrEqual")
    high = semver(limit)
    if current is None or low is None or high is None or low > high:
        return None
    if low <= current and (current < high if entry.get("lessThan") else current <= high):
        return entry["status"]
    return None


def evaluation_inputs(watch, installation, payload, *, windows=None):
    from .windows_cves import context

    if windows is None:
        windows = context(installation)
    inputs = [
        digest(payload),
        watch.vendor,
        watch.product_key,
        installation.product.identifier,
        installation.version,
        installation.build,
        installation.edition,
    ]
    if windows is not None:
        inputs.append(windows)
    elif misp_cves.is_misp(watch):
        inputs.append(misp_cves.RULE)
    return inputs


def evaluate(watch, installation, payload, *, windows=None):
    from . import windows_cves

    if windows is None:
        windows = windows_cves.context(installation)
    if windows is not None:
        return windows_cves.evaluate(watch, installation, payload, windows)
    prefix = f"Public product index {watch.vendor}/{watch.product_key}; explicit local product mapping. "
    if payload.get("cveMetadata", {}).get("state") == "REJECTED":
        return "unknown", prefix + "CVE was rejected; reconcile the existing review."
    if not installation.version:
        return "unknown", prefix + "Installed version is unknown; product relevance requires review."
    containers = payload.get("containers", {})
    cna = containers.get("cna", {}) if isinstance(containers, dict) else {}
    affected = cna.get("affected", []) if isinstance(cna, dict) else []
    if not isinstance(affected, list):
        return "unknown", prefix + "Unsupported affected-product evidence."
    entries = [a for a in affected if same_product(watch, a)]
    misp_result = misp_cves.evaluate(watch, installation, cna, entries, semver)
    if misp_result:
        result, reason = misp_result
        return result, prefix + reason
    matches = []
    for item in entries:
        versions = item.get("versions", [])
        if isinstance(versions, list):
            matches.extend(
                status for entry in versions if (status := version_status(installation.version, entry))
            )
    if set(matches) == {"affected"}:
        result, reason = "potential", "A supported structured version rule matches an affected release."
    else:
        result, reason = (
            "unknown",
            "No unambiguous supported affected-version rule; review versions, configuration and vendor fixes.",
        )
    if (
        installation.build
        or installation.edition
        or any(
            a.get("platforms") or a.get("modules") or a.get("programRoutines") or a.get("programFiles")
            for a in entries
        )
    ):
        reason += " Build, edition or configuration qualifiers require human verification."
    return result, prefix + reason + " No confirmed affectedness, exploitation or compromise is inferred."


def sync_watch(pk, *, due=False):
    failed = False
    with transaction.atomic():
        watch = ProductWatch.objects.select_for_update(of=("self",)).select_related("product").get(pk=pk)
        now = timezone.now()
        if not watch.enabled or (
            due
            and not watch.requested
            and watch.last_attempt
            and now - watch.last_attempt < timedelta(minutes=watch.interval_minutes)
        ):
            return None
        try:
            with transaction.atomic():
                source, records = product_records(watch)
                installations = list(
                    Installation.objects.filter(
                        product=watch.product,
                        asset__organization=watch.product.organization,
                        asset__source__organization=watch.product.organization,
                        asset__lifecycle="active",
                    )
                    .select_related(
                        "asset__organization",
                        "product",
                        "agent_component__device__asset",
                        "agent_component__device__source",
                        "agent_component__device__organization",
                        "agent_component__last_report",
                    )
                    .defer("agent_component__last_report__body")
                )
                if len(installations) * len(records) > 10000:
                    raise ConnectorError("Product snapshot exceeds 10000 installation/CVE evaluations")
                from .windows_cves import context

                windows_contexts = {i.pk: context(i) for i in installations}
                changed = 0
                seen = set()
                for identifier, payload in records:
                    record, created = SourceRecord.objects.select_for_update().get_or_create(
                        organization=watch.product.organization,
                        source=source,
                        external_id=identifier,
                        defaults={"payload": payload, "shareable": True},
                    )
                    if not created:
                        snapshot_evidence(record)
                        record.payload, record.ingested_at = payload, now
                        record.save(update_fields=["payload", "ingested_at"])
                    revision = snapshot_evidence(record)
                    for index, installation in enumerate(installations):
                        if index % 100 == 0:
                            development_heartbeat()
                        windows = windows_contexts[installation.pk]
                        result, explanation = evaluate(watch, installation, payload, windows=windows)
                        finding = (
                            Finding.objects.filter(installation=installation, record=record)
                            .order_by("pk")
                            .first()
                        )
                        if finding is None:
                            finding = Finding.objects.create(
                                organization=installation.asset.organization,
                                installation=installation,
                                record=record,
                                rule=RULE,
                                explanation=explanation,
                                applicability=result,
                            )
                        # Preserve existing manual finding identity, rule and original assessment.
                        if finding.rule == RULE:
                            finding.applicability, finding.explanation = result, explanation
                            finding.evaluated_at = now
                            finding.save(update_fields=["applicability", "explanation", "evaluated_at"])
                        inputs = digest(evaluation_inputs(watch, installation, payload, windows=windows))
                        match, new = DiscoveryMatch.objects.get_or_create(
                            finding=finding,
                            defaults={
                                "watch": watch,
                                "evidence_revision": revision,
                                "input_hash": inputs,
                                "explanation": explanation,
                                "result": result,
                            },
                        )
                        if new or match.input_hash != inputs:
                            match.evidence_revision, match.input_hash = revision, inputs
                            match.result, match.explanation, match.review_required = result, explanation, True
                            match.evaluated_at = now
                            match.save()
                            DiscoveryRevision.objects.get_or_create(
                                match=match,
                                fingerprint=inputs,
                                defaults={
                                    "snapshot": {
                                        "evidence_revision": revision.pk,
                                        "version": installation.version,
                                        "edition": installation.edition,
                                        "build": installation.build,
                                        "product_identifier": installation.product.identifier,
                                        "result": result,
                                        "explanation": explanation,
                                        "windows": windows,
                                        "evaluation_rule": (
                                            misp_cves.RULE
                                            if windows is None and misp_cves.is_misp(watch)
                                            else ""
                                        ),
                                    }
                                },
                            )
                            audit(
                                None,
                                installation.asset.organization,
                                "vulnerability.discovery_changed",
                                finding.pk,
                                evidence_revision=revision.pk,
                            )
                            changed += 1
                        ensure_vulnerability_issue(finding)
                        seen.add(match.pk)
                # Missing upstream matches never delete/resolve local findings.
                missing = watch.discoverymatch_set.exclude(pk__in=seen).count()
                watch.summary = {
                    "cves": len(records),
                    "installations": len(installations),
                    "changed": changed,
                    "retained_missing": missing,
                }
        except (ConnectorError, ValidationError, ValueError, TypeError, KeyError):
            failed = True
            watch.error = ERROR
        else:
            watch.error, watch.last_success = "", timezone.now()
        watch.last_attempt, watch.requested = now, False
        watch.save(update_fields=["error", "last_success", "last_attempt", "requested", "summary"])
        audit(
            None,
            watch.product.organization,
            "vulnerability.discovery_failed" if failed else "vulnerability.discovery_synced",
            watch.pk,
        )
    if failed:
        raise ConnectorError(ERROR)
    return watch.summary
