# 0005: Atomic source-scoped NetBox inventory projection

Status: Accepted, 2026-10-16.

Project all four supported NetBox types into the existing Asset model, keyed by source/type/external-ID. Keep upstream metadata allowlisted and separate from local assessments, software and findings. Network addresses are inventory, not proof of authority or a cross-source identity.

Commit each complete four-type traversal atomically, retaining previous data on any failed page/schema/identity check. Hold a source row lock shared with write workers; use an inner savepoint so failure health commits under that same lock. Reconcile pending writes only with a confirmed same-source bearings_id. PostgreSQL supports concurrency; SQLite remains single-worker.

Absence marks a retained missing-object review candidate. Changed permissions or reassignment can produce valid empty results, so never infer deletion. Reappearance keeps identity and clears the current missing marker. Import/query/write health stay distinct; source freshness and bounded pagination are explicit.

Use an interval and durable queued-refresh flag on InventorySource, with a single-pass operator command and automatic development-worker loop. This provides repeatable polling without adding a queue service; monitored production scheduling, upstream transactional snapshots and broader topology remain separate work. Inventory views/API are paginated for imported datasets.
