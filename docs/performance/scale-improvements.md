# Iterative scale improvements — 19 November 2026

The original [failed baseline](scale-test.md) is retained. This follow-up implements the measured fixes and repeatedly tests the **same 40,000-company, 1,200,000-asset/installations PostgreSQL dataset**, including 240,000 findings and 360,000 issues. The normal lab's business data was not replaced by scale fixtures. No external mail, scan, public deployment or production connector write was performed.

## What changed and why

* Global reviews previously prefetched the whole inventory and exceeded 3 GiB of application memory. Company cards now page 24 organizations before related work. Review/issue pages sort narrow IDs and hydrate 25 objects through the original scoped queryset. Company selectors/search and operator audit work are bounded; no 40,000-company permission loop remains.
* PostgreSQL estimated highly correlated same-company ownership comparisons as independent predicates, selecting huge nested loops. SQL CASE preserves all ownership checks and NULL rejection while avoiding that selectivity multiplication. Small company scopes also supply redundant literal bounds alongside the live authorization query. This fixed particularly bad owner review plans exposed by testing 16 different owners after ANALYZE. Ordering and software identity indexes support bounded pages and exact research.
* National summaries, version prevalence, problems and trends now use incrementally refreshed per-company projections. Separate operator/shared evidence variants still apply current membership and sharing policy at read time. Relevant bulk/database changes invalidate their company transactionally. Health-only poll updates do not trigger unnecessary full rebuilds. The UI states the prepared-company coverage, pending count and oldest refresh time; unavailable data is never shown as a clean zero.
* A dedicated `national-worker` refreshes bounded batches independently of external imports. Concurrent refresh/write tests found a lock cycle; removing database foreign keys **only from disposable cache children** avoids it. Business constraints remain. Organization delete/truncate cleanup, merge, cache-reset recovery and synthetic provenance cleanup are tested explicitly.
* Confidential no-CVE research uses original product identities and combines prepared data with pending companies' live data inside one repeatable-read snapshot. Versions are never silently skipped because a company is awaiting refresh. The map uses the same safe partitioning. Large pending sets fall back to bounded live queries. Research criteria stay out of URLs, audit details and upstream requests.
* Lists, map and research now return private retryable unavailable responses on overload. PostgreSQL planning/JIT settings and query budgets are transaction-local and restored; permissions, source integrity and applicability semantics remain enforced.

## Iterations, including failures

| Round | Actual finding / result | Response |
| --- | --- | --- |
| Original, 2 DB CPU cores | National/action timeouts, map 500, 1000-query issue abort, 39-second review abort | Bounded pages, scoped query changes and read models |
| Early fixes | All serial routes became available, but a full four-client matrix still failed | Add exact research projections, selective bounds and bounded list planning |
| Multiple owners | Some company review plans timed out after statistics refresh | Preserve live scope and add small-scope literal bounds; 400 requests across 16 owners then passed |
| Concurrent refresh | A writer/refresher key-lock cycle was reproducible | Remove only cache-child FK locks; test both serialization orders |
| Full workload with ongoing changes, 2 CPU cores | 7 failures / 168 HTTP calls; all 19 correctness/workflow checks passed | Retain the failure as evidence of a capacity limit |
| Same workload, 4 CPU cores | 0 failures / 168 HTTP calls, p95 4.06 s; 129 updates and 71 refreshes, no errors | Use this resource envelope for broader repeat runs |
| 16-client national run during whole-lab startup | 7 timeouts / 300 calls | Do not accept the startup-contended result; repeat after startup |
| Stable 16-client national repeat | 0 failures / 300 calls, p50 1.39 s, p95 2.60 s | Passed; no excluded route |

Percentiles include failure durations where present; a timeout is never counted as a successful request. The original two-core baseline, the two-core live-write failure and the four-core successes must not be presented as one hardware-identical comparison. The shared host has five CPUs and other lab services; this is an observed envelope, not a guaranteed production SLA.

## Final repeated measurements

All 21 serial routes returned 200 with three samples each and no diagnostic guard. The final full workload used four database CPU cores / 3 GiB RAM. Serial values are medians in milliseconds, not concurrent percentiles. The original baseline used two cores and is shown only to identify the historical failures.

| Route | Original baseline (ms / status) | Final serial median (ms) | Final SQL statements |
| --- | ---: | ---: | ---: |
| `company_overview` | 274.6 / 200 | 405.1 | 36 |
| `company_inventory` | 22.3 / 200 | 21.8 | 15 |
| `company_detail` | 54.6 / 200 | 84.7 | 27 |
| `company_asset` | 28.6 / 200 | 52.4 | 16 |
| `company_issues` | 3657.1 / 200 | 79.2 | 28 |
| `company_reviews` | 825.5 / 200 | 57.1 | 36 |
| `company_actions` | 3068.2 / 503 | 44.6 | 23 |
| `company_wizard` | 22.6 / 200 | 28.5 | 16 |
| `national_shell` | 8.8 / 200 | 9.5 | 7 |
| `national_summary` | 4152.9 / 503 | 264.4 | 27 |
| `national_problems` | 1372.9 / 200 | 170.8 | 23 |
| `national_versions` | 3031.4 / 503 | 301.0 | 21 |
| `national_activity` | 3045.5 / 503 | 282.9 | 23 |
| `national_map` | 6166.0 / 500 | 1829.4 | 27 |
| `national_findings` | 4658.2 / 200 | 772.8 | 23 |
| `national_company_search` | 683.2 / 200 | 450.0 | 47 |
| `national_inventory` | 1978.5 / 200 | 121.4 | 16 |
| `national_issues` | 994.9 / 500 | 1262.4 | 31 |
| `national_reviews` | 38935.3 / 500 | 1014.1 | 40 |
| `research_exact` | 14286.1 / 200 | 979.4 | 28 |
| `research_range` | 12481.0 / 500 | 987.9 | 29 |

| Real HTTP profile | Concurrency | Requests | Failures | p50 / p95 (ms) | Elapsed (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| National panels | 16 | 300 | 0 | 1389.3 / 2598.2 | 25.56 |
| Company pages / distinct owners | 16 | 400 | 0 | 547.8 / 2090.2 | 19.83 |
| All routes + ongoing changes | 4 | 1050 | 0 | 547.6 / 4054.4 | 305.23 |

The final full run passed **19/19 correctness/workflow checks**, with **784 committed inventory updates and 431 refreshes**, no background error and the original version restored. All 40 concurrent scoped owner writes passed (p95 75.0 ms); committed write/read/probe cleanup passed and the exact 1,200,000-asset count was preserved. The serial-stage process peak RSS was 103.5 MiB, compared with the baseline's 3.27 GiB review abort; this is not a measurement of all production worker memory or the later HTTP phase. The synthetic database including new projections occupied 1.86 GiB, not a sizing estimate for real evidence.

Published reports omit SQL plans and retain individual samples/statuses:

* [live-full4](scale-40000-live-full4.json) — intentionally failed two-core workload.
* [live-full4-4cpu](scale-40000-live-full4-4cpu.json)
* [final-national16-stable](scale-40000-final-national16-stable.json)
* [final-full-soak](scale-40000-final-full-soak.json)
* [final-company16](scale-40000-final-company16.json)

A final targeted check narrowed the global issue ordering input to the explicitly selected company, while keeping the original full eligibility query. Three CIRCL company drilldowns on the retained fixture returned 200 in 270.4 / 93.6 / 70.4 ms (previously 1581.6 / 419.1 / 434.2 ms). These are small local diagnostic samples with differing cache/host conditions, not a separate capacity claim. The full HTTP matrix above predates this additional restriction; its unfiltered paths are unchanged.

## Operation and reproduction

PostgreSQL is required for the measured national read-model path. SQLite remains a small, single-worker fallback. Apply migrations **before serving traffic**: the new index migration can lock tables while building indexes. Back up the deployment and plan an upgrade window; this change does not claim an online migration rehearsal.

In the bundled lab, `python3 scripts/dev.py up --no-build` applies migrations, starts the independent `national-worker`, and reloads web/worker code. For another deployment, schedule the refresh process independently of connector imports:

```sh
uv run --frozen python manage.py refresh_national --limit 100000
uv run --frozen python manage.py refresh_national --watch
```

The first command prepares the initial backlog in bounded transactions; the second is an ongoing process. Initial preparation of this dataset took several minutes, not an HTTP request. Multiple refreshers use SKIP LOCKED. Monitor worker health/heartbeat, pending-company count, oldest prepared timestamp and database/storage headroom. If preparation is unavailable, panels disclose partial coverage or return 503; they do not manufacture national completeness. Migrations/triggers and current scope are part of correctness; do not disable them to accelerate writes.

To repeat on the retained, isolated fixture:

```sh
python3 scripts/scale_test.py measure --label repeat-national --database-cpus 4 --samples 3 --concurrency 16 --http-profile national --http-repeats 50
python3 scripts/scale_test.py measure --label repeat-company --samples 3 --concurrency 16 --http-profile company --http-repeats 50
python3 scripts/scale_test.py measure --label repeat-full --samples 3 --concurrency 4 --http-profile full --http-repeats 50 --churn
python3 scripts/scale_test.py stop
```

The CPU option validates ownership and changes only the isolated scale database. It persists for subsequent measurements. RAM remains capped at 3 GiB, PostgreSQL shared_buffers at 256 MiB and work_mem at 16 MiB. Reports record actual settings. The host Python application runs outside that memory cap. Measurements run with DEBUG=False, refreshed planner statistics, local sessions, file mail and no upstream credentials. The raw SQL plans remain private under `.local/scale-test/`; published JSON omits plans and cookies.

The full profile exercises all 21 routes, including actual CSRF-protected exact/range research POSTs. Continuous churn commits one synthetic installation's version changes while a separate refresher runs, then restores its original version. Forty additional concurrent owner-create operations exercise real view/CSRF/service/SQL behavior inside rolled-back transactions; these are explicitly not HTTP write-throughput measurements. A separate CSRF-enforced client commits one owner asset, reads it, deletes exactly that probe and checks the original inventory count. Original counts and ownership remain checked after each run.

## Regression and real bundled runtime

The final corrected full suites pass: **604/604 PostgreSQL tests**; SQLite **567 pass / 37 PostgreSQL-specific skips out of 604**. Frozen sync, full-repository Ruff lint/format, system/migration-drift checks and static collection pass. Retained bundled startup, NetBox/FlowIntel/RT/RTIR smoke and shared native SSO/HTTPS canvas checks pass. The scale container is stopped while its volume and raw reports remain available for a repeat. See [validation details](../validation.md).

## Limits before an operational rollout

Passing these tests supports the tested **cardinality and workload**, not every possible workload. This fixture has one installation per asset, three product identities per company and limited history. A very large single tenant, many installations per host, long evidence histories, skewed distributions and hours/days of sustained traffic need deployment-specific capacity testing. The threaded loopback WSGI diagnostic is not a production server or TLS/SSO capacity test. Native bundled SSO/integrations are checked separately with real lab services, not 40,000 native identities.

Production rollout still needs representative authorized provider/SMTP validation, monitored workers and failure recovery, backup/restore/retention and sizing of the intended ingress/database/web-worker configuration. Four DB CPUs and 3 GiB were sufficient for the passing local workload; this is a measured test configuration, not a universal minimum or a recommendation to operate without headroom. No public deployment was performed.
