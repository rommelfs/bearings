# Implementation backlog

Canonical issue/milestone definitions are in [backlog.json](backlog.json). GitHub publication is authorized for the public `rommelfs/bearings` repository. `uv run python scripts/sync_backlog.py` publishes missing milestones and issues idempotently by exact title, checks the expected repository identity, and updates nothing already present. The backlog is published as [4 milestones](https://github.com/rommelfs/bearings/milestones) and [17 issues](https://github.com/rommelfs/bearings/issues?q=is%3Aissue). The first slice ([#1](https://github.com/rommelfs/bearings/issues/1)) is complete; 14 issues remain open. A second publisher run created zero duplicate issues.

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
- **Complete security contact and release governance**: AGPL-3.0-or-later and public source publication are approved. Establish a verified responsible reporting destination/key and review dependency/integration notices. Operational deployment and data publication require separate authorization.

## Later: Imports and delegation

Extend without changing authoritative-source rules

- **Add organization-owned NetBox read-only sources**: Exactly one authoritative source per organization. Import directly into common model, no central duplication or bidirectional synchronization. Explicit URL approval and SSRF/credential controls.
- **Add SBOM, endpoint imports and delegated providers**: Reuse software identity boundaries and source provenance; scanner/agent/SBOM imports with isolation and explicit grants. Scanning remains separate authorization.

## Multi-instance NetBox increment

Named instances, isolated credential references, explicit read-only/read-write/disabled capability, shared tenant and dedicated ownership scopes, paginated GET-only queries and read health are implemented. This does not complete automatic inventory imports. The new milestone-1 item is defined in backlog.json; live mixed-capability validation remains in #2 and projection/reconciliation in #3/#14.

## Complete local environment

Completed in [#17](https://github.com/rommelfs/bearings/issues/17): a bundled real NetBox + Bearings lab and external-instance starter are implemented, with generated credentials, verified TLS, read-only/read-write examples, automatic job processing and retained data across mode changes. See development-stack.md. General inventory imports remain in #3/#14; live compatibility beyond the pinned bundled NetBox version remains in #2.
