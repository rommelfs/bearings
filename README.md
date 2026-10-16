# Bearings

A standalone organization inventory and evidence review portal intended for CIRCL operation. It connects inventory ownership, emergency contacts, infrastructure authority claims, and technology relevance without equating a match with compromise.

**Status: first runnable development increment, not production-ready.** No operational data is included. The existing repository is `rommelfs/bearings`; no additional repository is needed. Licensing is undecided; no license grant is implied.

## Implemented

- Django authentication, multi-organization memberships (administrator, editor, reader), CIRCL analyst group, and operator-controlled visibility (default deny).
- Organization and authorized CIRCL dashboards; versioned, session-authenticated read APIs with the same isolation rules.
- Emergency contacts, substantive review, configurable review intervals, separate reachability and emergency availability, expiring one-use verification tokens, and deduplicated review reminders in a **local file mail sink**.
- Infrastructure declarations and operator verification, overlapping assignments, historical validity, IPv4/IPv6/range/domain matching, and private-network context isolation.
- Durable manual inventory submissions, a labeled development adapter, central NetBox write adapter with pending/failed/confirmed state and read-before-retry reconciliation. Source/object/external-ID identity is distinct from an address.
- Organization-local product selection, manual product identifiers, operating system/software installations, unknown versions, CVE retrieval for explicit review, evidence records, finding deduplication, analyst applicability overrides, workflow reasons, and audit history.

**Not yet implemented:** continuous NetBox import/refresh, MISP and Plum Island adapters, automatic applicability/version matching, full vulnerability alias resolution, source-specific redistribution policy evaluation, organization-owned NetBox, active scanning, production notifications, SSO/MFA, public deployment, or a production job scheduler. See [backlog](docs/backlog.md).

## Quick start

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and optionally Docker for PostgreSQL.

```sh
cd /workspace/bearings  # or your checkout
uv sync --frozen
export DJANGO_DEBUG=1
# Use a random DJANGO_SECRET_KEY for anything beyond an isolated local session.
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver 127.0.0.1:8000
```

`seed_demo` asks for a password (12+ characters) and creates `company-admin` and `circl-analyst` only if absent. Existing passwords and operator policies are preserved. All seeded data is synthetic, including the evidence record. `--no-users` is available for noninteractive checks. Create a separate platform administrator with `uv run python manage.py createsuperuser`; demo users have no platform administration privileges.

Use the existing checkout. Cloud tasks already run in isolation; do not create worktrees unless explicitly requested. No live process is assumed to survive a restored cloud snapshot.

Run durable inventory writes and prepare reminders in a separate shell:

```sh
export DJANGO_DEBUG=1
uv run python manage.py process_jobs
uv run python manage.py remind_contacts
```

Commands run once. For local continuous processing, run `while uv run python manage.py process_jobs; do sleep 10; done`. SQLite supports one worker only. Reminders and verification messages are written under `.local/mail/`; they are **never sent to real companies**. Tokens are submitted on the contact verification page. The message does not establish authority or emergency availability.

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
- [Deployment](docs/operations/deployment.md), [backup/restore](docs/operations/backup-restore.md), [synchronization](docs/operations/synchronization.md), [incident handling](docs/operations/incidents.md)
- [ADR](docs/decisions/0001-modular-monolith.md), [open decisions](docs/decisions/open.md), [backlog](docs/backlog.md), [validation record](docs/validation.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [agent instructions](AGENTS.md)
