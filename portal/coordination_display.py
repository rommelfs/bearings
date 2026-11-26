"""Bounded current-policy examples; counts and saved assessments remain independent."""

from django.db.models import Case, F, IntegerField, Value, When, Window
from django.db.models.functions import RowNumber
from .distro_verdicts import decorate_package_verdict
from .presentation import vulnerability_summary
from .review_queue import classified


def decorate(user, rows, *, prepared=False):
    from .circl import findings_for, outstanding

    by_id = {r["record__external_id"]: r for r in rows}
    for row in rows:
        row["coordination"] = row["companies"] > 1 and row["affected"] > 0
        row["examples"] = []
    if not rows:
        return
    candidates = outstanding(findings_for(user))
    if prepared:
        # Examples must describe the same clean subset as the prepared counters.
        candidates = candidates.filter(organization__national_state__dirty=False)
    # Two concrete installations per advisory, in one query, regardless of fleet size.
    selected = (
        candidates.filter(record__external_id__in=by_id)
        .annotate(
            example_position=Window(
                RowNumber(),
                partition_by=[F("record__external_id")],
                order_by=[
                    Case(
                        When(analyst_applicability="affected", then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    ).asc(),
                    F("organization_id").asc(),
                    F("pk").asc(),
                ],
            )
        )
        .filter(example_position__lte=2)
        .order_by("record__external_id", "example_position")
        .values_list("pk", flat=True)
    )
    ids = list(selected)
    examples = {
        finding.pk: finding
        for finding in classified(candidates.filter(pk__in=ids))
        .select_related(
            "organization",
            "record",
            "installation__product",
            "installation__asset",
            "distro_match__component__device",
            "distro_match__advisory__feed",
        )
        .defer(
            "installation__asset__upstream_data",
            "distro_match__advisory__criteria",
            "distro_match__component__binary",
            "distro_match__component__device__reported_network",
            "distro_match__component__device__services",
        )
    }
    for pk in ids:
        finding = examples.get(pk)
        if finding is None:
            continue
        row = by_id[finding.record.external_id]
        summary = vulnerability_summary(finding.record.payload)
        description = summary["description"] or (
            summary["title"] if summary["title"] != "Vulnerability review" else ""
        )
        finding.coordination_description = description[:240]
        decorate_package_verdict(finding)
        verdict = finding.package_verdict
        if verdict and verdict["current"]:
            state = verdict.get("verdict")
            if state == "affected":
                finding.next_step = "Check vendor fix and repository availability; plan remediation."
            elif state in {"fixed", "not_matched"}:
                finding.next_step = "Reconcile the retained review with this package result."
            else:
                finding.next_step = "Inspect the unsupported or missing conditions in the evidence."
        elif verdict:
            finding.next_step = "Refresh inventory and vendor evaluation before deciding on remediation."
        elif finding.queue_bucket == "cleared":
            finding.next_step = "Review retained evidence and the saved assessment."
        else:
            finding.next_step = (
                "Verify this installed version against the advisory's affected-version conditions."
            )
        if finding.analyst_applicability == "affected" and not verdict:
            finding.next_step = "Review remediation with the responsible company."
        if finding.status == "accepted_risk":
            finding.next_step = "Review the recorded risk acceptance and its conditions."
        row["examples"].append(finding)
