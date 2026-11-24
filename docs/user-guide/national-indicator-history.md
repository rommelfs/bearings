# National indicator history

Under the live national indicators, **Indicator history** offers three collapsed
Vitrine charts: review stocks, inventory stocks and coverage gaps. Open a chart,
use its legend to hide larger series when scales differ, and inspect exact daily
values and capture windows in its accessible table. One observed day appears as
points; a line develops as more days are recorded. Missing days are actual gaps.

## What is recorded

The existing `refresh_national --watch` worker records each company's clean,
source-backed national counters normally hourly (sooner after date or policy
generation changes). The latest successful capture of
a local calendar date replaces that day's earlier capture. Previous dates are
retained. Today is provisional; these are per-company observations, not a
simultaneous end-of-day census. Dirty or failed summaries are never saved as zero.
Source health and verified response-contact coverage are sampled at capture time.

- **Review stock:** outstanding review items, saved analyst-confirmed affected
  reviews, companies with open reviews, Critical source-severity reviews and
  accepted-risk reviews. These retain the live counter definitions. Accepted risk
  remains open; resolved/false-positive/not-affected reviews are excluded. A review
  count does not prove that an installed package is vulnerable or lacks a fix.
- **Inventory stock:** active assets and recorded installations. These are records
  in permitted inventory, not unique national machines or a complete census.
- **Coverage gaps:** unknown installed versions, companies without a current
  verified response contact, stale/disabled or missing sources, import errors and
  synthetic/development sources. Synthetic data is not operational evidence.

Recording starts after migration and worker update. Earlier totals cannot be
reconstructed from today's inventory or review-event history. No backfill,
interpolation, forward-fill or invented zero is used. A measured zero is displayed
as zero, while missing/incomplete/withheld dates are labelled. Renderer failure
leaves the server-rendered daily values available. The displayed timezone defines
the date buckets; a timezone change does not mix old buckets into the new series.

## Current permissions and comparable dates

Stored counters are company-owned, with separate operator and shareable-evidence
review totals. Every historical read uses current organization/role policy and
chooses the corresponding audience. A date is displayed only when every company
in the currently permitted cohort has an authorized capture for that date.
Missing companies or pending captures therefore produce a gap, not a low total.
Adding/removing companies can change historical comparability: this is a current
permitted cohort, not a fixed historical population or a retrospective census.

Bulk evidence-sharing changes, relevant ownership/lineage transfers and raw source
resets rotate a per-company UUID policy generation inside the writing transaction.
Old observations are retained but conservatively withheld after these changes;
they are never silently reinterpreted with today's narrower policy. Newly captured
points use the new generation. Normal version, severity and workflow changes do
not erase historical observations. Current organization joins and generation
checks also prevent raw resets/reused numeric IDs from revealing previous scope
history. Platform-admin access does not bypass a historical-generation mismatch.

## Updating and operation

On the Ubuntu deployment, after checking out the reviewed release:

```sh
cd /opt/bearings &&
./deploy/ubuntu24/manage.py migrate --noinput </dev/null &&
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null &&
./deploy/ubuntu24/manage.py refresh_national --limit 500 </dev/null &&
systemctl restart bearings-web bearings-national
```

Migration **0067** adds retained daily observations, policy generations and
PostgreSQL bulk-write/truncate guards. The worker continues capturing after the
initial bounded pass; on large cohorts, complete coverage can take several batches.
No Linux client rebuild/restart or ordinary `bearings-worker` restart is needed.
No new timer or upstream connection is required. Refresh the browser after update.

Check `systemctl status bearings-national` and its journal if captures do not
appear. `refresh_national` reports separately how many clean company observations
it captured. Web GETs never create snapshots. No upstream API calls, scans or
notifications are performed by capture. Failure retains the last successful
observations; dates without successful captures stay missing. PostgreSQL is
required for recording and policy/locking guarantees; SQLite is not a historical
capture backend.

These tables are retained history, not disposable derived caches. Ordinary
national-summary rebuilds preserve them; there is no automatic history pruning.
Include them in database backups and size retention operationally. Reversing the
migration would discard this newly recorded history and is not a routine rollback.
