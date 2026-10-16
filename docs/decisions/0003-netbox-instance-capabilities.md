# ADR 0003: Multiple NetBox instances with explicit capabilities

Status: accepted for implementation. Date: 2026-10-16.

The owner requires querying many NetBox instances, with some read only and others read/write. A global endpoint/token cannot provide safe instance identity, credential isolation or different capabilities.

Introduce operator-owned NetBoxInstance connection records, with stable UUIDs, approved endpoints, server-side credential references, explicit authentication scheme, read-only default, optional read-write capability and disabled state. One instance may serve several organization source bindings through explicit tenant filters. Whole-instance access requires dedicated organization ownership. Keep one authoritative infrastructure source per organization. External connections are not duplicated into central NetBox and instances never synchronize bidirectionally.

Capability is independent of central/external topology. Where explicitly configured read/write, the existing portal create/recovery workflow may write to that authoritative instance; read-only mode denies it at both portal/service and connector/job boundaries. Upstream key permissions remain an independent limit. No arbitrary update/delete API is exposed.

Queries support complete bounded offset pagination for devices, VMs, IPs and prefixes and preserve source-instance identity. They initially return data to connector callers and report query health/counts through an operator command, without importing local inventory. Full projection refresh/reconciliation remains a separate increment. Existing singleton bindings fail closed after migration until explicitly assigned; no credentials are migrated into database fields.
