# NetBox: multiple instances and explicit capabilities

Status: **multi-instance connections, scoped paginated imports/queries and recoverable writes implemented**. Live integration is verified against the bundled official NetBox v4.7.3 / netbox-docker 5.1.1 image using scoped v2 Bearer tokens. Other deployed versions and authentication configurations still need validation. The separate `sync_netbox` importer projects all four supported types and retains missing objects for explicit review. Development mode remains a separately labeled synthetic adapter.

An organization has one authoritative infrastructure source binding. The platform can query many instances and many tenant-scoped bindings on a shared instance. Results from organization-owned instances are not copied into central NetBox. Read-write capability authorizes portal writes to that instance only; it does not introduce bidirectional synchronization between instances. Multiple simultaneous authoritative inventories within one organization are not part of this increment.

## Operator configuration

1. Create a **NetBox instance** in platform administration: name, approved HTTPS base URL (no credentials/query/fragment), credential environment-variable name, authentication scheme, enabled flag and access mode. Access defaults to `read_only`; choose `read_write` explicitly where authorized. Only platform superusers can edit these fields. Permission changes are audited.
2. Give each connection a least-privilege credential, injected securely into a `NETBOX_*TOKEN` variable such as `NETBOX_CENTRAL_TOKEN` or `NETBOX_ACME_TOKEN`. The database holds the variable name only. Missing credentials never fall back to another instance's key. Rotate a key or its reference without changing source identity. In proxy-backed environments authorize the binding for the exact destination; never copy placeholder values into database fields.
3. Select `Bearer` for current tokens or `Token` for a deployed legacy contract; test the selected scheme against the chosen NetBox release. Keys may have upstream restrictions stricter than Bearings' capability; a local read-write setting never overrides upstream denial. Use an upstream read-only key for read-only connections as defense in depth.
4. Bind the organization's **InventorySource** to the instance in `central` or `external` mode. Shared instances (no dedicated organization) require an explicit tenant ID. Every returned record must match it. Whole-instance scope is permitted only if the instance was explicitly dedicated to that same organization before binding. A dedicated instance cannot be assigned to another organization. Missing tenant assignments on objects are excluded from tenant-scoped queries.
5. For writes, configure site, role and device-type IDs on that instance. Provision a writable/filterable text custom field `bearings_id` on devices and virtual machines. Read-only queries require none of these write fields. Current writes create/recover devices or VMs; arbitrary updates and deletes are not implemented.
6. Approve network destinations separately. With cloud proxy DNS, add each exact hostname to `CONNECTOR_ALLOWED_HOSTS` and the environment egress policy. Private/VPN destinations require the instance's `allow_private` approval plus deployment networking rules. TLS verification, no redirects, 15-second timeouts and bounded JSON responses remain enforced. Do not install a separate VPN client.

Instances and bindings have stable UUIDs. Imported identity is instance/binding, object type and external ID; the same numeric ID in two instances is distinct. Bound endpoint/dedicated ownership cannot be repointed in admin. Bindings with existing assets cannot change their instance or tenant. A migration needs explicit reconciliation; a hostname change must not silently rewrite identity. Credentials and permission modes can be rotated/revoked without repointing identity.

## Capability matrix

| Operation | Read only | Read and write |
| --- | --- | --- |
| Scoped GET queries: devices, VMs, IP addresses, prefixes | yes | yes |
| Portal submission / external create and recovery | denied | allowed for editors/admins |
| Queued writes after a downgrade to read only | denied before any external request | allowed while authorized |
| Local software/contact workflows | normal membership policy | normal membership policy |
| Automatic import / disappearance reconciliation | not implemented | not implemented |

A disabled instance permits no connector requests. The connector reloads instance capabilities before an operation so a cached instance object cannot bypass a downgrade. Calls already in flight when an operator revokes access cannot be retroactively cancelled; revoke upstream credentials and egress too when immediate containment is needed. Read-write permits only the create/recovery workflow currently implemented, not unrestricted NetBox administration.

## Query runner and health

```sh
DJANGO_DEBUG=1 uv run python manage.py query_netbox --all
DJANGO_DEBUG=1 uv run python manage.py query_netbox --source "<binding-uuid>" --source "<another-binding-uuid>" --object-type devices
DJANGO_DEBUG=1 uv run python manage.py query_netbox --all --object-type virtual-machines --object-type ip-addresses --object-type prefixes
```

The operator-only command uses GETs exclusively on both access modes. It reports counts by source UUID and updates separate last-read attempt/success/error state and an audit event. It continues other bindings after one fails, then exits nonzero if any failed. It does not print raw operational records or credentials. Query health records success for the requested types only; it is not proof of a complete refreshed local inventory.

`query_objects(source, object_type)` returns source/instance/type/external-ID provenance and the untrusted raw record for the separate importer. Offset pagination requests 100 records per page, caps at 100 pages and 10,000 records per type/binding, rejects changing counts, duplicates, missing pages and wrong tenants, and reconstructs requests rather than following supplied links. Continuations must retain the exact destination, path, tenant scope, limit and next offset. Cursor/count-null pagination and server limits incompatible with this contract fail closed. A complete query is not an atomic upstream snapshot; concurrent edits preserving count may still require later reconciliation. Partial/error queries never update projections; the importer accepts a validated empty complete response only as a missing-object review signal, never a deletion instruction.

## Write recovery

Portal submissions persist as pending with an InventoryWrite job. `process_jobs` checks current connection capability, queries the selected instance using tenant plus `cf_bearings_id`, rejects partial/ambiguous results, and creates only when the complete filtered result is empty. Devices use that instance's defaults; VMs use their own endpoint and the configured site default, required by the tested NetBox version. Lifecycle active/retired maps to NetBox active/offline. A returned object must match the tenant (where scoped) and custom identity.

Lost POST responses are retried with a lookup before another POST. Local job row locks prevent duplicate local workers; NetBox custom-field uniqueness is not guaranteed, so out-of-band duplicates require review. Errors and permission downgrades leave the write visibly failed/unconfirmed with capped retry backoff and retain last-known data. No external request is made when the connection is read only or disabled. No response bodies or credentials enter job error state. Read success and write success are shown separately.

## Upgrade from singleton configuration

Run committed migrations. Existing development sources are unchanged. Existing `central` sources retain all local assets and identities but have no instance assignment, so writes/queries fail closed until an operator configures and assigns the intended instance. An initial assignment to a previously unbound legacy source is allowed; moving an already-bound source is not. Migrations do not read or copy secret values or silently enable write access.

The old global `NETBOX_URL`, `NETBOX_ALLOW_PRIVATE`, and site/role/type settings are no longer used. Move their non-secret values into the instance record. You may reference an existing `NETBOX_TOKEN` variable explicitly for its intended instance, or create distinct named bindings. Review per-instance permissions and scope before retrying old jobs.

## Inspected contracts and remaining work

Official references inspected 2026-10-16: [REST pagination/API examples](https://github.com/netbox-community/netbox/blob/main/docs/integrations/rest-api.md) and [device serializer](https://github.com/netbox-community/netbox/blob/main/netbox/dcim/api/serializers_/devices.py). Current REST examples use Bearer authentication; legacy token mode remains explicit. Latest documentation is a starting contract, not a tested deployed-version guarantee.

Validate both read-only and read-write keys against isolated live instances before operational use. Periodic import/projection, disappearing-object review and freshness thresholds are implemented; see [synchronization](../operations/synchronization.md). Strong upstream snapshot consistency, monitored production scheduling, broader topology, connection onboarding UX and reviewed source migration workflows remain future work.

## Bundled starter

`python3 scripts/dev.py up` installs/runs the isolated NetBox alongside Bearings and provisions scoped read/write and read-only connections with verified local TLS. `configure` plus `up --external` selects another instance without starting bundled NetBox services. See [development stack](../operations/development-stack.md) for accounts, certificate trust, data retention and external configuration. The bundled initializer verifies its known synthetic seed identities; the running worker additionally performs general GET-only inventory imports.
