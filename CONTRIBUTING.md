# Contributing

This repository is in an initial implementation phase. Licensing and public contribution terms remain unresolved; discuss intended contributions with the repository owner before assuming an open-source license.

Follow README quick start. Use `uv sync --frozen`; add dependencies through uv and commit lockfile changes. Include migrations for model changes. Use synthetic data only. Keep changes small and runnable, and update relevant documentation in every commit that changes behavior.

Before submitting: run Django tests/checks, migration drift checks, and Ruff formatting/linting. Authorization changes need negative tests across organizations, roles, operator policies, and evidence visibility. Connector changes need contract fixtures and explicit tests for partial/failure responses, identity, retries, and idempotency. Do not run tests against production services or message real organizations. Read AGENTS.md and the integration/runbook documents.

Use logical commits describing behavior. Report the test commands and actual outcomes in pull requests. Mark remaining limitations explicitly. GitHub milestone/issue definitions are kept in `docs/backlog.json`; the publication script is idempotent by title.
