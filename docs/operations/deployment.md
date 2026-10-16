# Local deployment and production prerequisites

Use README for host-based development. `docker compose up --build` starts PostgreSQL 17 and the local Django development server; web and DB published ports bind to loopback only. Compose embeds a clearly local-only DB password and is not a production deployment. `docker compose down` preserves its database volume; `down -v` destroys it, so never run that against valuable data. No external service is needed for the synthetic slice.

Environment settings are operator-owned. `.env.example` contains placeholders only. Host-based Django does not auto-load `.env`; export variables or use a trusted environment manager. Docker Compose reads its own environment interpolation, but organization users cannot supply process configuration. Freeze dependencies using `uv sync --frozen`; no migration is silently generated at startup.

For a long-running host session, start web with `DJANGO_DEBUG=1 uv run python manage.py runserver 127.0.0.1:8000` and invoke `process_jobs` periodically in a second shell. `remind_contacts` is a once-per-schedule reminder preparation command. Processes must restart after cloud restoration. Retained `.local/` files, `.venv/`, and Postgres volume are separate from runtime processes. The saved cloud startup instructions cover this distinction.

Before production: choose an approved WSGI server and reverse proxy/TLS configuration; DEBUG off, strong secret key from secret storage, explicit hosts, HTTPS and secure cookie/HSTS policy, rate limits including token redemption, SSO/MFA/account lifecycle, outbound allowlist and DNS-rebinding protection, least-privilege database/connector roles, retention/privacy policy, audit export, monitored scheduling, backup/restore exercise, and security review. `manage.py check --deploy` must be reviewed under actual deployment settings. The current Dockerfile serves local development only and no production readiness is claimed.

The application rejects startup without a secret key unless DEBUG is explicitly on. It uses secure cookies outside DEBUG. `PGSSLMODE` configures PostgreSQL transport (local default prefer; use verified TLS appropriate to your deployment). HTTP connector certificates are verified. Do not disable TLS verification or package integrity checking.

In this cloud sandbox Docker configuration must be writable: set `DOCKER_CONFIG=/workspace/.cache/docker`. Cloud image builds also require the platform's existing proxy and trust bundle, without baking either into the image:

```sh
uv run python scripts/cloud_image_build.py
```

The helper forwards Docker's transient proxy arguments, resolves the existing proxy host into the build namespace, and mounts the CA through an optional BuildKit secret. This preserves certificate verification without embedding proxy credentials or CA files in image layers. An ordinary Docker host can use plain `docker build` / Compose. Pass approved proxy/CA configuration to a runtime container separately if live connectors are needed; none is embedded in the local image. Never use insecure TLS flags to solve trust failures.
