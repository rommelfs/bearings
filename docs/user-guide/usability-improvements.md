# Simpler infrastructure review

Implemented on the current `codex/continuous-review-workflow` application baseline. These are presentation and navigation changes, not new vulnerability determinations or a deployment.

## Infrastructure overview

Company cards lead with the shared machine indicators. A current package-version match, an analyst-confirmed affected review, an application requiring manual assessment, and missing evaluation coverage remain distinct. Machine percentages retain their explicit denominators and currentness rules. Top-level inventory objects and all inventory objects are named separately because assigned address records are grouped only in the former; neither is relabeled as a machine count.

The main card shows at most three prioritized next steps. Each has an owner role and a direct action link; reasons and observation/evaluation timestamps are available under **Why this step?** Additional priorities, technical counters, coverage limitations and monitoring diagnostics are closed disclosures by default. No recommendations create tasks.

The server list presents one compact card per server. Network details and up to four evidence examples are expandable. The visible links retain exact asset/organization/attention scope. Selecting one company removes the redundant search-within-that-company form. The overview snapshot time and its refresh link are separate from the live Ubuntu lookup counters; a 100% lookup progress value is not a vulnerability clearance rate.

## Counters and language

The shared review categories use **Version matches & cases to assess**, **Vendor clarification needed**, **Awaiting current evaluation**, and **Fixed or not affected**. The first category can contain a current automatic match or a case still needing manual assessment; its title no longer asserts that every entry is affected. Classification, saved assessments and original evidence remain unchanged.

Group priority and issue-list ordering both use the highest recorded task priority or source severity, then the existing deadline/update tie breakers. Source severity is separate from organizational task priority and confirmed applicability. The original source summary and human decisions remain available.

## Filters and return paths

Issue filters visibly identify organization, software group, asset, attention, type, deadline and searches. Individual chips remove the relevant filter and reset pagination; removing an organization also removes its dependent group/product/asset constraints. The full filter form is available under **Search and filter issues**, while active filters remain visible. Software-group/product constraints are submitted again when applying another filter; the label stays visible even with no results.

Opening issue evidence carries the filtered list URL. The issue, ownership editor and action form retain it across validation and successful saves. Review-list links, including CVSS, vendor-priority and missing-score badges, retain search/category/severity/pagination when opening a guided case or original evidence; guided step navigation, assessment saves and the guided risk-link save retain the return path. Review-category navigation retains severity, and organization pagination retains category.

Ratings opened from a guided case or an evidence page keep the original validated list destination instead of nesting return URLs. Direct case links without list context remain direct.

Return destinations are limited to local issue/review/intelligence lists and known query keys. They grant no access: every destination rechecks current organization/evidence authorization. Arbitrary external redirects and nested return destinations are rejected.

## Other improvements

- Company-map review links open the exact review-record list rather than an unrelated default case category. Missing versions in compact company inventory explicitly remain uncertain.
- Assigned IP addresses appear in issue evidence and guided cases as well as review lists. Preview loading is batched for lists and limited to 16 assignments per host; foreign-organization/source assignments stay excluded. They are labeled **IP addresses / network**, without implying that every assignment is primary. Retained missing assignments are marked last-known.
- The **Assess** workflow link consistently opens the organization's vulnerability evidence view (or the authorized global review list).
- Product research shows version fields only for the chosen rule. Without JavaScript, every field remains available and server validation still applies. Search criteria continue to use POST and are not added to return URLs.
- National loading placeholders do not offer Retry before failure. Existing timeout/error retry behavior and no-JavaScript direct section links remain.
- Dates on the reviewed overview, national, research, guided and issue routes use the configured display timezone and numeric format. Live lookup counters use the same date order.
- Small overview explanations have increased text size. Compact cards, filters and research fields adapt to narrow screens.

## Validation and limits

Use synthetic local fixtures for browser validation. No live records, source endpoints or notification delivery settings are changed. SQLite supports local functional checks; PostgreSQL relational/concurrency checks require an available local PostgreSQL instance. Browser observations on a local synthetic dataset do not establish production load times, mobile-network performance or full accessibility conformance.

Validated locally on 2026-11-23:

- Frozen dependencies installed; local migrations applied; Django system checks and migration-drift check passed. No schema changes introduced.
- Full Django suite: **1027 tests, OK, 66 skipped** (SQLite, one worker). Local-network test fixtures ran with the required local execution permissions and a canonical temporary directory.
- Ruff and JavaScript syntax checks passed.
- Browser checks at **390 × 844** and **1440 × 1000**: no page-level horizontal overflow; version-rule field switching, group-filter submission and list/detail return paths verified on synthetic local fixtures. Screenshots retained as local review artifacts.
- PostgreSQL validation was not run because Docker Desktop was manually paused. No production migration, deployment or live-record edits were performed.

CVSS badge follow-up validated on 2026-11-24: **109 relevant Django tests passed, 1 skipped** on SQLite, including score/vendor/missing-score badge click-throughs, evidence anchors, original-filter return, repeated badge clicks and rejected external return targets. Frozen dependency sync, local migrations, Django checks, migration-drift check and Ruff passed. A local browser round trip on synthetic Log4j data returned to the exact same category/search/severity/page URL both directly and through a guided case. No live records or deployment were changed.
