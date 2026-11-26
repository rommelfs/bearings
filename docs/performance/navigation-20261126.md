# Browser navigation audit · 26 November 2026

## Method and coverage

The baseline was `ad9176eb`. An unchanged copy of that revision and the updated source ran against the same isolated PostgreSQL 17 data. Chromium used a desktop viewport over loopback HTTP with external browser requests blocked. The baseline started at public pages and authenticated entry points for reader, editor, company administrator, CIRCL analyst and platform administrator. It followed the same-origin GET links that the fixture exposed, including pagination, filter links, evidence and detail pages, downloads and Django administration. The follow-up runs replayed the concrete role and URL pairs and inspected the rendered links again.

The small fixture held four organizations, eleven assets, Linux and Windows reports, a CSV import preview and offline integration examples. The larger fixture held 160 organizations, 8,001 assets and 1,656 current Linux package-CVE records concentrated on one host. A copy of that database had 10,656 current records on that host. The scale matrices include the infrastructure, attention, issues, organization inventory and hosts, asset, CVE and national views.

Timing starts before Chromium navigation and ends after window load, font readiness, automatic host and national fragments, national map data and two animation frames. For a file link the timed operation is receipt of the complete local response. Each row records status, render duration, TTFB and SQL time when available, and the status and timing of automatic background requests. Navigation targets reached through a redirect are recorded separately in the same row. A background 503 does not count as a complete successful page.

A second is the investigation threshold. Two seconds is the upper bound for the measured normal navigation. The measurements describe this local runner and fixture. Different runs can overlap on the runner. The matched peak matrix and focused repeat samples give more reliable comparisons than an isolated slow observation during broad discovery.

The link inventory covers the destinations exposed by these fixtures. Links differing only by a return parameter, a signed timestamp for the same case, or an in-page anchor that does not change loading share a target.
Access events created by the audit itself are represented by sampled admin event details, list pages and sort columns. The organization host and inventory entry anchors retain separate tests. The crawl measures individual sort and filter controls and the fixed stress matrix adds selected combinations. It does not enumerate every possible combination or submit forms. OAuth starts, one-time codes and sign-out are excluded from the read-only crawl. External services and assets at external origins are blocked. A route without an applicable synthetic object or integration configuration is outside browser coverage. The audit creates ordinary local access logs and does not contact a production site.

## What changed

- The infrastructure, asset, attention and CVE views reuse current proof membership in their authorized scope. PostgreSQL reads at most 20,001 proof IDs into one repeatable-read snapshot. Up to 20,000 IDs use a single typed array parameter in later queries and larger scopes use the SQL subquery. The scope and currentness predicates still check the finding, source, asset, installation, device, inventory sequence and vendor rule. The per-request cache is cleared at the end of the snapshot.
- The host overview aggregates scoped findings directly. The national problem panel ranks narrow example IDs before loading their related display objects. The host and national HTML fragments skip unrelated workspace navigation rendering and retain the retry and CSRF behavior.
- The asset summary skips the confirmed-fix history query when its scoped records contain no fixed proof. The existing 30-day verified-fix rules remain in effect.
- Rollout and profile navigation uses the same organization administrator scope as those views. Membership links require a company administrator membership. A link to a data-review follow-up appears when that organization has a review schedule. Direct requests continue to enforce authorization and missing-object handling.

An initial cold national test had HTTP 503 on four panels before their projections were prepared. The ordinary projection refresh restored the data. Baseline and follow-up timings use the prepared national state. PostgreSQL execution plans exposed repeated current-proof subplans in the dense cases. A trial using an unnested array in a subquery was rejected after it made the join slower. The retained implementation uses direct array membership.

The GitHub PostgreSQL suite also reproduced an existing HTTP 503 in the
`/reviews/` pagination fixture. Its log records statement cancellation after
the five-second limit. The review queue now checks its visible scope for
package evidence before building that classification. The empty-package
fixture can use a constant current-proof marker. The targeted PostgreSQL
scale and review tests completed all 48 cases.

## Concentrated package evidence

The peak run used the same 52 role/URL pairs in both passes. All 52 document
requests and their automatic fragments succeeded. The count above one second
fell from 34 to 21, and the count above two seconds fell from 11 to zero.
Median render time was 1.33 s before and 0.87 s after. The p95 moved from
2.33 s to 1.48 s. The slowest follow-up was the analyst's organization host
overview at 1.93 s, including its asynchronous host data.

| Peak route | Role | Render before → after | Document SQL before → after |
| --- | --- | ---: | ---: |
| What needs attention | Company administrator | 2.63 → 1.26 s | 1.72 → 0.84 s |
| Intelligence, affected CVEs | CIRCL analyst | 2.48 → 1.48 s | 1.69 → 0.77 s |
| Infrastructure, selected company | CIRCL analyst | 2.33 → 1.59 s | 1.19 → 0.66 s |
| Infrastructure overview | Company administrator | 2.32 → 1.45 s | 1.03 → 0.57 s |
| What needs attention, selected company | CIRCL analyst | 2.26 → 1.45 s | 1.43 → 0.99 s |
| Organization host overview including fragment | CIRCL analyst | 2.22 → 1.93 s | 0.17 → 0.20 s |
| Infrastructure, organization search | CIRCL analyst | 2.12 → 1.23 s | 1.20 → 0.51 s |
| Organization host overview including fragment | Company administrator | 2.10 → 1.11 s | 0.09 → 0.05 s |
| National overview including panels and map | CIRCL analyst | 2.09 → 1.32 s | 0.03 → 0.01 s |
| Intelligence, affected CVEs | Company administrator | 2.08 → 1.42 s | 1.44 → 0.65 s |
| Asset detail with package findings | Company administrator | 2.08 → 1.00 s | 1.57 → 0.65 s |

Document SQL covers only the HTML request. The automatic fragments have their
own SQL durations in the individual measurements. In particular a faster shell
alone would not indicate a faster host or national overview.

## Repeat a matrix

Use a disposable database on loopback with a name starting with
`bearings_scale_nav_` and the frozen project environment. Apply the migrations,
seed the appropriate synthetic dataset, and build the national read models
before the timed pass when measuring more than 100 permitted organizations.
The script requires `BEARINGS_SCALE_TEST=1` and
`DJANGO_SETTINGS_MODULE=scripts.scale_settings`. It uses local Chromium and a
Python interpreter with Playwright, separate from the server installation.

The fixture file contains `users` mapping role labels to usernames, with
`null` for an anonymous role, and `seeds` mapping those labels to arrays of
relative entry URLs. Authenticated fixtures must have unusable passwords.
The runner refuses any connection other than a local synthetic PostgreSQL
database and blocks external requests.

```sh
.venv/bin/python scripts/navigation_audit.py --fixture fixture.json --output before.jsonl
.venv/bin/python scripts/navigation_audit.py --fixture fixture.json \
  --replay before.jsonl.manifest.json --verify-links --output after.jsonl
```

The release changes server modules and templates. The PostgreSQL suite ran
1,113 tests with five skipped. The update adds no migrations, dependencies or
client rebuild requirements.
