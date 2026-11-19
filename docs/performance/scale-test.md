# Synthetic PostgreSQL scale acceptance

This test creates **40,000 companies × 30 assets = 1,200,000 assets** in a separate, explicitly owned PostgreSQL container. The ordinary development database, worker, passwords, native SSO grants and upstream systems are not changed.

## Reproduce

From the repository root, with Docker and uv available:

```sh
python3 scripts/scale_test.py seed --companies 40000 --assets-per-company 30
python3 scripts/scale_test.py measure --label baseline --samples 3 --concurrency 4
python3 scripts/scale_test.py workflows  # separately verifies actual file-sink delivery
python3 scripts/scale_test.py stop
```

Seeding requires an empty dedicated database. An existing dataset is never erased/reseeded automatically; use `measure` to repeat on it. `measure` restarts the owned container if it was stopped. Reports and private ownership/password state live in ignored `.local/scale-test/`. Do not publish the private state or PostgreSQL environment file. `stop` retains the synthetic named volume and reports, so another measurement uses exactly the same records. The runner refuses an unrelated container occupying its name. A completed diagnostic is not a passing acceptance test: inspect `acceptance_passed`, all HTTP statuses and correctness checks in its report.

The container publishes PostgreSQL on an automatically assigned loopback-only port (also suitable for Docker Desktop), uses an internal Docker network, and has limits of two CPU cores and 3 GiB RAM. PostgreSQL 17 uses 256 MiB shared buffers and 16 MiB work memory. The Python application runs on the host. The shared development environment is not a dedicated capacity lab. The fixture is created in batches of 500 companies, with database statistics refreshed before measuring.

## Workload

Each company has its own local owner and membership, two contacts, two declared infrastructure claims, one manual inventory source, a periodic review policy and three product identities. Each asset has one software installation, including missing and differing version strings. Per company there are six findings covering confirmed/new/under-review/accepted/resolved/false-positive states, nine vulnerability/lifecycle/exposure issues, original evidence, discovery matches and repeated history. Ten percent of companies are private to CIRCL, and some evidence/issue details remain hidden from company users.

These are deliberately recognizable synthetic names, `.example.invalid` email/domain destinations, private test IPs and fictional addresses. CVE identifiers label synthetic evidence; the generated distribution is not a statement about actual Luxembourg vulnerabilities. Watches are disabled; no connector credentials are copied. Service mail stays in the isolated local file outbox. No real vulnerability lookup, MISP, NetBox, AIL, SMTP or other upstream service is called.

## Measurements and checks

The serial matrix covers company overview/inventory/detail/asset/issues/reviews/actions/wizard, national shell and all four panels, map, findings, company search, national inventory/issues/reviews and confidential exact/range software research. A full Django request client exercises authentication middleware, authorization, queries and templates with `DEBUG=False`. The first request is retained as a first observed sample; these are warm-database runs, not operating-system cold-cache claims. SQL counts/durations and the slowest estimated PostgreSQL query plans are saved. SQL parameters, session cookies, passwords and reminder links are not included in the report.

The HTTP phase uses an actual loopback threaded WSGI diagnostic server with authenticated local sessions and four concurrent clients. It includes national panel requests rather than counting only the fast shell. Serially failed panel routes are explicitly excluded from parallel traffic and listed as exclusions; those failures remain acceptance failures. No exclusion is a passing result. This server is not the intended production web-server configuration and does not test TLS/SSO/ingress latency.

Each diagnostic SQL statement has a five-second timeout; national endpoints retain their existing tighter limits. A diagnostic request stops at the next SQL execution after 1,000 statements or a 12-second wall budget. Fetching/rendering already in progress can exceed that wall budget. Timeouts, query guards, 500/503s and HTTP client timeouts are failures, not successful latencies. Parallel percentiles include completed failures and must be read alongside status counts. Full local reports retain all individual samples and query plans.

Functional checks cover exact row counts, one company per owner, current CIRCL visibility, national access refusal for company users, foreign-company refusal and scoped inventory. A real owner asset write is rolled back to preserve fixture cardinality. Bounded inventory jobs and inventory-review reminders are exercised; reminder mail is local only.

## Production interpretation

A useful initial acceptance target is successful interactive company responses within one second and each national panel within two seconds under the tested four-request concurrency, with no timeout/guard and bounded work per page. These are proposed review thresholds, not a promised service level. Correct current authorization and evidence visibility remain required even if a cache or read model is added later.

This is a realistic cardinality test plus a small concurrency test. It does not establish sustained throughput, a maximum national user population, real connector capacity, native SSO performance, production SMTP delivery, backup/restore, failover or a long-duration soak. Uniform thirty-asset companies do not cover a single very large company, and one installation per asset is a lower software-density case. More software per asset, more accumulated history, skewed tenants and longer-running concurrent read/write traffic require additional runs.

## Observed result — 19 November 2026

**The current application is not ready for this cardinality on the tested resources.** The complete requested fixture was created and measured. Several company paths perform well; global reviews, action queries and national aggregates are production blockers. No application queries or authorization policy were changed during this baseline experiment.

The run used PostgreSQL 17.11 and Python 3.12.14, with the database limited as above and five host CPUs available to the Python process/shared lab. The dataset took **520 seconds** to seed and occupied **1.43 GiB** including database indexes. The scale database contains 40,000 owner users plus one analyst. The analyst sees 36,000 companies and 1,080,000 assets; 4,000 companies remain private. A company owner has exactly one company and thirty assets. These small synthetic records are not a storage estimate for real inventories.

[Machine-readable baseline](scale-40000-baseline.json) contains every sample. Successful routes have three serial samples; a failed route stops after its first failure. “Abort” below means the diagnostic guard stopped further work. In particular, the global review figure is time until abort, not a completed request.

| Path / feature | Observed serial median | Last status | Queries | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `company_overview` | 0.275 s | 200 | 34 | successful |
| `company_inventory` | 0.022 s | 200 | 13 | successful |
| `company_detail` | 0.055 s | 200 | 27 | successful |
| `company_asset` | 0.029 s | 200 | 16 | successful |
| `company_issues` | 3.657 s | 200 | 19 | successful |
| `company_reviews` | 0.826 s | 200 | 23 | successful |
| `company_actions` | 3.068 s | 503 | 18 | postgres_timeout |
| `company_wizard` | 0.023 s | 200 | 16 | successful |
| `national_shell` | 0.009 s | 200 | 7 | successful |
| `national_summary` | 4.153 s | 503 | 19 | postgres_timeout |
| `national_problems` | 1.373 s | 200 | 19 | successful |
| `national_versions` | 3.031 s | 503 | 15 | postgres_timeout |
| `national_activity` | 3.046 s | 503 | 16 | postgres_timeout |
| `national_map` | 6.166 s | 500 | 16 | postgres_timeout |
| `national_findings` | 4.658 s | 200 | 11 | successful |
| `national_company_search` | 0.683 s | 200 | 47 | successful |
| `national_inventory` | 1.978 s | 200 | 130 | successful |
| `national_issues` | 0.995 s | 500 | 1000 | query_count |
| `national_reviews` | 38.935 s | 500 | 6 | wall_time |
| `research_exact` | 14.286 s | 200 | 15 | successful |
| `research_range` | 12.481 s | 500 | 10 | wall_time |

The global review request reached **3,344.8 MiB process peak RSS** (about 3.27 GiB), versus roughly 80 MiB before that request. Peak RSS is a cumulative process high-water mark, not independently measured memory consumption for every subsequent route. Code inspection confirms that `views.home` eagerly builds all visible organizations and prefetches their assets before paginating findings: this run pulls approximately 1.08 million asset objects into Python. It then performs per-company reads/audits. The diagnostic abort occurs only at the next SQL execution, after the already-running fetch/materialization; that explains the 39-second wall time despite a nominal twelve-second guard.

`issue_views.board` iterates every visible company to audit/check edit permissions and populate selectors/creation links. It hit the **1,000-query guard** before returning. Its reported 0.99 seconds is only the early abort; it does not estimate total real page time.

The estimated PostgreSQL plans show another problem: same-company integrity predicates across source/asset/product tables lead to strongly underestimated join cardinalities and nested-loop plans. For example, a company-only issue page's slowest query chooses a broad asset/source scan, and national version aggregation estimates almost no surviving rows despite over a million valid installations. This is evidence to investigate join shape/statistics and request scoping; no claim is made that estimated plans alone prove exact executor row counts. Merely increasing a timeout or adding a generic foreign-key index is not a verified fix. The tenant/evidence consistency checks must remain enforced.

The ordinary national shell was 9 ms, but summary, versions and activity returned **503** from their existing database budgets. The map returned **500** after its six-second database timeout, which also requires graceful failure handling. Exact software research completed around **14.3 seconds**; range research hit the diagnostic wall budget. The national findings page completed around **4.7 seconds**. Thus shell latency is not representative of usable national information.

### Parallel HTTP and correctness

Four concurrent HTTP clients made twelve real authenticated requests: company overview, national shell and the national problems panel, repeated four times. Overall p50 was **617 ms**, p95 **3,137 ms**, and **3/12 requests failed (503)**. The failures were all national problem-panel requests. Company overview stayed at **418–907 ms**. Summary/versions/activity were already failed in the serial matrix and are explicitly excluded from this small burst, not counted as passing. The observed 2.37 completed responses/second includes failures and is not a capacity claim.

**Eleven of twelve functional checks passed.** The failed check is national-summary availability. The passing checks cover exact company/asset counts, login requirement, one membership/company, cross-company asset/company denial, private-company denial to CIRCL, national/map denial to company users, exact scoped inventory contents and an actual owner asset write. That write took about **18 ms** and was rolled back. The unavailable summary prevented checking its aggregate counters through the UI; this is a failed acceptance condition, not missing evidence to assume away.

A due-reminder batch of ten policies completed in **159 ms / 159 SQL statements**, with eight deliveries into Django’s local in-memory test outbox. The initial test-template setup also replaced the email backend; the harness now explicitly restores the configured local file backend. A separate workflow run confirmed **eight actual file-sink messages, zero errors, 179 ms / 159 statements** without Django test-environment overrides. Django can append several messages to one file, so the verification counts Message-ID headers rather than equating file and message counts. The empty inventory-write queue poll took **4 ms / two statements**; this is not importer or queued-write throughput. No real message or connector call was made. Five harness safety/fixture tests passed on PostgreSQL, including ownership integrity and refusal to reseed a populated fixture.

### Next implementation priorities

1. **Bound global pages before loading related rows.** Paginate company cards and organization pickers, remove whole-inventory asset prefetches and per-company audit/permission loops from review/issue entry pages. Audit the scoped read and actually displayed records with bounded work; preserve current authorization. Add regression tests that verify work stays bounded as company count increases.
2. **Reshape scoped issue/action/research queries.** Keep company filters early, separate count and page work, remove unnecessary joins and diagnose the correlated same-company predicates without weakening tenant integrity. Validate proposed indexes/query shapes with actual execution plans on this retained dataset. Protect expensive confidential research with bounded execution and a recoverable error.
3. **Move repeated national aggregation to an incremental read model or background snapshots.** Publish freshness/completeness; apply current company/evidence visibility when serving data. Do not cache a privileged analyst's entire result globally. Version distribution and trend refresh need explicit bounded work rather than complete repeated joins on every page view.
4. **Make national failures recoverable.** The map needs the same graceful unavailable/retry behavior as other panels. A shell rendering successfully must not count as a passing overall overview.
5. **Repeat this unchanged dataset, then broaden acceptance.** Require all functional checks and panels to succeed before a longer 16/32-client read/write soak. Add more installations per asset, a large-tenant distribution, accumulated history and real deployed web/SSO/connector/SMTP paths separately.

This change provides the reproducible benchmark and evidence. It does **not** claim those production blockers have already been fixed.
