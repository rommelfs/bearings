# 0004: Bundled development environment with external mode

Status: Accepted, 2026-10-16.

Provide a Docker Compose starter containing Bearings, its PostgreSQL database and durable job worker, plus the pinned official NetBox image, its own PostgreSQL/Valkey, and a local HTTPS gateway. Python's standard library orchestrates the starter so contributors need only Python and Docker Compose on the host. Synthetic tenants demonstrate independently scoped read-only and read-write credentials.

Generate passwords, tokens and a private local certificate authority in ignored files or Docker volumes. Keep verified TLS, separate credential references and upstream permissions. Bootstrap must preserve existing passwords, policy revocations and identities. Synthetic starter projection is explicitly distinct from general inventory import.

External mode starts only Bearings services and stores a separate database identity for each endpoint/scope/capability configuration. Require an explicit tenant or dedicated-instance scope, default to read-only, prompt privately for the token and support a supplied CA. Never provision external NetBox data during startup. Stop the previous helper-managed stack when switching, retain volumes, and never silently repoint existing source identities.

The cost is a larger first download and startup, plus retained volumes that users must manage explicitly. Native SQLite development remains available. The stack is a local development environment, not a production deployment recipe. Validate actual API authentication, TLS, scoped queries, worker acknowledgements and restart behavior in integration CI.
