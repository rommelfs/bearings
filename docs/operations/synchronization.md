# NetBox inventory synchronization

Bearings imports devices, VMs, IP addresses and prefixes from each operator-approved source into its organization-scoped Asset inventory. The same GET-only importer supports central and organization-owned NetBox, read-only and read/write connections. It never copies inventory from one NetBox into another. Each organization has one authoritative source.

## Running and scheduling

The complete Docker starter automatically calls `sync_netbox --all --due` after processing due writes. Sources default to a 15-minute interval. Operators can pause periodic import or change the interval (at least one minute) in InventorySource administration. A failed attempt is also throttled by that interval. Disabled instances are skipped by the scheduler; explicit operator imports fail with visible health rather than reaching them.

```sh
python3 scripts/dev.py manage sync_netbox --all
python3 scripts/dev.py manage sync_netbox --source <source-uuid>
```

Without Docker, use `DJANGO_DEBUG=1 uv run python manage.py sync_netbox --all`; invoke `sync_netbox --all --due` periodically alongside `process_jobs`. These are single-pass commands, not installed operating-system schedulers. SQLite requires a single worker; PostgreSQL is required for concurrent workers. An organization administrator/editor can queue **Refresh inventory** in the portal, including when automatic import is paused. The web request never performs connector HTTP. The worker must be running to consume that request.

A failed source does not stop other selected sources. Manual CLI imports exit nonzero on any failure; due worker failures are recorded and later iterations continue. The local development loop is not a monitored production scheduler. Imports hold a source lock during bounded HTTP and projection work, so a slow source can delay its writes; its failure never turns into inventory deletion.

## Atomic projection and identity

All four types and every page must validate before projection changes commit. The existing adapter reconstructs scoped pagination, rejects wrong tenants, duplicate IDs, changed counts, partial responses and unapproved destinations. Boundaries remain 100 pages / 10,000 objects per type, 2 MB per response and 15-second HTTP timeouts. Larger or incompatible scopes fail closed instead of silently truncating; subdivide approved sources or extend the contract explicitly. A complete traversal is not an atomic upstream snapshot: concurrent edits that preserve counts can still move objects between reads.

Identity is source binding UUID, canonical NetBox object type and external ID. Equal IDs in different instances or types are distinct; addresses and names are not identities. IP/VRF overlap does not imply ownership. The importer does not create infrastructure authority claims or infer software, applicability or compromise from network inventory.

NetBox owns the name/address/prefix and a small allowlisted metadata projection: status, site/role/type/cluster/VRF references and primary IPs where present. Raw custom fields, arbitrary payloads and upstream-provided URLs are not exposed. Source links are constructed from the optional operator-approved HTTPS browser base (otherwise the API base) and validated identity, never a response URL. API credentials are never sent to the browser-only address. Local kind refinements, criticality, lifecycle, responsible team, installations, findings and analyst assessments survive refresh. NetBox status is displayed separately from local lifecycle. Devices and VMs default to server/vm; network objects use ip_address/prefix kinds and cannot be submitted through the create/recovery write adapter. Interfaces, service topology, automatic platform/OS/product mapping and historical upstream revisions are not implemented.

PostgreSQL imports take a source lock before updating assets/jobs, as do outgoing write workers. A matching same-source bearings_id on a confirmed device/VM may complete a pending write acknowledgement before its retry. Conflicting identities discard the import; foreign-organization markers never reassign local assets. No importer request is a POST, PATCH or DELETE.

## Health, absence and review

Last query success records only the types requested by `query_netbox`; it does not import. Last write success is a write acknowledgement. Last import success means a complete validated four-type traversal committed. Failed imports retain projections, last success and last successful summary, recording a separate safe import error/attempt. No raw response or secret-bearing exception is stored in health. Freshness becomes stale when no successful import exists or more than twice the configured interval has elapsed. An error remains visible even within that freshness window.

A confirmed external identity absent from a complete traversal receives `missing_since`. Pending submissions without a confirmed identity are not disappearance candidates. Missing objects retain all local data and may reflect deletion, tenant reassignment or reduced upstream permissions. An empty but complete result can mark candidates; errors/partial pages cannot. An editor can record a reasoned review without deleting or retiring the object. Reappearance clears the current missing/review marker and retains its stable local identity; audit events preserve review history. No automatic deletion occurs.

The workspace shows attempts, last complete import, interval/pause/queue state, errors and snapshot counts, plus per-object source links and missing reviews. Inventory HTML pages contain 50 assets; `/api/v1/organizations/<slug>/inventory/?page=N` returns 100 assets with page/pages/count metadata and the same authorization checks on every page. Consumers must follow all pages. Restricted organizations remain invisible to unauthorized users and CIRCL analysts without explicit visibility.

## Development validation

`python3 scripts/dev.py smoke` is restricted to the bundled synthetic lab. It creates one device directly in NetBox without a seed identity, verifies import/update and local assessment preservation, deletes only that newly created probe in NetBox, and verifies retained local missing state. It also validates read-only import and existing write/recovery behavior. This controlled upstream deletion is a smoke fixture action, never importer behavior. See `docs/validation.md` for actual results and deployed versions.
