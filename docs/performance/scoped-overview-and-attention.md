# Company infrastructure and attention response times

The reported authenticated CIRCL page loads were approximately five seconds
for `/infrastructure/?organization=circl` and seven seconds for
`/actions/?organization=circl`. The production requests were not replayed.

Infrastructure keeps the complete company counters and priority previews. It
groups reviews on the scoped proof facts and derives the workflow bucket from
those counts without rechecking the package proof for the bucket. Automatic
version evidence and saved analyst decisions are counted separately.

The attention machine list groups current authorized affected proofs once for a
selected company. Counts and sorting use the resulting machine flags. It uses a
single PostgreSQL snapshot across the grouped evidence and paginated results
and retains the existing query when more than 250 matched machines would be
materialized or no company is selected. Device coverage, analyst assessments,
operational follow-up, overdue ranking, bounded previews and missing evaluations
retain their existing rules.

## Measurements

The same loopback PostgreSQL 17 fixture contained 1,000 active machines and
10,000 current native Ubuntu package-CVE proofs with linked issues. One host
reported inventory and each cloned proof included about 29 KB of synthetic
context. Each median uses six warm authenticated requests through Django. Both
pages returned HTTP 200 with their full results. Infrastructure included 10,000
automatic matches and counted one matched machine. Attention counted 1,000
machines, showed the current distribution-version match and paged the cards.

| Complete response | 391046a | Updated |
| --- | ---: | ---: |
| Infrastructure | 751 ms | 625 ms |
| What needs attention? | 1,593 ms | 595 ms |

After updating, check both authenticated page requests in the browser's Network
panel. The numeric `Server-Timing` response header gives the view duration,
total database time, slowest query and render time. Infrastructure also reports
scope, company and priority phases. Compare these values with the browser's
waiting time and page-load time to locate any remaining difference.

Use the normal server update with migrations, Django checks and a web restart.
This change adds no migration, runtime dependency or client release.
