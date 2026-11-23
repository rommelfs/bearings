# CIRCL national overview and confidential inventory research

CIRCL analysts and trusted platform administrators have a **National overview** entry at the top of the navigation and the Bearings brand link. Open `/circl/`. The existing `/` Infrastructure overview remains available for company-by-company status and its existing login/diagnostic routes remain stable. Company accounts cannot open the CIRCL overview, findings list or research endpoint.

## Read the reporting picture

The overview covers **companies the current user may access**, through explicit operator visibility or ordinary membership. It is not a complete census of Luxembourg or national market-share measurement. Every request applies current organization/source/evidence visibility; counts and trends can change when access is revoked. Synthetic/development source counts and the existing demo banner identify fixture inventory.

- **Confirmed affected reviews, unresolved:** a review records affectedness and is not resolved/false-positive/not-affected. This describes missing recorded remediation, not verified absence of an installed patch.
- **Companies with outstanding reviews** and **Critical source severity:** show company reach and technical source severity separately from company business risk. Critical is not an assertion of exploitation.
- **Accepted-risk reviews:** remain outstanding; acceptance is not patching. The indicator reflects review workflow state, not a new risk approval or a guarantee that acceptance is still valid.
- **Cross-company vulnerability follow-up:** prioritize advisories with outstanding reviews at more than one permitted company and at least one saved analyst-confirmed affected review. This flags a follow-up candidate, not universal affectedness or an automatic outreach decision. Single-company and unconfirmed cases stay in a collapsed **Technical checks** section. Up to twelve advisory priorities are shown, follow-up candidates first, then source severity; each has at most two concrete installation examples with software/version, company/server, advisory description, saved assessment and a direct evidence link. Several evidence sources may create several reviews for an installation; review counts are not deduplicated server counts.
- **Automatic package checks and next steps:** examples reuse current vendor-version proof, with a vendor-listed fix only where explicitly supported. An installed fix produces a retained-review reconciliation step, not an update alert. Changed inputs or stale vendor data withhold a previous result and request reevaluation. Missing version proof stays unconfirmed. Saved analyst decisions and risk acceptance remain separate and are never overwritten. Repository availability/entitlement and local exploitability are not inferred. Missing examples or pending prepared data remain explicit.
- **Most widespread software versions:** top twelve by distinct reporting companies, then installation count. Exact names/identifiers are grouped case-insensitively; aliases are not automatically equated. Unknown versions are explicit. **Find installations** sends criteria in a POST to the research form.
- **Coverage:** active assets, installations, unknown versions, current verified response-contact gaps, stale/disabled/missing inventory sources and import errors. Empty review lists do not establish safety or complete software coverage. The company infrastructure page retains detailed monitoring/coverage actions.

Auto-refresh starts enabled at 60 seconds and defers while the tab is hidden or an input is being edited. The page performs local aggregate reads; it does not refresh source services or deliver messages.

## Research without a CVE

Open **Research a product or version · no CVE needed**, or `/circl/research/`.

1. Enter a product name or identifier, choosing text containment or exact identity text. These are inventory candidates; names alone do not establish vendor identity or affectedness.
2. Choose all recorded versions, an exact recorded version (including vendor strings such as `2019 CU12`), or a plain release SemVer range. Range minimum is inclusive and maximum exclusive; use three-part releases such as `1.9.0` / `2.0.0`. Vendor suffixes, prereleases and missing versions are not silently compared.
3. Search local inventory. Separate counts and the **Show** selector expose matching versions, unknown versions and non-comparable range versions. A range spanning more than 500 distinct version strings is refused with a request to refine; no partial result is presented as complete.
4. Follow company/asset/installation links and the assigned contact/team. An assigned contact is not automatically verified reachable; the company contact record retains channel and role-review status. Results are paginated in groups of 25; Next/Previous retain the criteria in POST bodies.

A product/version match does not create a CVE, finding, risk assessment, campaign or affectedness decision. Review the exact build, configuration, entitlement and source evidence with the company before deciding treatment.

## Confidential information, including TLP:RED context

The research form is transient and local. Enter inventory criteria, **not advisory text**. It can be used by an authorized recipient to investigate an early product/version report before a public CVE exists. This is not a TLP advisory repository or a new recipient/sharing policy: authorization to handle and redistribute the source report remains separate from inventory read access.

Criteria are not placed in application URLs, sessions or saved advisories; GET query parameters are not used to initiate research. Requests perform no external service lookup. All CIRCL pages use private/no-store responses and same-origin referrer policy: same-origin CSRF-protected forms work, while external sites receive no referrer. Application audit entries record the operator read, without the query, report text or result set. The Django request-log filter also redacts CIRCL query strings, including accidentally supplied GET criteria; bundled Nginx already logs only the URI path. Source-level POST-body capture by independently configured infrastructure is outside this application's transient research implementation.

Research has no auto-refresh or automatic notification. A reviewer must use the existing explicit outreach/case workflows for subsequent coordination; source audience restrictions still apply there.

## Interpret trends

The thirty-day Vitrine chart shows **first product-watch evidence records** (the earliest immutable DiscoveryRevision for each review) and **recorded transitions to Resolved**. It does not count repeated source refreshes as new discoveries or repeated Resolved-to-Resolved history as another resolution. Seven-day totals compare the most recent week with its preceding week. Daily values are available in an accessible table; dates use the configured application timezone.

Current visibility and active-inventory constraints apply to the underlying findings. Distribution-package discovery histories and manual/imported reviews without first product-watch evidence do not become invented historical discoveries. These are recorded workflow events, not exploitation, verified patch-installation or historical national backlog curves. Historical version-adoption trends require periodic inventory snapshots; they are not inferred from the current version table.

[Desktop overview](../images/circl-overview-1440.png) · [Mobile overview](../images/circl-overview-390.png) · [Local research](../images/circl-research-1440.png)

## Performance diagnostics

Update with `python3 scripts/dev.py up --no-build`; startup now applies migrations before restarting the retained Python processes. Migration 0028 adds indexes for first discovery history and closure status/time. The activity query starts from discovery matches and selects each first immutable revision through its index, instead of scanning every refresh as a candidate event. Current organization/evidence visibility and watch/product/record lineage remain enforced.

`python3 scripts/dev.py web-timing --national` authenticates the existing bundled CIRCL SSO identity and prints sanitized numeric response timings, including `nationalcounts`, `nationalversions`, `nationalvulns` and `nationaltrend`. No queries, credentials or research criteria are printed. Compare repeated samples on the affected machine. A separate synthetic PostgreSQL test with 27,000 findings and 270,000 history revisions measured 2.03–2.22 seconds before and 0.51–0.73 seconds after; this is not a promise of national population capacity or the affected environment’s latency.

## Company map and heatmap

The overview now includes a separately loaded, offline [company severity map](circl-map.md), approximate Luxembourg postal/place lookup, explicit manual positioning, severity colors, optional heat overlay and exact scoped problem links. Unlocated companies and coverage limits remain visible. No company addresses leave the application. A map point describes the company location, not physical server locations.

## Independent bounded sections

The National Overview document now performs only authentication/navigation/audit work. Summary/coverage, vulnerability ranking, version prevalence and history load independently from `/circl/panels/{summary,problems,versions,activity}/`; the map remains independent. A failed section clears its old data, shows an unavailable/missing-data message and offers **Retry section**. Other sections remain usable. Missing results never display as zero findings. Direct section links are available with JavaScript disabled. Every fragment enforces current role/organization/evidence policy and private/no-store responses; no shared response or authorization cache is introduced.

PostgreSQL fragment work has a 3-second per-statement timeout and 8-second section budget checked between executes; an in-flight final statement may finish up to three seconds after the section budget. Previous database settings are transaction-local/restored, including nested transactions and cancellation. SQLite remains a local single-worker fallback without PostgreSQL statement cancellation. The client has a 12-second section timeout. These bounds isolate bad queries rather than proving that every underlying aggregate is fast.

After `git pull` and `python3 scripts/dev.py up --no-build`, `python3 scripts/dev.py web-timing --national` measures the lightweight document and each data section/map separately. HTTP failures report a numeric status and available numeric server timings; network/timeouts have a separate sanitized reason. No response bodies, SQL, passwords or customer fields are printed. This replaces the former undifferentiated “failed during national” message. Please use affected-environment results to locate a remaining slow section.

### PostgreSQL planning overhead

National panel and map requests locally set PostgreSQL `join_collapse_limit` and `from_collapse_limit` to 4 alongside the existing local JIT setting. This bounds join-order planning of the current authorization/evidence queries without changing their filters, results or the section timeouts. Settings restore after success, nested use and cancellation; other requests retain their original settings. There is no shared authorization or response cache. Use `python3 scripts/dev.py web-timing --national` after updating/restarting to measure the actual environment.

## Deploying the follow-up presentation

After updating the reviewed checkout, run `./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null`
and `systemctl restart bearings-web`, then refresh the browser. This change adds no
migration and needs no worker/client restart. Live and prepared national queries
use the same priority ordering; concrete examples are reread under current policy
in one bounded database query, never fetched from an upstream service.

## Interactive time series

Vitrine charts now have a date axis, integral daily event counts, named series,
hover/keyboard values and a chart/table toggle. The server-rendered **Daily values**
table remains usable without JavaScript or when the chart engine fails. National
activity refreshes retain the same authorization and prepared-data coverage rules.
No historical open-vulnerability backlog or software adoption curve is inferred.
Zero means no matching event retained, not a healthy system or complete coverage.

Two company-specific graphs are available in collapsed sections:

- **Evidence / vulnerability detail → Review decisions over time**: confirmed,
  resolved and reopened status transitions for the current visible review filter,
  across all pages. Repeating the same status is not a new transition. A reopened
  confirmation can appear in two series. Resolution does not attest installed fixes.
- **Linux inventory reports → Report activity over time**: receipts by server
  receipt date, split by their current applied/pending/rejected/superseded status.
  Opening a device restricts the graph to that device; otherwise it covers company
  devices with consistent current source/asset lineage. Statuses of past receipt
  cohorts can change after processing. Reports are not unique servers and do not
  establish inventory completeness, uptime or delivery success before admission.

All graphs cover the last 30 local calendar dates including today; the timezone
and endpoints are shown. Future events are excluded from the company graphs.
Current source visibility applies retrospectively; deleted/missing histories
cannot be reconstructed. First evidence histories do not include all manual or
vendor-package discoveries, so the national discovery series is explicitly
labelled **First product-watch evidence**.

The pinned Vitrine chart and Apache ECharts/ZRender engine are served locally
with retained licenses/provenance. Charts load lazily on opening/visibility, with
no runtime CDN or external analytics. Update the reviewed checkout, run
`./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null`, restart
`bearings-web`, and reload the browser. No migration, worker or client restart
is needed. npm is used only to reproduce vendored artifacts during maintenance.

## Historical indicator stocks

The live indicator and coverage cards now have an independent **Indicator history**
section with Vitrine stock charts. These use newly recorded daily company
observations, separate from workflow-event charts. Previous totals are not
reconstructed. Missing or restricted/incomplete dates remain gaps; exact values
and capture windows follow in accessible tables. See [indicator history](national-indicator-history.md)
for audience rules, sampling, migration 0067 and the required `bearings-national`
restart. Unlike the earlier event-chart presentation change, this feature requires
a database migration and an updated national worker.

## Visual orientation

Navigation, indicator cards and workflow steps now use consistent labelled
pictograms. Historical charts have prominent icon tiles, a short description and
**View chart / Hide chart** action rather than a small text-only disclosure. The
controls retain native keyboard behavior and do not change indicator meanings.
See [interface navigation](interface-navigation.md) for accessibility and updating.
