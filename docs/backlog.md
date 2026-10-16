# Implementation backlog

Canonical issue/milestone definitions are in [backlog.json](backlog.json). GitHub publication is pending API access. `uv run python scripts/sync_backlog.py` publishes missing milestones and issues idempotently by exact title, checks that the target repository is private, and updates nothing already present. The first slice is delivered locally; live connection and operations items remain open.

## M1: Foundation and inventory

Complete inventory ownership and onboarding

- **Deliver first organization-to-installation slice**: Local first increment: login, memberships, operator policy, contacts/scope review, manual asset outbox, software and evidence UI/API. Validate tests and docs; track delivered status in docs/validation.md.
- **Validate central NetBox against an isolated live tenant**: Provision filterable bearings_id custom fields, least-privilege credentials and tenant/site/type/role defaults. Verify devices and VMs, lost-POST recovery, field permissions and tested release. No production inventory.
- **Implement complete NetBox source refresh and reconciliation**: Paginate safely, retain data on auth/partial failures, expose stale thresholds and source links, stage disappearances for explicit review. Test idempotency, concurrency and tenant isolation.
- **Harden operator-assisted onboarding and product normalization**: Account/membership lifecycle, contact validation and history, explicit product identity normalization, network/service inventory topology, database tenant integrity, source binding migration controls.

## M2: Correlation

Add evidence-backed intelligence without unsafe inference

- **Validate live Vulnerability-Lookup and canonical aliases**: Enable approved egress, exercise real API and persisted CVE evidence, record deployed version. Add aliases and immutable source record revisions, source-specific schema adapters and freshness health.
- **Implement explicit product/version applicability**: Use supported structured source capabilities; preserve unknown versions, vendor fixes, backports and configuration requirements. Keep severity, EPSS, catalog membership, exploitation sightings and applicability distinct.
- **Implement MISP ingestion with redistribution policy**: Inspect selected release API, paginate/retry safely, preserve event/object roles and markings. Enforce distribution, sharing groups and operator policy for raw and derived data. Test default-deny behavior and common origins.
- **Implement Plum Island historical observation adapter**: Verify authentication/permissions/schema and InfoIP time/404/empty semantics. Preserve tcp/udp, report-level tags, hostname context and uncertainty. Investigate network/domain export; never enumerate large ranges blindly or launch scans.
- **Generalize observations, relationships and explained priorities**: Keep categories and assessment dimensions distinct. Match historical/shared claims, preserve rule versions, observation/ingestion/evaluation times, evidence provenance and independent origins.

## M3: Operational workflow

Prepare controlled operational use

- **Deliver controlled notification and escalation workflow**: Keep development sink; require operational authorization for production transport. Add delivery failure state, reminder escalation, deduplication, handling policy and audited preparation history.
- **Complete organization remediation and CIRCL triage**: Review filters, acknowledgment/corrections, assignment, urgency summaries and freshness coverage. Test all counts/exports/notifications against visibility restrictions.
- **Security and recovery gate before deployment**: SSO/MFA, rate limits, source approval/egress enforcement, DB row-level integrity, least privilege, audit export, retention and PostgreSQL recovery drill. Approve WSGI/TLS configuration and production scheduler.
- **Resolve licensing, security contact and release governance**: Owner decision on license, verified responsible reporting destination/key, dependency and integration license review, repository visibility and release approval. No license invention or public release by default.

## Later: Imports and delegation

Extend without changing authoritative-source rules

- **Add organization-owned NetBox read-only sources**: Exactly one authoritative source per organization. Import directly into common model, no central duplication or bidirectional synchronization. Explicit URL approval and SSRF/credential controls.
- **Add SBOM, endpoint imports and delegated providers**: Reuse software identity boundaries and source provenance; scanner/agent/SBOM imports with isolation and explicit grants. Scanning remains separate authorization.
