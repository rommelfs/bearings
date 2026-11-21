"""Read-only presentation of independent host, client and export stages; no network calls."""

from django.utils import timezone


def synchronization_status(asset, device):
    source = asset.source
    connected = source.mode in {"central", "external"} and bool(source.instance_id)
    host = {
        "label": "No NetBox connection",
        "detail": "This inventory is maintained in Bearings.",
        "tone": "neutral",
    }
    if connected:
        if not source.instance.enabled:
            host = {
                "label": "Connection disabled",
                "detail": "The NetBox connection is disabled by the operator.",
                "tone": "warning",
            }
        elif asset.external_id and asset.state == "synced":
            host = {
                "label": "Host linked",
                "detail": "The host identity is confirmed. Software and IP export have their own status below.",
                "tone": "good",
            }
        else:
            host = {
                "label": "Host not confirmed",
                "detail": "Host registration or reconciliation is required before inventory export.",
                "tone": "warning",
            }
    client = {
        "label": "No client linked",
        "detail": "Inventory can also come from NetBox or manual entries.",
        "tone": "neutral",
    }
    valid_device = bool(
        device and device.source_id == source.pk and device.organization_id == asset.organization_id
    )
    active = valid_device and device.enabled and device.expires_at > timezone.now()
    if device:
        if not valid_device:
            client = {
                "label": "Client binding needs review",
                "detail": "The client must belong to this host's company and inventory source.",
                "tone": "warning",
            }
        elif not active:
            client = {
                "label": "Client inactive",
                "detail": "The client credential is revoked or expired.",
                "tone": "warning",
            }
        elif not device.last_observed_at:
            client = {
                "label": "Waiting for first report",
                "detail": "Registration is complete; no software report has been processed yet.",
                "tone": "pending",
            }
        elif device.stale:
            client = {
                "label": "Reports outdated",
                "detail": "The last processed observation is more than 12 hours old.",
                "tone": "warning",
            }
        else:
            client = {
                "label": "Reports received",
                "detail": "Software observations are available. CVE matching coverage is shown with the software.",
                "tone": "good",
            }
    export = {
        "label": "Not configured",
        "detail": "A writable NetBox connection and an explicit export policy are required.",
        "tone": "neutral",
    }
    receipt = device.netbox_export_receipt if valid_device else {}
    if connected:
        if not source.instance.enabled:
            export = {
                "label": "Connection disabled",
                "detail": "New exports are blocked. Earlier confirmed exports are retained.",
                "tone": "warning",
            }
        elif source.instance.access_mode != "read_write":
            export = {
                "label": "Read-only connection",
                "detail": "Bearings imports inventory; client data is not written back to this connection.",
                "tone": "neutral",
            }
        elif not source.agent_export_policy or not source.agent_managed:
            export = {
                "label": "Not activated",
                "detail": "Client reports stay in Bearings until the platform operator enables NetBox inventory export.",
                "tone": "warning",
            }
        elif not active:
            export = {
                "label": "Active client required",
                "detail": "A current client binding is needed to export observations.",
                "tone": "pending",
            }
        elif device.netbox_export_error:
            export = {
                "label": "Export needs attention",
                "detail": device.netbox_export_error,
                "tone": "warning",
            }
        elif device.netbox_export_pending:
            export = {
                "label": "Export queued",
                "detail": "A background task will verify the host and synchronize the current observations.",
                "tone": "pending",
            }
        elif receipt and receipt.get("sequence") == device.applied_sequence:
            if source.agent_export_policy.get("vrf") is None:
                export = {
                    "label": "Software inventory exported",
                    "detail": "Inventory-only mode: native interfaces and IP addresses are not enabled for export.",
                    "tone": "good",
                }
            elif receipt.get("network") == "exported":
                export = {
                    "label": "Export confirmed",
                    "detail": "Software inventory and reported interface/IP data were acknowledged by NetBox. Primary IP is not set automatically.",
                    "tone": "good",
                }
            else:
                export = {
                    "label": "Software exported; network pending",
                    "detail": "No current network export is confirmed. Check the network observation age and client version.",
                    "tone": "warning",
                }
        else:
            export = {
                "label": "No confirmed export",
                "detail": "The current observations have no matching export confirmation yet.",
                "tone": "pending",
            }
    return {"host": host, "client": client, "export": export, "receipt": receipt}
