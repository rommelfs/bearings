"""Explain recorded coverage limits without inventing host remediation or CVE verdicts."""

from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from . import distro_results
from .models import AgentReport


def count(summary, key):
    value = summary.get(key)
    return value if type(value) is int and value >= 0 else 0


def explain(summary):
    source = count(summary, "missing_source_metadata")
    rules = count(summary, "unsupported_conditions")
    matches = count(summary, "uncertain")
    feed = count(summary, "unindexed_definitions")
    reasons = []
    if source:
        reasons.append(
            f"{source} reported Debian packages lack source-package names/versions. Check source-package collection and obtain a fresh inventory report; update the client if needed."
        )
    if rules:
        reasons.append(
            f"{rules} vendor definitions associated with reported package names could not be decided with supported facts."
        )
    if matches:
        reasons.append(
            f"{matches} package/definition/CVE associations remain unresolved. These are not confirmed vulnerable installations."
        )
    if feed:
        reasons.append(
            f"{feed} definitions in the entire vendor feed cannot be indexed. Their relevance to this host is unknown; this feed-wide count is not a host-specific finding."
        )
    if not reasons:
        reasons.append(
            "The stored partial result does not identify which limitation caused it. No server change can be recommended from this status alone."
        )
    return {
        "actionable": bool(source),
        "title": "Supply missing source-package facts" if source else "Recorded package-check limitations",
        "reason": " ".join(reasons),
        "items": reasons,
        "guidance": "A package update or client restart is not indicated by coverage limits alone. The platform operator can inspect evaluator support; assess actual CVE/version evidence separately.",
    }


def reasons_for(receipt):
    reasons = set()
    samples = (receipt.get("samples") or {}).get("unknown", [])
    for sample in samples[:10]:
        proof = sample.get("package_check") or {}
        conditions = proof.get("unresolved_conditions") or []
        if not conditions and proof.get("version_checked") is False:
            reasons.add("The vendor rule supplies no affected/fixed version boundary.")
        for condition in conditions[:16]:
            # Fixed labels only: do not echo arbitrary vendor text or CVE identities.
            if condition == "Host architecture is not reported":
                reasons.add("Host architecture is missing; check OS metadata in the client report.")
            elif condition.startswith("Unsupported package condition:"):
                field = condition.split(":", 1)[1].strip()
                labels = {
                    "signature_keyid": "Package-signature identity required by the vendor rule is not supported by the evaluator.",
                    "signaturekeyid": "Package-signature identity required by the vendor rule is not supported by the evaluator.",
                    "modularitylabel": "The RPM module label required by the vendor rule is not supported by the evaluator.",
                }
                reasons.add(
                    labels.get(field, "A required package property is not supported by the evaluator.")
                )
            elif "architecture" in condition:
                reasons.add("The vendor architecture constraint is not supported by the evaluator.")
            elif "variable" in condition:
                reasons.add("The vendor rule uses an unsupported version/architecture variable.")
            elif "object set" in condition:
                reasons.add("The vendor rule uses an unsupported inventory object set.")
            elif "OS inventory" in condition or condition.startswith("Unsupported host condition:"):
                reasons.add("The vendor rule needs host facts outside the supported inventory.")
            else:
                reasons.add("The vendor rule contains a condition unsupported by the evaluator.")
    return sorted(reasons) or [
        "The stored package proof does not specify the remaining condition. Inspect package evidence; no host change is established."
    ]


def examples(device, summary, feed):
    """At most five current scoped package examples; no findings or CVE IDs exposed."""
    if not count(summary, "uncertain") and not count(summary, "missing_source_metadata"):
        return []
    if (
        not settings.DISTRO_CVE_ENABLED
        or not feed
        or device.distro_requested
        or summary.get("generation") != str(feed.generation)
        or summary.get("evaluator_version") != distro_results.VERSION
        or AgentReport.objects.filter(device=device, status="pending").exists()
    ):
        return []
    source_missing = count(summary, "missing_source_metadata") > 0 and feed.key.startswith("debian:")
    selection = Q(distro_check__counts__unknown__gt=0)
    if source_missing:
        selection |= Q(package_source={})
    candidates = (
        device.components.filter(
            selection,
            missing_since__isnull=True,
            observed_at__gte=timezone.now() - timedelta(hours=12),
            manager__in=["dpkg", "rpm"],
            installation__asset_id=device.asset_id,
            installation__asset__source_id=device.source_id,
            installation__product__organization_id=device.organization_id,
            package_identity__distribution=device.os.get("id"),
            package_identity__release=device.os.get("version"),
        )
        .only(
            "name",
            "version",
            "package_source",
            "package_identity",
            "distro_check",
            "installation_id",
            "last_report_id",
        )
        .order_by("name", "pk")[:6]
    )
    result = []
    for component in candidates:
        receipt = component.distro_check
        if (
            receipt.get("version") != distro_results.VERSION
            or receipt.get("generation") != str(feed.generation)
            or receipt.get("input_hash") != distro_results.inputs(component, device)
        ):
            continue
        missing = source_missing and not component.package_source
        result.append(
            {
                "name": component.name,
                "version": component.version,
                "reasons": ["Source-package name/version is missing from the report."]
                if missing
                else reasons_for(receipt),
                "url": reverse("asset", args=[device.organization.slug, device.asset_id])
                + "?"
                + urlencode({"software_q": component.name})
                + "#software",
            }
        )
        if len(result) == 5:
            break
    return result
