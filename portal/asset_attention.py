"""Presentation of update evidence and vulnerability reviews for a single asset."""

from django.conf import settings
from django.db.models import Count, F, Q

from .agents import current
from .distro_fix_evidence import HasVendorFix
from .presentation import ACTIVE_REVIEWS
from .review_queue import classified

MACHINE_KINDS = {"server", "vm", "desktop", "laptop", "appliance"}


def attention_for(asset, device, findings, windows_update):
    if not device and asset.kind not in MACHINE_KINDS:
        return {}
    reviews = findings.order_by()
    active = Q(status__in=ACTIVE_REVIEWS) & ~Q(analyst_applicability="not_affected")
    saved = Q(
        status__in=[*ACTIVE_REVIEWS, "accepted_risk"],
        analyst_applicability="affected",
    )
    windows = bool(device and device.os.get("id") == "windows")
    counts = {
        "total": Count("pk"),
        "open": Count("pk", filter=active),
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
        affected = (
            Q(distro_match__component__device_id=device.pk)
            & Q(package_current=True, distro_match__queue_proof__verdict="affected")
            & ~Q(analyst_applicability="not_affected")
            & Q(status__in=[*ACTIVE_REVIEWS, "accepted_risk"])
        )
        reviews = classified(reviews).annotate(vendor_fix=HasVendorFix(F("distro_match__snapshot")))
        counts.update(
            version_matches=Count("pk", filter=affected),
            fixes=Count("installation_id", filter=affected & Q(vendor_fix=True), distinct=True),
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
            "attention": True,
        }
    else:
        updates = {
            "label": "Update backlog unknown",
            "detail": "Repository update availability has not been checked.",
        }
    return {
        "updates": updates,
        "updates_href": "#windows-update" if windows else "#software",
        "reviews": result,
        "has_reviews": bool(result["open"] or result["saved"] or result.get("version_matches")),
    }
