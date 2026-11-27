"""Bounded source facts for review; no product matching, risk score or exploitation inference."""

import math

ACTIVE_REVIEWS = ["new", "under_review", "confirmed"]
SEVERITY_ORDER = ["critical", "high", "medium", "low", "none", "unknown"]


def severity_rank(field):
    from django.db.models import Case, IntegerField, Value, When

    return Case(
        *[When(**{field: key}, then=Value(i)) for i, key in enumerate(SEVERITY_ORDER)],
        default=Value(len(SEVERITY_ORDER)),
        output_field=IntegerField(),
    )


def severity_first(findings):
    """Order the authorized query before pagination; unknown severity always follows known values."""
    return findings.annotate(source_severity_order=severity_rank("record__source_severity")).order_by(
        "source_severity_order", "-evaluated_at", "pk"
    )


def vulnerability_summary(payload):
    result = {
        "title": "Vulnerability review",
        "description": "",
        "severity": "Unknown",
        "score": None,
        "cvss_version": "",
    }
    if not isinstance(payload, dict):
        return result
    containers = payload.get("containers")
    cna = containers.get("cna") if isinstance(containers, dict) else None
    if not isinstance(cna, dict):
        return result
    title = cna.get("title")
    if isinstance(title, str) and title.strip():
        result["title"] = title[:300]
    descriptions = cna.get("descriptions")
    if isinstance(descriptions, list):
        for item in descriptions[:50]:
            if isinstance(item, dict) and str(item.get("lang", "")).lower().startswith("en"):
                if isinstance(item.get("value"), str):
                    result["description"] = item["value"][:1500]
                    break
    distro = payload.get("bearings_distro", {})
    if (
        isinstance(distro, dict)
        and distro.get("schema") == "bearings.distro-oval.v1"
        and (
            distro.get("severity") in {"critical", "high", "medium", "low", "none"}
            or (distro.get("severity") == "negligible" and str(distro.get("feed", "")).startswith("ubuntu:"))
        )
    ):
        result["severity"] = distro["severity"].title()
        result["vendor_priority"] = True
        feed = str(distro.get("feed", "")).split(":", 1)[0]
        result["priority_source"] = {"ubuntu": "Ubuntu", "debian": "Debian", "rhel": "Red Hat"}.get(
            feed, "Vendor"
        )
    score, version = cvss_rating_v1(cna)
    if score is not None:
        severity = (
            "Critical"
            if score >= 9
            else "High"
            if score >= 7
            else "Medium"
            if score >= 4
            else "Low"
            if score > 0
            else "None"
        )
        result.update(score=score, cvss_version=version, score_severity=severity, score_key=severity.lower())
        if not result.get("vendor_priority"):
            result["severity"] = severity
    return result


def cvss_rating_v1(cna):
    metrics = cna.get("metrics")
    if not isinstance(metrics, list):
        return None, ""
    for metric in metrics[:50]:
        if not isinstance(metric, dict):
            continue
        for key, version in [("cvssV4_0", "4.0"), ("cvssV3_1", "3.1"), ("cvssV3_0", "3.0")]:
            value = metric.get(key)
            if not isinstance(value, dict) or value.get("version") != version:
                continue
            score = value.get("baseScore")
            if type(score) in {int, float} and 0 <= score <= 10 and math.isfinite(score):
                return score, version
    return None, ""


def decorate_finding(finding):
    from .asset_context import asset_context

    finding.source_summary = vulnerability_summary(finding.record.payload)
    finding.severity_key = finding.source_summary["severity"].lower()
    finding.assessment_key = (
        finding.analyst_applicability
        if finding.analyst_applicability in {"affected", "potential", "not_affected"}
        else "unknown"
    )
    finding.asset_context = asset_context(finding.installation.asset, workspace=True, case_id=finding.pk)
    return finding
