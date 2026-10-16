# Architecture and current boundaries

Bearings is a Django modular monolith with a relational database (PostgreSQL target, SQLite local fallback), server-rendered interface, and session-authenticated `/api/v1/` read API. It consumes upstream services rather than modifying them. [ADR 0001](decisions/0001-modular-monolith.md) records the stack decision.

`portal/models.py` holds the initial domain; `access.py` centralizes policy; `scope.py` implements pure address/domain rules; `services.py` owns domain transactions; `connectors/` contains thin HTTP adapters; `views.py` scopes every request before loading objects. Templates render escaped data. These modules can become separate Django apps when boundaries warrant it; no microservices, search cluster, or graph database is introduced.

An organization has exactly one source binding. In central mode NetBox owns infrastructure; local assets are unconfirmed submissions or last-known projections. Software installations, claims, contact reviews, findings, and workflows belong to Bearings. Source binding UUID, object type, and external ID identify imported objects; IPs are not identities. Source bindings include a tenant mapping but tenant assignment does not grant application access.

The development source is an explicit fixture backend. It records synthetic external IDs and must never be presented as successful NetBox integration. External organization-owned NetBox is a planned read-only inventory authority; do not duplicate its inventory into central NetBox or introduce bidirectional sync.

`InventoryWrite` is the durable background-job/outbox entry. PostgreSQL row locking serializes a job across workers; retries use capped backoff. `process_jobs` executes at most 100 due items per invocation. Production scheduling is not included. The reminder command locks each organization and deduplicates by contact and review due date. Network outages retain all local data. No deletion/reconciliation importer exists yet.

Operator-owned settings are server environment and platform administration: visibility policies, membership/source bindings, tenant mapping, connector URLs/tokens, review interval, database, and future delivery policy. Organization forms cannot modify these. File-mail delivery is deliberately fixed in code until operational messaging is authorized.

Production outbound requests require an operator egress allowlist in addition to application checks. URLs are HTTPS, operator-configured, disallow embedded credentials and redirects, and reject non-global DNS results unless NetBox private access is explicitly approved. DNS validation alone does not prevent DNS rebinding; upstream names must be controlled and deployment egress restrictions enforced. Organization-supplied connectors are blocked until stronger approval controls exist.

Cloud proxy-only DNS is explicitly opt-in through `CONNECTOR_PROXY_DNS=1`, requires an existing HTTPS proxy and an exact `CONNECTOR_ALLOWED_HOSTS` match, and delegates destination DNS/policy enforcement to that approved proxy. Private IP literals remain blocked unless explicitly approved for NetBox. This avoids unsupported direct DNS in the cloud without weakening TLS or exposing caller-controlled destinations. Direct-network mode retains DNS/address checks.
