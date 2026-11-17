# CIRCL national overview and confidential inventory research

CIRCL analysts and trusted platform administrators have a **National overview** entry at the top of the navigation and the Bearings brand link. Open `/circl/`. The existing `/` Infrastructure overview remains available for company-by-company status and its existing login/diagnostic routes remain stable. Company accounts cannot open the CIRCL overview, findings list or research endpoint.

## Read the reporting picture

The overview covers **companies the current user may access**, through explicit operator visibility or ordinary membership. It is not a complete census of Luxembourg or national market-share measurement. Every request applies current organization/source/evidence visibility; counts and trends can change when access is revoked. Synthetic/development source counts and the existing demo banner identify fixture inventory.

- **Confirmed affected reviews, unresolved:** a review records affectedness and is not resolved/false-positive/not-affected. This describes missing recorded remediation, not verified absence of an installed patch.
- **Companies with outstanding reviews** and **Critical source severity:** show company reach and technical source severity separately from company business risk. Critical is not an assertion of exploitation.
- **Accepted-risk reviews:** remain outstanding; acceptance is not patching. The indicator reflects review workflow state, not a new risk approval or a guarantee that acceptance is still valid.
- **Vulnerabilities needing coordination:** prioritize Critical/High source severity, affected review counts and company reach. Follow a record or indicator to the paginated cross-company list, then its exact original review, installation and company. Several evidence sources may create several reviews for an installation; the review count is not a deduplicated server count.
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

The thirty-day chart shows **first automated evidence records** (the earliest immutable DiscoveryRevision for each review) and **recorded transitions to Resolved**. It does not count repeated source refreshes as new discoveries or repeated Resolved-to-Resolved history as another resolution. Seven-day totals compare the most recent week with its preceding week. Daily values are available in an accessible table; dates use the configured application timezone.

Current visibility and active-inventory constraints apply to the underlying findings. Manual/imported reviews without first automated evidence do not become invented historical discoveries. These are recorded workflow events, not exploitation, verified patch-installation or historical national backlog curves. Historical version-adoption trends require periodic inventory snapshots; they are not inferred from the current version table.

[Desktop overview](../images/circl-overview-1440.png) · [Mobile overview](../images/circl-overview-390.png) · [Local research](../images/circl-research-1440.png)

## Performance diagnostics

Update with `python3 scripts/dev.py up --no-build`; startup now applies migrations before restarting the retained Python processes. Migration 0028 adds indexes for first discovery history and closure status/time. The activity query starts from discovery matches and selects each first immutable revision through its index, instead of scanning every refresh as a candidate event. Current organization/evidence visibility and watch/product/record lineage remain enforced.

`python3 scripts/dev.py web-timing --national` authenticates the existing bundled CIRCL SSO identity and prints sanitized numeric response timings, including `nationalcounts`, `nationalversions`, `nationalvulns` and `nationaltrend`. No queries, credentials or research criteria are printed. Compare repeated samples on the affected machine. A separate synthetic PostgreSQL test with 27,000 findings and 270,000 history revisions measured 2.03–2.22 seconds before and 0.51–0.73 seconds after; this is not a promise of national population capacity or the affected environment’s latency.
