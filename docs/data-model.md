# Data model

| Entity | Ownership and purpose |
| --- | --- |
| Organization / Membership | Platform identity separate from users; one user may have different roles in several organizations |
| NetBoxInstance | Operator-owned endpoint, credential reference, auth scheme, default-deny read/write capability, dedicated/shared ownership and write defaults |
| InventorySource | One authoritative binding per organization; stable UUID, instance, mode, tenant scope, separate query/write attempt/success/error state |
| Asset / InventoryWrite | Local submission/projection plus durable pending external write; external identity is unique within source and object type |
| Product / Installation | Organization-local product name and original supplied CPE/PURL; installation records version, edition, build, and OS designation on an asset |
| InfrastructureClaim | Declared/verified/disputed/expired responsibility, method/reviewer/time, assignment interval and network context; overlaps permitted |
| Contact / ContactToken | Role/scope, language/time zone, escalation, channels, secure communication, three independent review concepts; hashed one-use 24-hour tokens |
| SourceRecord | Organization-scoped raw record, source identity and source-specific ID, ingestion time, conservative default redistribution denial |
| Finding | One review relationship per installation/record/rule; category, confidence, priority, automated applicability, independent analyst assessment, workflow, provenance times |
| FindingHistory | Actor, previous/new workflow and analyst applicability, reason and timestamp; original evidence unchanged |
| AuditEvent | Policy/configuration changes, reads by operators, inventory/contact/claim/finding actions |

Source and instance identity and original IDs are preserved. Query results carry both UUIDs. The separate importer upserts Asset identities for devices, VMs, IP addresses and prefixes, tracking allowlisted upstream_data, inventory_seen_at, missing_since and explicit missing-review state. Source import attempt/success/error/summary and scheduling fields are distinct from read-query and write health. CVE-only retrieval is supported initially; aliases and source-specific identifiers need a canonical identity layer before expanding beyond this adapter. Product identifiers are stored as manual assertions, not authoritative normalization or affectedness. Version blank means unknown.

`full_clean` checks cross-organization foreign keys in service paths, and all views scope foreign object IDs. Django's `save()` does not automatically validate models: importers must validate and authorize explicitly. Database uniqueness prevents duplicate identities, memberships, records, and findings, but multi-column tenant integrity does not yet have database-level triggers/RLS. Direct SQL/ORM scripts and superusers are trusted administrative boundaries.

Migrations are committed. Evidence/finding/time fields form the initial correlation slice; a separate general observation and many-to-many relationship model is still planned for MISP/Plum Island. Asset fields do not yet cover all network/service topology. Contact role review history is in the audit log; complete escalation/delivery workflow is planned. No evidence expiry or retention deletion job exists yet; operator retention policy is an open decision.
