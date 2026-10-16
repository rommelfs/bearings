# Initial implementation validation

Date: 2026-10-16. All application data used here is synthetic. No production notifications, active scans, NetBox writes or public deployment occurred.

| Check | Actual outcome |
| --- | --- |
| `uv sync --frozen` | Passed, repeated without dependency/lockfile changes |
| Django migrations | Applied on SQLite and PostgreSQL 17; repeat application was a no-op |
| Django tests | **44 executed, 44 passed on SQLite; 44 executed, 44 passed on PostgreSQL**; no skips or expected failures |
| System check and migration drift | Passed; no pending model changes |
| Ruff lint and format | Passed |
| Static collection | Passed, 128 files collected |
| Real host HTTP workflow | Login, organization/CIRCL dashboards, inventory/software APIs, live CVE lookup and authorized evidence read passed with temporary synthetic accounts; accounts deleted afterward |
| Live Vulnerability-Lookup | Retrieved CVE-2021-44228 (PUBLISHED), persisted its real source record and finding; repeated retrieval reused the finding; applicability remained unknown |
| Docker | Built non-root development image with frozen dependencies and verified TLS using temporary cloud CA mount; repeat helper build passed. Container + PostgreSQL real HTTP login, organization page and software inventory API passed |
| Compose | Configuration syntax validated; image/runtime/database separately exercised. Full Compose lifecycle was not used in this session |
| PostgreSQL recovery | Custom-format dump restored into an isolated database; organization, operator policy, source/asset, installation and finding relationships verified, then isolated restore database removed |
| GitHub access | Native Git read and API metadata succeeded. `git push --dry-run origin HEAD:refs/heads/main` passed, confirming the push path without publishing a branch |
| Repository visibility and license | Owner confirmed public open-source publication and selected AGPL-3.0-or-later; no visibility change is needed |
| GitHub Actions | [Run 38872455361](https://github.com/rommelfs/bearings/actions/runs/38872455361) passed: 44 tests on SQLite and 44 on PostgreSQL, plus lint, formatting, migration drift, checks and static collection |

Tests cover cross-organization reads/writes and foreign-key injection; per-organization membership roles; operator default-deny/revocation and audit; policy ownership; restricted raw and derived finding visibility/counts; CSRF and HTML escaping; IPv4/IPv6/ranges/domains and DNS boundaries; historical/shared/private claims; separate contact review concepts, hashed/expiring/one-use tokens, update invalidation and reminder deduplication; pending/failed/confirmed inventory writes, backoff and recovery; partial NetBox responses and wrong tenant identities; product selection isolation; unknown versions; finding deduplication, analyst override/history; proxy destination restrictions; repeatable synthetic seeding; and the inventory-to-both-views slice.

Toolchain: host Python 3.12.14, Django 5.2.18, uv 0.12.23; image Python 3.12.15. Dependencies and hashes are in `uv.lock`. Cloud-specific DNS/proxy and Docker build namespace issues were diagnosed and corrected without disabling verification. Source fixtures validate contracts, not live compatibility.

Connections: Vulnerability-Lookup real public read tested; central NetBox adapter fixture-tested but no live instance/key supplied; development inventory adapter explicitly synthetic; MISP official OpenAPI researched but adapter pending; Plum Island official InfoIP semantics researched but adapter pending. Generalized applicability, continuous import, production scheduling/delivery/security controls and complete connector policy remain backlog work.

The environment install/start configuration was saved as a draft, including cloud proxy-DNS settings and required GitHub/Vulnerability-Lookup domains. Draft persistence is not publication or proof of fresh-task restoration. Public source publication and AGPL-3.0-or-later are owner-approved. A verified security reporting channel remains outstanding.

The implementation and AGPL-3.0-or-later license are published on public `main`. Four milestones and 15 issues were created; issue #1 is completed. Repeating backlog publication created zero duplicate issues. Source/license links are present in the application. Repository description editing remains unavailable through the integration (HTTP 403); an owner can set the description in GitHub settings. No deployment or operational-data publication occurred.

## Multi-instance NetBox increment

The instance/capability migrations applied successfully to existing SQLite and PostgreSQL databases; drift checks pass. The expanded suite executed **64 tests on SQLite and 64 on PostgreSQL, all passed**, including 20 new multi-instance query/capability tests. Ruff lint/format checks and Django checks pass. The actual CLI runs against the current unconfigured environment and reports zero live sources; this is not a live connection validation.

Contract fixtures cover two distinct instance keys and URLs, identical external IDs across instances, complete offset pagination, malicious/changed continuation scope, missing/duplicate/wrong-tenant pages, failure isolation across multiple bindings, independent read health with retained data, read-only portal/service denial, blocked queued writes after downgrade, cached capability revocation, instance-specific write defaults/authentication, dedicated whole-instance access, missing/invalid credential references, operator-only configuration/audit and legacy fail-closed upgrade behavior. No NetBox instance was contacted and no automatic projection import is claimed.

## Bundled NetBox development environment

The local lab uses official NetBox `v4.7.3-5.1.1`, PostgreSQL 17, Valkey 9.1 and a verified HTTPS gateway. Fresh initialization, repeated provisioning, retained credentials/data, read-only and read-write tenant queries, upstream read-only POST denial, both application logins, real device/VM writes through the durable worker, and recovery after a lost acknowledgement were exercised against the real bundled API. The expanded suite passed all 75 tests on SQLite and all 75 on PostgreSQL. Ruff lint/format, migration drift and whitespace checks passed. The final live smoke/query checks passed again after the retained-data app restart; HTTPS-only cookies and the disabled outbound SMTP destination were confirmed in actual NetBox settings. General inventory import remains unimplemented; only explicitly identified synthetic starter assets are projected locally.

External mode was exercised against a separately running copy of the pinned reference NetBox, with a supplied CA, private token and read-only tenant scope. It started only Bearings and its database/worker, remained usable while the reference was unavailable, then queried devices, virtual machines, IP addresses and prefixes successfully after connectivity was restored. Switching back retained the bundled data. This validates the external wiring, not compatibility with every independently deployed NetBox release. AMD64 was run; ARM64 image manifests were checked but ARM64 execution was not tested.

A final full restart in this cloud hit the shared host's inode limit: Docker uses the `vfs` storage driver and copies the large NetBox image per container. Unused build cache and unstarted lab containers were removed without deleting volumes. Final local checks used the retained running NetBox and sequential app startup, omitting the separate NetBox background worker/provision container. The committed integration workflow exercises the complete default stack, smoke checks, shutdown, retained-volume restart and queries on a standard GitHub Docker runner. This environment is for development; no production notifications, scans, external-server provisioning or operational data publication occurred.

The smoke target guard additionally checks the current database endpoint, token reference, authentication, capability, tenant and organization before any HTTP access; a regression test verifies refusal after an operator changes the stored endpoint. The guarded real smoke workflow passed again.

Public CI confirmed the complete default stack on the guarded implementation: [Development stack run 38883987302](https://github.com/rommelfs/bearings/actions/runs/38883987302) passed fresh startup, the real HTTPS/query/login/write/recovery smoke, shutdown without data deletion, retained-volume restart and queries. [Checks run 38883987223](https://github.com/rommelfs/bearings/actions/runs/38883987223) passed 75 tests on each database plus lint, formatting, system checks, migration drift and static collection. Issue #17 is complete; general import and broader deployed-version validation remain separate backlog work.

## Docker prerequisite diagnostics

Following a macOS report with no `docker` executable on PATH, the helper now fails before changing local lab state, identifies missing Docker/Compose or an unreachable engine, and preserves offline external configuration. Regression checks cover missing CLI without state creation, missing Compose, engine errors and engine timeout. The expanded SQLite suite passed all 77 tests; Ruff passed. macOS Desktop installation remains a user-side prerequisite and was not performed in the Linux cloud.

## General NetBox import and reconciliation

The bounded four-type importer now projects devices, VMs, IP addresses and prefixes for central and external sources, using GETs only. It validates the complete traversal before committing, preserves local assessments/software/findings, tracks separate import health/freshness, queues member-requested refreshes and runs periodically in the development worker. Missing identities remain retained with reasoned review/reappearance handling; no importer deletion is implemented.

Local validation: **95 tests passed on PostgreSQL**, including two real concurrent-transaction tests that observe the second transaction waiting on the source lock. SQLite executed the same 95-test suite with **93 passed and the two PostgreSQL-only lock tests explicitly skipped**. Migrations applied to existing SQLite and PostgreSQL databases; system checks, Ruff lint/format, frozen dependency sync and migration drift passed. No test-created database sessions remain after the concurrency checks.

The rebuilt complete local stack passed the extended live smoke against official NetBox v4.7.3 / netbox-docker 5.1.1: one synthetic device created directly in NetBox without a seed identity was imported, renamed upstream and refreshed while local criticality/team survived, then deleted only as that invocation's owned upstream probe. Bearings retained its missing projection. The real read-only import, four scoped query types, HTTPS/admin and portal logins, upstream/portal read-only denial, portal device/VM worker writes and lost-ack recovery passed too. Source data and credentials were retained across the image/migration upgrade. These tests used only the synthetic bundled lab, not operational inventory or production delivery.

Contract coverage adds repeated/multi-instance identity, complete pagination, last-endpoint failure rollback, malformed/wrong-tenant data, lost-ack adoption and conflicting marker rollback, foreign-marker isolation, pause/manual queue/interval/failure throttling, continued processing after another source fails, membership/CSRF restrictions, escaped allowlisted metadata, bounded UI/API pages and preservation of import health during stale operator form saves. Strong upstream snapshot consistency, interfaces/service topology/OS inference, broader NetBox versions and monitored production scheduling are not claimed.

A separate real HTTP workflow verified company-admin login, the read-only workspace's CSRF-protected Refresh inventory request, consumption by the running periodic worker, and the fresh paginated inventory API containing all four kinds and constructed source links. Repeating the real `sync_netbox --all` command imported two sources without new identities or deletion; the smoke probe remained a retained missing record.

The first import revision passed complete public CI: [Checks 38901475599](https://github.com/rommelfs/bearings/actions/runs/38901475599) and [Development stack 38901475661](https://github.com/rommelfs/bearings/actions/runs/38901475661), including fresh full-stack startup, extended real import/write smoke and retained-volume restart. A final browser-link correction adds an optional operator-owned HTTPS browser base distinct from the API destination, with a localhost/gateway-port default for the bundled lab. Credentials still target only the API base; the regression test also rejects credential-bearing browser URLs. The expanded suite passed 96 tests on PostgreSQL; SQLite passed 94 with the two PostgreSQL-only concurrency tests explicitly skipped.

The separate browser-address revision also passed the rebuilt complete local stack and extended real smoke. A host request to the constructed localhost HTTPS device URL verified the generated CA and returned the expected unauthenticated login redirect (302).

Final browser-address implementation 2f798f1 passed [Checks 38902455756](https://github.com/rommelfs/bearings/actions/runs/38902455756) (96/96 PostgreSQL; 94 passed + two explicit PostgreSQL-only skips on SQLite) and [Development stack 38902455791](https://github.com/rommelfs/bearings/actions/runs/38902455791) (fresh full startup, extended import/write/browser-link smoke, stop retaining data, restart and queries). Issues #3 and #14 are completed.
