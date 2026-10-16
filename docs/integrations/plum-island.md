# Plum Island

Status: **contract researched, adapter not implemented or connected**. Reference inspected 2026-10-16: [official search documentation](https://github.com/D4-project/Plum-Island/blob/main/documentation/search.md). No deployed release is certified. Verify authentication transport and selected instance permissions/schema before enabling a connector.

Documented endpoint: `GET /api/v1/infoip/<ip>`, individual public IPv4/IPv6 only; CIDR returns 400. Protected permission is `can_get` on `InfoIpApi`; the documented Read Only role gains it after role synchronization. Authentication mechanism has not yet been verified from source/runtime and is not guessed here.

Default rolling window is 30 days. Use `days` or both `start` and `stop`, not both approaches. Dates are UTC; aware ISO datetimes work. Earliest start is two calendar years back, future stop rejected. Selection uses report `last_seen` within the window; returned `first_seen` may precede it. First/last are not evidence of continuous availability. These are historical observations, not present open-port claims.

404 means never indexed; a known address with no matching-window observations returns empty `ports`. Preserve this distinction. Entries include port, protocol (tcp/udp, possibly null for historical incomplete indexes), tags and first/last timestamps. TCP and UDP on one port are distinct. Tags co-occur at report level and may not identify that port's service. Preserve requested hostname and virtual-host context where available.

Do not blindly enumerate address ranges around a per-IP API. Investigate supported query/export interfaces for networks/domains, including the documented `net:` and `fqdn_requested` search fields. Observation ingestion must preserve provenance, requested window, uncertainty, permission and ingestion/evaluation time. Exposure and inventory discrepancy findings prompt review; tags must never establish vulnerability applicability. No scan is authorized or launched by registering scope or connecting inventory.
