# Bearings

A standalone organization inventory and evidence review portal intended for CIRCL operation. It connects inventory ownership, emergency contacts, infrastructure authority claims, and technology relevance without equating a match with compromise.

**Status: first runnable development increment, not production-ready.** No operational data is included. The existing repository is `rommelfs/bearings`; no additional repository is needed. This is a public open-source project licensed under [GNU AGPL v3.0 or later](LICENSE) (`AGPL-3.0-or-later`).

## Implemented

- Django authentication, multi-organization memberships (administrator, editor, reader), CIRCL analyst group, and operator-controlled visibility (default deny).
- Organization and authorized CIRCL dashboards; versioned, session-authenticated read APIs with the same isolation rules.
- Emergency contacts, substantive review, configurable review intervals, separate reachability and emergency availability, expiring one-use verification tokens, and deduplicated review reminders in a **local file mail sink**.
- Infrastructure declarations and operator verification, overlapping assignments, historical validity, IPv4/IPv6/range/domain matching, and private-network context isolation.
- Durable manual inventory submissions, a labeled development adapter, multi-instance NetBox connector with explicit read-only/read-write capabilities and a write adapter with pending/failed/confirmed state and read-before-retry reconciliation. Source/object/external-ID identity is distinct from an address.
- Organization-local product selection, manual product identifiers, operating system/software installations, unknown versions, CVE retrieval for explicit review, evidence records, finding deduplication, analyst applicability overrides, workflow reasons, and audit history.

**Not yet implemented:** continuous NetBox import/refresh, MISP and Plum Island adapters, automatic applicability/version matching, full vulnerability alias resolution, source-specific redistribution policy evaluation, complete organization-owned NetBox inventory imports, active scanning, production notifications, SSO/MFA, public deployment, or a production job scheduler. See [backlog](docs/backlog.md).

## Start with bundled NetBox (recommended)

Requires Docker Engine/Desktop with Compose v2.24+ and Python 3.10+ on the host. Application dependencies run in containers; no local uv/PostgreSQL/NetBox installation is needed. Allow about 6 GB of Docker memory and 10 GB of disk space. Images support AMD64 and ARM64, including Apple Silicon. First startup can take several minutes while NetBox migrates its database.

On macOS, install Docker Desktop (`brew install --cask docker`), launch it (`open -a Docker`), complete its first-run setup and wait for the engine to run. Verify `docker info` and `docker compose version` in your terminal. If the app is already installed but `docker` is missing, check Docker Desktop’s CLI/PATH settings.

From your checkout:

```sh
python3 scripts/dev.py up
python3 scripts/dev.py credentials
```

Bearings runs on loopback port **8000**, bundled NetBox on **8443 (HTTPS)**. The credentials command displays the generated **local-development** password: use `company-admin`, `circl-analyst`, or `platform-admin` in Bearings, and `netbox-admin` in NetBox. Existing passwords are not reset. Databases, secrets and demo inventory persist across restarts.

The lab includes two tenant-scoped NetBox connections: read/write and read-only, with synthetic devices, VMs, IPs, prefixes and local software installations. A background worker processes portal submissions automatically. These are real NetBox API connections to synthetic local data, separate from the existing fixture-only Example Labs workspace. NetBox cookies use distinct names so both applications can stay logged in.

Bearings automatically trusts the generated local NetBox CA. To use the NetBox browser interface, export its **public** CA with `python3 scripts/dev.py trust` and trust that certificate locally in your browser/OS. Private CA keys are not exported and verification is never disabled. See the [development stack guide](docs/operations/development-stack.md).

```sh
python3 scripts/dev.py query        # live GET queries and connection health
python3 scripts/dev.py smoke        # bundled-only synthetic writes and retry checks
python3 scripts/dev.py down         # stop containers; retain all data
```

### Use an existing NetBox instead

Replace the example URL and tenant ID with your approved instance. The API token is prompted without echo and stored outside Git.

```sh
python3 scripts/dev.py configure --url https://netbox.example.org --tenant-id 42
python3 scripts/dev.py up --external
```

External mode is **read-only by default** and starts no bundled NetBox, Redis/Valkey or NetBox database services. For a dedicated organization-owned instance, explicitly use `--dedicated` instead of a tenant ID. Options cover legacy authentication, private destinations, custom CA certificates, HTTPS ports and explicit read/write capability. Switching modes stops the previous lab and retains its volumes; each external endpoint/scope/access mode gets a separate development database. Initialization never provisions external NetBox; the worker processes authorized pending submissions only for read/write connections.

External queries currently report counts and health; general inventory import/reconciliation is still planned. Only the bundled synthetic seed objects are projected into the portal automatically. [Configuration and lifecycle details](docs/operations/development-stack.md).

## Run Bearings directly (without bundled NetBox)

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and optionally Docker for PostgreSQL. Run these commands from your existing checkout directory, the one containing `manage.py`. No `/workspace` path is needed on your own machine.

```sh
uv sync --frozen
export DJANGO_DEBUG=1
# Use a random DJANGO_SECRET_KEY for anything beyond an isolated local session.
uv run python manage.py migrate
# Enter a password of at least 12 characters when prompted (input is hidden).
# Start the server only if seeding succeeds.
uv run python manage.py seed_demo && uv run python manage.py runserver 127.0.0.1:8000
```

`seed_demo` asks for a password (12+ characters) and creates `company-admin` and `circl-analyst` only if absent. Existing passwords and operator policies are preserved. All seeded data is synthetic, including the evidence record. `--no-users` is available for noninteractive checks. Create a separate platform administrator with `uv run python manage.py createsuperuser`; demo users have no platform administration privileges.

Sign in as `company-admin` for the organization view or `circl-analyst` for the CIRCL view, using the password you entered during seeding.

If seeding reports `CommandError: Use at least 12 characters`, the transaction rolls back and no demo accounts are created by that attempt. Rerun `uv run python manage.py seed_demo` with a longer password before starting the server. If accounts already exist from an earlier successful run, seeding leaves their passwords unchanged; reset a forgotten password with `uv run python manage.py changepassword company-admin` (or `circl-analyst`). Do not delete the database to fix a login problem.

Use the existing checkout. Cloud tasks already run in isolation; do not create worktrees unless explicitly requested. No live process is assumed to survive a restored cloud snapshot.

Run durable inventory writes and prepare reminders in a separate shell:

```sh
export DJANGO_DEBUG=1
uv run python manage.py process_jobs
uv run python manage.py remind_contacts
```

Commands run once. For local continuous processing, run `while uv run python manage.py process_jobs; do sleep 10; done`. SQLite supports one worker only. Reminders and verification messages are written under `.local/mail/`; they are **never sent to real companies**. Tokens are submitted on the contact verification page. The message does not establish authority or emergency availability.

### Multiple NetBox instances

Platform administrators register each NetBox instance under `/admin/` with its HTTPS endpoint, token environment-variable **name**, authentication scheme, and read-only (default) or read-write capability. Bind each organization to its authoritative instance. Shared instances require tenant-scoped bindings; querying a whole instance requires an explicit dedicated-organization assignment. Use a least-privilege key for each instance. No credentials are stored in the database.

```sh
# After operator configuration and secure credential injection:
uv run python manage.py query_netbox --all
uv run python manage.py query_netbox --source "<binding-uuid>" --object-type devices --object-type virtual-machines
# Also supported: --object-type ip-addresses and --object-type prefixes
```

This is a GET-only query runner for both connection modes. It reports counts and per-binding query health, never raw records or keys. It does not yet import results into local inventory or reconcile missing objects. Queries paginate within the approved endpoint/scope and fail closed on partial/ambiguous results. Read-only instances reject portal asset submission and queued external writes; local software records remain editable according to membership. See [NetBox setup and migration](docs/integrations/netbox.md).

For PostgreSQL, use `docker compose up -d db`, export `DATABASE_URL=postgresql://bearings:local-development-only@127.0.0.1:5432/bearings`, then rerun migrations. The Compose password is intentionally local-only. `docker compose up --build` additionally runs the local web application. See [deployment](docs/operations/deployment.md).

## Verify

```sh
DJANGO_DEBUG=1 uv run python manage.py check
DJANGO_DEBUG=1 uv run python manage.py makemigrations --check --dry-run
DJANGO_DEBUG=1 uv run python manage.py test
uv run ruff check .
uv run ruff format --check .
```

Tests use isolated databases and synthetic service responses. For PostgreSQL, run the same commands with `DATABASE_URL` set; a test database creation privilege is needed. CI runs both database backends. `/api/v1/organizations/<slug>/inventory/`, `/findings/`, and `/findings/<id>/evidence/` require a login session. These APIs are read-only. All HTML writes use CSRF protection.

Live vulnerability retrieval is opt-in through the inventory UI: select an installation and a CVE ID. The adapter fetches the CVE JSON 5 record from Vulnerability-Lookup and persists a review relationship. It **does not claim the product is affected**. Network access to `vulnerability.circl.lu` is required; live retrieval was validated in this instance. Cloud proxy-only DNS additionally needs `CONNECTOR_PROXY_DNS=1` (see the integration document). No key is required for this public read. The demo finding uses `fixture://...`, never a fabricated live response.

## Documentation

- [Architecture](docs/architecture.md), [data model](docs/data-model.md), [authorization](docs/authorization.md), [correlation](docs/correlation.md)
- [NetBox](docs/integrations/netbox.md), [Vulnerability-Lookup](docs/integrations/vulnerability-lookup.md), [MISP](docs/integrations/misp.md), [Plum Island](docs/integrations/plum-island.md)
- [Company guide](docs/user-guide/companies.md), [CIRCL guide](docs/user-guide/circl.md)
- [Development stack](docs/operations/development-stack.md), [deployment](docs/operations/deployment.md), [backup/restore](docs/operations/backup-restore.md), [synchronization](docs/operations/synchronization.md), [incident handling](docs/operations/incidents.md)
- [Licensing](docs/licensing.md), [public-license decision](docs/decisions/0002-license-and-public-development.md)
- [ADR](docs/decisions/0001-modular-monolith.md), [open decisions](docs/decisions/open.md), [backlog](docs/backlog.md), [validation record](docs/validation.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [agent instructions](AGENTS.md)
