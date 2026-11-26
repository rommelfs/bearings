"""Presentation of update evidence and vulnerability reviews for a single asset."""

from django.conf import settings
from django.db.models import Count, F, Q

from .agents import current
from .distro_fix_evidence import HasVendorFix
from .presentation import ACTIVE_REVIEWS
from .review_queue import classified
from .review_focus import machine_coverage
from .review_update_preview import asset_fix_preview
from .review_work import (
    CONFLICTING,
    CURRENT_AFFECTED,
    NEEDS_ATTENTION,
    positive_package_coverage,
    verified_fix_progress,
)

MACHINE_KINDS = {"server", "vm", "desktop", "laptop", "appliance"}


def attention_for(user, asset, device, findings, windows_update):
    if not device and asset.kind not in MACHINE_KINDS:
        return {}
    findings = classified(findings, assets=[asset.pk])
    reviews = findings.order_by()
    saved = Q(
        status__in=[*ACTIVE_REVIEWS, "accepted_risk"],
        analyst_applicability="affected",
    )
    windows = bool(device and device.os.get("id") == "windows")
    counts = {
        "total": Count("pk"),
        "open": Count("pk", filter=NEEDS_ATTENTION),
        "saved": Count("pk", filter=saved),
    }
    linux_evaluable = (
        device
        and not windows
        and settings.DISTRO_CVE_ENABLED
        and device.distro_summary.get("state") in ("ready", "partial")
        and not device.stale
        and device.distro_checked_at
        and device.distro_checked_at >= device.last_observed_at
        and current(device)
    )
    if linux_evaluable:
        affected = Q(distro_match__component__device_id=device.pk) & CURRENT_AFFECTED
        reviews = reviews.annotate(vendor_fix=HasVendorFix(F("distro_match__vendor_fix_inputs")))
        counts.update(
            version_matches=Count("installation_id", filter=affected, distinct=True),
            conflicts=Count("pk", filter=affected & CONFLICTING),
            fixes=Count("installation_id", filter=affected & Q(vendor_fix=True), distinct=True),
            fixed_evidence=Count("pk", filter=Q(distro_match__queue_proof__verdict="fixed")),
        )
    result = reviews.aggregate(**counts)
    if windows:
        updates = windows_update.get("backlog") or {
            "label": "Windows update backlog unknown",
            "detail": "Windows Update observation unavailable.",
        }
    elif result.get("fixes"):
        count = result["fixes"]
        updates = {
            "label": f"{count} package" + ("s" if count != 1 else "") + " with documented vendor fixes",
            "detail": "Repository update availability has not been checked.",
            "targets": asset_fix_preview(findings.filter(distro_match__component__device_id=device.pk)),
            "attention": True,
        }
    else:
        updates = {
            "label": "Update backlog unknown",
            "detail": "Repository update availability has not been checked.",
        }
    has_reviews = bool(result["open"] or result["saved"] or result.get("version_matches"))
    clear = False
    progress = 0
    if linux_evaluable:
        if result["fixed_evidence"]:
            progress = verified_fix_progress(findings.filter(distro_match__component__device_id=device.pk))
        if not has_reviews and positive_package_coverage(device.distro_summary, True):
            machines, _ = machine_coverage(user, [asset.organization_id])
            clear = machines.filter(pk=asset.pk, evaluated=True, partial=False).exists()
    return {
        "updates": updates,
        "updates_href": "#windows-update" if windows else "#software",
        "reviews": result,
        "has_reviews": has_reviews,
        "clear": clear,
        "checked_packages": device.distro_summary.get("packages") if clear else None,
        "progress": progress,
    }
