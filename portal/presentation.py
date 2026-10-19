"""Bounded source facts for review; no product matching, risk score or exploitation inference."""

import math

ACTIVE_REVIEWS = ["new", "under_review", "confirmed"]


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
    metrics = cna.get("metrics")
    if not isinstance(metrics, list):
        return result
    for metric in metrics[:50]:
        if not isinstance(metric, dict):
            continue
        for key, version in [("cvssV4_0", "4.0"), ("cvssV3_1", "3.1"), ("cvssV3_0", "3.0")]:
            value = metric.get(key)
            if not isinstance(value, dict) or value.get("version") != version:
                continue
            score = value.get("baseScore")
            if type(score) not in {int, float} or not 0 <= score <= 10 or not math.isfinite(score):
                continue
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
            result.update(score=score, severity=severity, cvss_version=version)
            return result
    return result


def decorate_finding(finding):
    finding.source_summary = vulnerability_summary(finding.record.payload)
    return finding
