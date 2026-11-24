# Host-first organization overview

Organization pages now start with **Which hosts need attention?**, using live, authorized evidence instead of showing inventory synchronization as a security status. The complete retained inventory, contacts, infrastructure declarations, sharing/settings and existing workflow links remain in an expandable administration section. Search/pagination of those sections still works and opens that section when selected.

## What is implemented

- Active hosts use the existing machine-kind and source/organization consistency contract. Assigned addresses, inactive inventory and other objects remain in the full inventory. No records or assessments are deleted.
- Four quick filters show active hosts, hosts with problems/reviews, evaluation gaps, and hosts with documented vendor fixes. Search affects the totals; quick filters narrow that cohort. Lists paginate at 25 hosts and sort in the database before pagination; all five headings work, with accessible direction indicators and mobile sort controls.
- Priority uses current positive distribution version evidence and explicit standalone asset-issue priority. The more urgent explicit category sorts first, with source evidence winning ties. Badges state **source** or **asset issue**; review-only task priority is labeled **Review needed**, never inferred Medium severity. Saved affected assessments and manual applicability reviews remain separate. No calculated local risk score or exploitation claim is introduced.
- Package counts deduplicate installation identities rather than multiplying CVE/advisory rows. Currentness reuses the live proof/input/feed contract. Changed inventory, expired/revoked agents, new definitions and stale/missing evaluation remove current priority/fix claims immediately. A current partial result remains partial.
- Application gaps include missing/disabled source watches, pending/failed/stale discovery, unknown versions and stale/missing reported application entries. Up to three scoped application examples link to their exact product discovery view. Distribution packages keep their separate vendor evaluation path. No CVE match is not proof of safety.
- A vendor-fix count requires a current affected verdict plus an explicit vendor fixed-version note bound to the same satisfied strict version comparison. This is the existing evidence-detail contract, evaluated inside SQLite/PostgreSQL before filtering/counting. Unrelated notes, inclusive bounds, malformed data and string booleans cannot supply a fix. Repository candidates, update availability, entitlement and overall update backlog remain **not checked**; collection of those facts is planned work.
- Last active report time is visible, with the exact configured display timezone available in the time label/tooltip. Missing/stale reports remain explicit. No unverified last-known OS becomes a confirmed current evaluation.
- Asset and review evidence links retain the original validated host search/filter/sort/page destination. External/nested return URLs remain rejected. Every destination rechecks authorization; restricted evidence is omitted from counts, priority and fixes.

## Reading style

The approved **stronger text + reading font** is the default across the application. Body/control/table text uses the local system font stack, dark foreground `#15232d`, secondary text `#354954` and stronger text links `#17445a`. Headings and branding retain bundled Raleway. Semantic priority/status colors stay separate. A stylesheet version change refreshes cached CSS; no external font service is used.

## Bounds and failure behavior

Only page-sized host scalar fields, one OS entry and three gap examples per host are hydrated. Full proofs, source payloads and review history are not rendered into the list. Summary counts are reused for pagination. Existing query/HTML-size limits remain in the tests.

An actor's analyst-group read is reused only within this read-only view/render using a context-local scope. It is not stored on the user, session or global cache; actor identity is checked, scope is restored on exit, and the next request rechecks revocation. Organization membership and operator visibility remain query predicates.

PostgreSQL queries retain local JIT/planning/timeout protections. On a timeout/unavailable database, the host section shows a retry explanation instead of zero/healthy counters; the existing inventory remains available. Source/network ownership, sharing, human decisions, notifications and external integrations are unchanged.

## Validation

Local frozen dependencies, migrations/system checks, migration drift and Ruff pass. The full SQLite suite passes 1,051 tests (66 skipped); targeted host/inventory/navigation tests also pass after the final bounded gap preview. Browser verification uses only isolated synthetic data. PostgreSQL and CI results are recorded on the pull request. No live deployment or production-data edits were performed.

## Update an existing native Ubuntu server

Back up the PostgreSQL database and protected configuration/state using the existing [backup procedure](../operations/backup-restore.md). This PR adds no database migration, dependencies or service units. The normal migration command below is idempotent and also handles previously pending migrations.

The following installs the pull-request branch for review; use the PR's reviewed exact commit when pinning a deployment. Run as an operator with sudo. The script stops on the first error and refuses local changes. Investigate a failure before reactivating workers; do not rerun first installation or reset data/secrets.

```bash
sudo bash -e <<'SH'
cd /opt/bearings
if [ -n "$(git status --porcelain)" ]; then
  echo 'Local changes exist; preserve/reconcile them before updating.' >&2
  exit 1
fi
git fetch origin refs/heads/codex/host-overview
host_revision=$(git rev-parse --verify 'FETCH_HEAD^{commit}')
systemctl stop bearings-web bearings-worker bearings-national
git checkout --detach "$host_revision"
/opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12
./deploy/ubuntu24/manage.py migrate --noinput
./deploy/ubuntu24/manage.py collectstatic --noinput
./deploy/ubuntu24/manage.py check --deploy
systemctl restart bearings-web bearings-worker bearings-national
systemctl is-active bearings-web bearings-worker bearings-national
git rev-parse --short HEAD
SH
```

Restart the three Bearings services shown above. Nginx, NetBox, the database and client enrollments need no change for this increment. Allow Gunicorn to finish starting, then open the organization's host overview and hard-reload the browser (`Ctrl+F5` / `Cmd+Shift+R`). Verify the darker reading text, priority ordering, quick filters, explicit missing evidence and return-to-list links. A service being active alone is not proof of HTTP readiness; investigate persistent 502 responses using the existing journals/proxy logs.

For an existing development Compose lab, fetch/check out the reviewed revision and run `python3 scripts/dev.py up`; the starter applies migrations and restarts/waits for the application workers. Do not run development bootstrap/seeding on the native production server.
