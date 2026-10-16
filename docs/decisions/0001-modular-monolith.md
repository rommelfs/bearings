# ADR 0001: Django modular monolith with relational persistence

Status: accepted for the initial development increment. Date: 2026-10-16.

The repository was empty and supplied no competing stack constraints. A maintainable organization-isolated workflow needs authentication, forms, migrations, relational constraints, and operator administration before complex intelligence processing.

Use Python 3.12+, Django 5.2 LTS and PostgreSQL 17 as the deployment target. SQLite is an explicit single-worker local fallback. uv manages exact dependencies in `uv.lock`. Server-rendered HTML avoids a second application stack; `/api/v1/` provides a versioned read surface. Thin HTTP adapters isolate upstream formats from services. A database-backed inventory outbox and periodic management commands avoid adding a broker before a demonstrated workload requires it.

Consequences: small operational footprint, transactional workflows, mature framework protections and accessible local setup. PostgreSQL is necessary for concurrent row-lock behavior. The current app is not an HA worker platform, scheduler, production notification system, or universal vulnerability matcher. Introduce separate Django apps, broker/scheduler, richer normalization or indexing only with measured need and an ADR.
