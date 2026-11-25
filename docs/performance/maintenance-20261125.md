# Portal maintenance and performance, 25 November 2026

The first maintenance pass separates the browser views for inventory, inventory edits,
company contacts and scope, and vulnerability review. Organization read APIs and signed
device APIs have their own modules. The [architecture guide](../architecture.md) records
the new entry points.

The review found an inconsistency between the review list and grouped follow-up cases.
A saved **not affected** decision now places the finding in the cleared group even
when the package proof still matches an affected version. The original proof remains
available. Both views use the same precedence rule.

Host summaries skip package proof queries when no distribution feed can yield a current
evaluation. The page still reports missing coverage and counts saved assessments and
operational issues. Views that only need machine rows skip unused aggregate totals.
The issue board filters and orders explicit eligible IDs before fetching the page
details. The review list groups bucket and severity counts together. The overview
batches audit inserts, and read-only views reuse the actor's analyst role within the
request. The map fetches the fields it uses and resolves link routes once per response.
Review and overview templates reuse repeated links.

## Paired measurements

Both datasets used isolated PostgreSQL 17.11 with two database CPUs and 3 GiB RAM.
The small dataset held four companies and 48 assets. The larger one held 480 companies,
48,000 assets and installations, 2,880 findings, and 4,320 issues. The workload has one
installation per asset and does not include a live distribution advisory feed. The
serial figures below are medians of five authenticated requests through the application
and its templates. The same retained data and actual route were used on both sides.

| View | 48 assets, before → after | 48,000 assets, before → after |
| --- | ---: | ---: |
| Infrastructure overview | 342 → 168 ms | 309 → 207 ms |
| Company detail | 396 → 117 ms | 423 → 150 ms |
| What needs attention | 305 → 136 ms | 366 → 216 ms |
| National summary panel | 104 → 39 ms | 174 → 89 ms |
| National issue list | 60 → 54 ms | 403 → 131 ms |
| National map | 28 → 22 ms | 67 → 46 ms |
| National review queue | 90 → 87 ms | 156 → 137 ms |

With four concurrent clients, each dataset completed 84 loopback requests across
21 routes with zero HTTP failures. The final p95 was **393 ms** with 48 assets and
**498 ms** with 48,000. All 18 functional checks passed on both datasets.

The original benchmark pointed the overview and company search at the public landing
page. The comparison above uses the corrected authenticated routes. The initial
small repeat also exhausted the due reminder. The reminder probe now uses a temporary
file sink and rolls back fixture changes, so repeats can verify actual file delivery.
Final loopback HTTP timings exclude Django's test-only template instrumentation.

## Stability and production-shaped verification

The first sixteen-client threaded diagnostic run returned five 503s on the map.
The final run on the same workload completed **420/420 requests** and all 19
functional checks. It included 186 synthetic software changes and 122 summary
refreshes, restored the original version, and completed 40 concurrent scoped write
probes with zero failures. Its p95 was **5.53 s**. That in-process diagnostic remains
too slow under contention even though the map recovered.

A separate loopback verification used Gunicorn with the Ubuntu service's **three
workers and two threads per worker**. Sixteen callers made **420 requests** on
the larger dataset while another process updated a synthetic software version and
refreshed company summaries. It recorded 106 updates and 43 refreshes with no
errors. All 420 responses succeeded, with p50 **435 ms**, p95 **922 ms**, and
maximum **1.35 s**. Authenticated Chromium loaded the infrastructure overview,
vulnerability review, and national overview with all five panels and the map.

The Gunicorn verification used one synthetic company user and one analyst, and
ran without Nginx, TLS or SSO. The sustained load limit and behavior with denser
software inventories or fresh vendor rules still require separate measurements.
Production browser latency and the current 40,000-company capacity were not
measured in this pass.

Use the [guarded scale runner](scale-test.md) with an empty isolated dataset.
For the larger workload, seed with `--companies 480 --assets-per-company 100`.
For the diagnostic stress test, measure with `--samples 5 --concurrency 16
--http-profile full --http-repeats 20 --churn`. Stop the owned lab when finished.
