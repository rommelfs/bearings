# Company inventory request performance

The company page used to render every visible CVE, complete source payload, review form and history entry even when the browser opened `#inventory`. An HTML fragment does not restrict server-side work. With one synthetic asset, 1,000 installations and 1,000 reviews, the request issued 2,031 queries, produced 2,043,846 bytes and had a 7.2104s median. Most cost was rendering, plus 1,000 history queries and 1,000 actor lookups.

The page now aggregates authorized workflow counts once and links to the dedicated review workspace. It does not select CVE payloads or histories or render per-CVE forms. Inventory remains paged at 50 assets with ten software previews each; contacts and scope declarations have independent 25-row pages preserving the other section selections. Asset status is projected from JSON without loading each entire NetBox snapshot; package display omits unused report/network/service blobs. Request-local findings authorization is reused without a cross-request cache.

Initial fixes reduced the same single-asset request to 29 queries, 18,604 bytes and 0.2997s median. A signed-agent case with 1,000 actual projected packages and 1,000 reviews measured 29 queries, 21,510 bytes and 0.2109s median. These are separate synthetic local request measurements, not production latency guarantees.

A larger case with 101 assets, 100,900 installations and 10,000 reviews exposed a second issue: the installation review-count query joined the whole inventory through column-to-column ownership conditions. PostgreSQL selected a nested-loop plan traversing 100,900 rows for a page containing no matching reviews, costing about three seconds despite a bounded result. The count now uses the concrete authorized installation/company IDs from callers that already require matching asset/product organizations; finding and raw-source organization checks remain. No planner settings or permission caches are weakened.

After that query fix the larger case measured **0.3863s median, 26 queries and 349,771 bytes**, versus 3.6803s immediately before the count fix. The returned first page remains bounded to fifty assets and five hundred installation previews. Fresh bulk-loaded statistics were intentionally retained rather than hiding the bad plan with ANALYZE. Regression tests check query/response growth, no payload/history selection, raw intelligence visibility, independent section pagination and a preserved source binding. See [raw measurements](company-inventory-20261120.json).

No production records, SMTP, scans, NetBox writes or database schema were changed by this performance validation. This addresses company-page rendering; it is not a new fleet ingestion/publication throughput acceptance. Standard detailed asset/CVE views retain their own pagination and authorization.

## Direct inventory links and host evaluation — 25 November 2026

The organization document now delivers inventory independently of the host
attention cohort. Opening the existing `#inventory` link expands the inventory
section and skips the background host request. The normal company landing page
loads the host panel independently. Explicit host filters, sorting and pagination
retain a full-page path that also works without JavaScript. The panel applies
current company scope and has a separate unavailable state and retry path.

On the retained **48,000-asset PostgreSQL** fixture, five warm authenticated
requests measured a median of **42.4 ms** for the company document,
**174.2 ms** with synchronous host evaluation requested, and **109.7 ms**
for the separate panel. With an eight-second synthetic delay deliberately
injected into host evaluation, the synchronous response took **8,180 ms**
and the company document **56 ms**. Chromium reached the open inventory in
**439 ms** with that delay in place. It issued the host request only when
the user explicitly opened the panel. These measurements isolate the effect
of the split. The source of the reported production latency remains unverified.

The company response reports numeric company, inventory and render times in
`Server-Timing`. The scale runner measures the company document and host panel separately.
The host response reports its own duration. Deploy
with the usual source update and `collectstatic` to publish `company-hosts.js`.
