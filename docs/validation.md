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

The local lab uses official NetBox `v4.7.3-5.1.1`, PostgreSQL 17, Valkey 9.1 and a verified HTTPS gateway. Fresh initialization, repeated provisioning, retained credentials/data, read-only and read-write tenant queries, upstream read-only POST denial, both application logins, real device/VM writes through the durable worker, and recovery after a lost acknowledgement were exercised against the real bundled API. The expanded suite passed all 74 tests on SQLite and all 74 on PostgreSQL. Ruff lint/format, migration drift and whitespace checks passed. The final live smoke/query checks passed again after the retained-data app restart; HTTPS-only cookies and the disabled outbound SMTP destination were confirmed in actual NetBox settings. General inventory import remains unimplemented; only explicitly identified synthetic starter assets are projected locally.

External mode was exercised against a separately running copy of the pinned reference NetBox, with a supplied CA, private token and read-only tenant scope. It started only Bearings and its database/worker, remained usable while the reference was unavailable, then queried devices, virtual machines, IP addresses and prefixes successfully after connectivity was restored. Switching back retained the bundled data. This validates the external wiring, not compatibility with every independently deployed NetBox release. AMD64 was run; ARM64 image manifests were checked but ARM64 execution was not tested.

A final full restart in this cloud hit the shared host's inode limit: Docker uses the `vfs` storage driver and copies the large NetBox image per container. Unused build cache and unstarted lab containers were removed without deleting volumes. Final local checks used the retained running NetBox and sequential app startup, omitting the separate NetBox background worker/provision container. The committed integration workflow exercises the complete default stack, smoke checks, shutdown, retained-volume restart and queries on a standard GitHub Docker runner. This environment is for development; no production notifications, scans, external-server provisioning or operational data publication occurred.
