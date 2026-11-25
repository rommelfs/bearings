"""Bounded display of current package remediation evidence from authorized findings."""

from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber

from .distro_fix_evidence import HasVendorFix
from .distro_verdicts import vendor_fix_targets
from .review_queue import classified

TARGET_PREVIEW_LIMIT = 3
FIX_PROOF = "distro_match__vendor_fix_inputs"
FIX_FEED = "distro_match__queue_proof__feed"
FIX_FIELDS = ("installation__product__name", FIX_PROOF, FIX_FEED)


def fix_targets(row):
    payload = row[FIX_PROOF] or {}
    return vendor_fix_targets(payload.get("package_check") or {}, row[FIX_FEED] or "")


def _current_fix_rows(findings):
    return (
        classified(findings)
        .filter(package_current=True, distro_match__queue_proof__verdict="affected")
        .alias(has_vendor_fix=HasVendorFix(F(FIX_PROOF)))
        .filter(has_vendor_fix=True)
        .order_by("installation__product__name", "pk")
    )


def _preview(records):
    rows = []
    for record in records:
        for target in fix_targets(record):
            row = {"software": record["installation__product__name"], **target}
            if row not in rows:
                rows.append(row)
                if len(rows) == TARGET_PREVIEW_LIMIT:
                    return rows
    return rows


def asset_fix_preview(findings):
    return _preview(_current_fix_rows(findings).values(*FIX_FIELDS)[:TARGET_PREVIEW_LIMIT])


def add_case_fix_previews(findings, page):
    if not page:
        return
    keys = {(finding.installation.asset_id, finding.case_identifier): finding for finding in page}
    scope = Q(
        *(Q(installation__asset_id=asset, case_identifier=identifier) for asset, identifier in keys),
        _connector=Q.OR,
    )
    rows = (
        _current_fix_rows(findings.filter(scope))
        .alias(
            fix_row=Window(
                expression=RowNumber(),
                partition_by=[F("installation__asset_id"), F("case_identifier")],
                order_by=[F("installation__product__name").asc(), F("pk").asc()],
            )
        )
        .filter(fix_row__lte=TARGET_PREVIEW_LIMIT)
        .values("installation__asset_id", "case_identifier", *FIX_FIELDS)
    )
    previews = {}
    for row in rows:
        key = (row["installation__asset_id"], row["case_identifier"])
        previews.setdefault(key, []).append(row)
    for key, finding in keys.items():
        finding.update_preview = _preview(previews.get(key, ()))
