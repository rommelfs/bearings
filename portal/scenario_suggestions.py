"""Explained local scenario drafts and bounded public-catalog recommendations.

Drafts are hypotheses, never automatic company risk scores or proof of applicability.
"""

import re
from django.db.models import Q
from .intelligence import digest
from .issues import data_for
from .models import MOSPRisk
from .presentation import vulnerability_summary

RULE = "asset-evidence-scenario/v1"
PROFILES = {
    "execution": (
        "Unauthorized code execution",
        "If this installation and configuration are affected and exploitable, an attacker could execute code with service privileges, altering data or interrupting the service.",
        "Check the exact build, vendor fixes and exposure; test and install the applicable update or mitigation.",
        ["malware infection", "unauthorized access", "unauthorised access"],
    ),
    "data": (
        "Unauthorized access to or alteration of data",
        "If the documented weakness applies, unauthorized queries, scripts or access could disclose or alter data. Scope and business consequences require review.",
        "Validate affectedness, access controls and vendor guidance; apply and verify the relevant fix.",
        ["unauthorized access", "unauthorised access", "disclosure", "data modification"],
    ),
    "availability": (
        "Interruption of the hosted service",
        "If the documented denial-of-service condition applies and can be triggered, the hosted service could become unavailable. Duration and business impact are unassessed.",
        "Validate affectedness and recovery controls; test the vendor fix or an appropriate mitigation.",
        ["unavailability", "denial of service", "saturation"],
    ),
    "vulnerability": (
        "Service or data impact from a software vulnerability",
        "If the recorded vulnerability affects this exact installation and is exploitable, the service or its data could be affected. The available evidence does not yet establish a specific attack outcome.",
        "Review source evidence, exact version/build and vendor fixes before choosing remediation.",
        ["unavailability"],
    ),
    "support": (
        "Loss of security maintenance or support continuity",
        "If the recorded support/lifecycle evidence applies to this installation or entitlement, unresolved defects or incidents could take longer to remedy and service disruption could persist.",
        "Validate the lifecycle date and local entitlement; plan an upgrade, replacement or support renewal and test recovery.",
        ["unavailability", "maintenance", "malware infection"],
    ),
    "exposure": (
        "Unexpected access through a reachable service",
        "If the recorded service is unintentionally reachable and the observed scope still applies, unauthorized access or service disruption may be possible. A port observation does not establish exploitation or compromise.",
        "Verify the current network observation and intended exposure; restrict unnecessary access and review the actual service/version.",
        ["unauthorized access", "unauthorised access", "unavailability"],
    ),
    "entitlement": (
        "Loss of entitlement or delayed service recovery",
        "If the recorded contract or entitlement issue applies, use of the service or timely repair/recovery could be impaired. Vendor lifecycle facts alone do not establish local contract coverage.",
        "Verify the contract, expiry and local entitlement; arrange renewal, replacement or an alternative recovery path.",
        ["unavailability", "maintenance"],
    ),
    "other": (
        "Operational consequences of the recorded asset issue",
        "If the recorded issue is confirmed in the company context, operation of this asset or its service may be affected. Consequences and likelihood require assessment.",
        "Validate the evidence, identify the business service and record an owner, controls and next action.",
        ["unavailability"],
    ),
}


def draft_scenario(issue):
    profile = (
        "support"
        if issue.kind in {"eol", "support"}
        else "entitlement"
        if issue.kind in {"license", "warranty", "maintenance"}
        else issue.kind
        if issue.kind in {"exposure", "vulnerability"}
        else "other"
    )
    basis = f"Recorded {issue.get_kind_display().lower()} issue"
    summary = {}
    if issue.finding_id:
        finding = issue.finding
        summary = vulnerability_summary(finding.record.payload)
        payload = finding.record.payload
        containers = payload.get("containers", {}) if isinstance(payload, dict) else {}
        cna = containers.get("cna", {}) if isinstance(containers, dict) else {}
        cwes = set()
        types = cna.get("problemTypes", []) if isinstance(cna, dict) else []
        if isinstance(types, list):
            for item in types[:50]:
                descriptions = item.get("descriptions", []) if isinstance(item, dict) else []
                if isinstance(descriptions, list):
                    for entry in descriptions[:50]:
                        if isinstance(entry, dict):
                            cwes.update(
                                re.findall(
                                    r"\bCWE-\d+\b",
                                    str(entry.get("cweId", ""))[:100]
                                    + " "
                                    + str(entry.get("description", ""))[:500],
                                )
                            )
        text = (summary.get("title", "") + " " + summary.get("description", "")).casefold()
        if cwes & {"CWE-78", "CWE-94", "CWE-95", "CWE-502"} or any(
            term in text
            for term in ["remote code execution", "arbitrary code execution", "command injection"]
        ):
            profile = "execution"
        elif cwes & {"CWE-79", "CWE-89", "CWE-200", "CWE-287", "CWE-862"} or any(
            term in text for term in ["sql injection", "authentication bypass", "information disclosure"]
        ):
            profile = "data"
        elif (
            cwes & {"CWE-400", "CWE-476", "CWE-770"}
            or "denial of service" in text
            or "denial-of-service" in text
        ):
            profile = "availability"
        basis = f"{finding.record.external_id} on {finding.installation.product.name} (recorded version {finding.installation.version or 'unknown'}, build {finding.installation.build or 'unknown'}): source weakness {', '.join(sorted(cwes)) or 'not supplied'}; analyst applicability {finding.analyst_applicability}, workflow {finding.status}"
    title, consequence, action, terms = PROFILES[profile]
    assumptions = "Affectedness, reachable attack paths, business impact and control effectiveness must be verified. A catalog's organizational weakness is a hypothesis; this issue alone does not establish flawed company processes. No exploitation or compromise is asserted."
    if issue.finding_id and (
        issue.finding.analyst_applicability == "not_affected"
        or issue.finding.status in {"resolved", "false_positive"}
    ):
        assumptions = (
            "The recorded review is not affected or closed. Reconcile that decision before treating this hypothetical scenario as actionable. "
            + assumptions
        )
    result = {
        "title": title,
        "profile": profile,
        "consequence": consequence,
        "next_action": action,
        "basis": basis,
        "assumptions": assumptions,
        "rule": RULE,
        "terms": terms,
    }
    result["reason"] = (
        f"Automatic scenario draft ({RULE}): {title}. Basis: {basis}. {consequence} {assumptions}"
    )
    result["fingerprint"] = digest(
        {
            "rule": RULE,
            "issue": data_for(issue),
            "asset_kind": issue.asset.kind,
            "criticality": issue.asset.criticality,
            "evidence": digest(issue.finding.record.payload) if issue.finding_id else issue.evidence_text,
            "version": [
                issue.finding.installation.version,
                issue.finding.installation.build,
                issue.finding.installation.edition,
            ]
            if issue.finding_id
            else None,
            "assessment": [issue.finding.analyst_applicability, issue.finding.status]
            if issue.finding_id
            else None,
            "product": [
                issue.finding.installation.product.name,
                issue.finding.installation.product.identifier,
            ]
            if issue.finding_id
            else None,
        }
    )
    return result


def catalog_suggestions(issue, draft=None):
    draft = draft or draft_scenario(issue)
    asset_names = {
        "server": ["Server"],
        "vm": ["Server"],
        "desktop": ["Desktop computer"],
        "laptop": ["Laptop computer", "Desktop computer"],
        "appliance": ["Firewall", "Router", "Switch"],
    }.get(issue.asset.kind, [])
    if not asset_names:
        return []
    asset_query = Q(pk__in=[])
    for name in asset_names:
        asset_query |= Q(description__icontains=f"Asset: {name}.")
    threat_query = Q(pk__in=[])
    for term in draft["terms"]:
        threat_query |= Q(description__icontains=term)
    risks = (
        MOSPRisk.objects.filter(
            source__enabled=True,
            source__publisher="MONARC",
            source__language="EN",
            missing_since__isnull=True,
        )
        .filter(asset_query, threat_query)
        .select_related("source", "current_revision")
        .order_by("pk")[:200]
    )
    if issue.finding_id:
        withdrawn = set(
            issue.finding.risk_links.filter(
                withdrawn_at__isnull=False,
                evidence_revision__content_hash=digest(issue.finding.record.payload),
            ).values_list("risk_revision__risk_id", flat=True)
        )
    else:
        withdrawn = set(
            issue.risk_scenarios.filter(
                withdrawn_at__isnull=False, issue_revision__snapshot=data_for(issue)
            ).values_list("risk_revision__risk_id", flat=True)
        )
    if issue.finding_id:
        linked_revisions = set(
            issue.finding.risk_links.filter(
                withdrawn_at__isnull=True,
                evidence_revision__content_hash=digest(issue.finding.record.payload),
            ).values_list("risk_revision_id", flat=True)
        )
    else:
        linked_revisions = set(
            issue.risk_scenarios.filter(
                withdrawn_at__isnull=True, issue_revision__snapshot=data_for(issue)
            ).values_list("risk_revision_id", flat=True)
        )
    ranked = []
    for risk in risks:
        payload = risk.payload
        if (
            not isinstance(payload, dict)
            or payload.get("fixture")
            or risk.current_revision_id
            and risk.current_revision.payload.get("fixture")
            or payload.get("publisher") != "MONARC"
            or payload.get("licenses") != ["CC0-1.0"]
            or risk.pk in withdrawn
        ):
            continue
        label = risk.description.casefold()
        matching = [term for term in draft["terms"] if term in label]
        score = len(matching) * 10 + int(
            any(term in label for term in ["patches", "maintenance", "update management"])
        )
        ranked.append(
            {
                "risk": risk,
                "score": score,
                "why": f"Catalog asset type matches {issue.asset.get_kind_display()}; draft topic matches {', '.join(matching)}. Organizational weakness and company relevance remain unverified.",
                "linked": risk.current_revision_id in linked_revisions
                and risk.current_revision.risk_hash == risk.content_hash,
            }
        )
    return sorted(ranked, key=lambda candidate: (-candidate["score"], candidate["risk"].pk))[:3]
