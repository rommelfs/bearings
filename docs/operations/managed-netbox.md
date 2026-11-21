# Managed NetBox inventory for the CIRCL service

Bearings distinguishes operator-enabled **managed NetBox registration** from a customer's existing **read-only inventory**. Enabling managed registration is a platform operation, not a permission granted by a rollout secret. Existing rollout codes retain their original observed-only mode; issue a new code after enabling managed inventory. No API change or client rebuild is required.

## Concrete native CIRCL plan

1. Keep the retained CIRCL organization, authoritative source, native tenant, API identity and credential reference. Check the private native receipt and current non-admin service permissions; refuse an ambiguous host, changed endpoint/tenant, disabled service or altered native policy.
2. Provision only the retained tenant's Device/VM view/add/change capabilities, no delete and no network-allocation writes. Preserve token value, expiry, account password, groups and human SSO/roles. Add only narrowly scoped reference-data read access. Native reference objects explicitly say **Unspecified**; they do not claim a physical location, manufacturer or hardware model.
3. Convert the existing observed LXC host to a **VM** with the explicit **lxc** tag. Use its existing Bearings UUID as `custom_fields.bearings_id`; never adopt an upstream machine by hostname. Keep device key, local asset UUID, software/installations, findings and assessments.
4. Queue a policy-guarded write and reconcile by UUID on retry. An existing external ID whose UUID binding disappeared cannot cause a replacement POST. Tag updates preserve other tags; a requested virtualization tag is added only after the current tenant/UUID/ID are validated.
5. Read the exact scoped NetBox record back, verify UUID/tenant/tag, run the existing complete GET-only import, then verify the same asset/device/software/review identities in Bearings. Repeat apply is idempotent. Verification does not restart services or grant capabilities; it does update the local import/audit records.

Virtualization is separate from the VM/device kind. Supported explicit tags are `lxc`, `incus`, `proxmox`, `vmware`, `kvm` and `hyperv`. Additional tags and a physical host/cluster relationship remain NetBox/operator data; they are not inferred from a hostname, an IP address or a package inventory.

## Native installation commands

Back up the existing database and private configuration. Update the reviewed source using the normal stop/migrate/collectstatic/check/restart procedure, including **migration 0063**. This migration preserves all existing fleet codes as **observed-only** and leaves managed registration disabled by default.

On bearings.circl.lu, as root:

```sh
cd /opt/bearings
python3 deploy/ubuntu24/ecosystem.py manage-circl-inventory --host bearings.circl.lu --kind vm --virtualization lxc
python3 deploy/ubuntu24/ecosystem.py manage-circl-inventory --host bearings.circl.lu --kind vm --virtualization lxc --apply
python3 deploy/ubuntu24/ecosystem.py manage-circl-inventory --host bearings.circl.lu --kind vm --virtualization lxc --verify
```

The first command is a non-mutating plan. `--apply` explicitly provisions the managed native capability and registers/verifies that existing Bearings host. The host must exist exactly once in the retained native source and have an active enrolled device. A previously confirmed external object cannot silently change between physical-device and VM inventory. Private credentials remain in the existing root-owned receipt/environment; stdout contains only non-secret verification metadata. Do not run the original first-install or connection-creation command to replace a retained source.

Success reports `uuid_match`, `tenant_match`, `import_match` and `agent_software_reviews_preserved` as true, with the confirmed NetBox object ID. Check **Virtualization → Virtual machines**, the CIRCL tenant, the hostname, `bearings_id` and `lxc` tag in NetBox; Bearings offers the direct authoritative record link after successful reconciliation. An unconfirmed write stays failed/pending with the same UUID. Repeating the same operation recovers an accepted POST with a lost response instead of creating a second host.

After enabling managed inventory, open the company's **Automatic Linux registration** page and create a **new** limited rollout code. Choose VM plus the declared virtualization type, or the appropriate physical host type. New clients use the same central installer and signed enrollment/report protocol; the worker registers the host in the configured tenant. Old observed-only codes keep recording only in Bearings. Revoking managed policy, disabling/read-protecting the connector or revoking the device prevents pending managed writes. Native API credentials remain tenant-scoped independently of Bearings checks.

## Boundaries

Host registration alone leaves reported interface/IP information as a declaration in Bearings. The separately enabled inventory exporter below adds scoped native interfaces/IPs and a structured software snapshot; CVE/human-review records remain in Bearings. This does not invent a NetBox software-inventory plugin. Hostnames are not identity proofs and existing external machines without the UUID marker are not silently adopted. No patches, probes, emails or changes to customers' existing read-only connectors are performed.

The native helper validates the retained receipt and fails closed on changed users, credentials, native permissions or owned reference records. The native database transaction is atomic; a subsequent Bearings failure can leave the explicit native managed capability provisioned but the host unconfirmed. Preserve the receipt and retry/inspect rather than resetting identities or replacing sources. Native token expiry and later renewal remain operational lifecycle work.

## Validation

Local acceptance uses the real pinned NetBox over verified HTTPS and an explicitly synthetic isolated tenant. It checks retained-host promotion, tag visibility, same-UUID import, repeated apply/verify, signed automatic registration/reporting for an Incus VM and a physical host, lost enrollment acknowledgement recovery, preserved software, foreign-tenant rejection and denied deletion. Independent native NetBox ORM queries verify one object per UUID and the expected tags. The normal bundled NetBox/FlowIntel/RT/RTIR smoke is rerun; no production host or credential is touched. Production acceptance occurs when the operator runs the commands above and inspects their receipts.

## Reported inventory export (migration 0064)

Managed host registration can now be extended to recurring inventory export. This is explicit per **authoritative source**, independently of read/write connector capability. An existing read-only customer connection is never silently upgraded.

| Client evidence | NetBox representation |
| --- | --- |
| Host / VM and declared virtualization | Native Device / VirtualMachine and tags |
| Currently reported addressed interfaces | Native Interface / VMInterface, linked to the confirmed host |
| Configured unicast IPs and subnet lengths | Native IPAddress, assigned to the interface in an explicitly selected VRF |
| OS, kernel, software package/binary names, exact versions, runtime observations | JSON custom field `bearings_inventory` on the host, labeled **Bearings reported inventory** |
| Observation dates, device/source/asset UUIDs, report references | In the same structured inventory, with a Bearings detail URL and export receipt |

Software is exported, not merely linked. NetBox has no built-in full Linux package inventory model: the JSON field provides the complete bounded current component list without requiring an inventory plugin. It is not a separate native object per package and does not duplicate private CVE intelligence or human assessments. Export is capped at 5,000 current components / 1.5 MB; oversized snapshots fail visibly instead of silently truncating. MAC, MTU, unaddressed/down interfaces, CPU/RAM, physical host/cluster relationships and authoritative patch attestation are not collected by this client and are not invented.

### Native CIRCL activation

After normal backup, migrate/collectstatic/restart to the reviewed release:

```sh
python3 deploy/ubuntu24/ecosystem.py manage-circl-inventory --export-inventory --apply
python3 deploy/ubuntu24/ecosystem.py manage-circl-inventory --export-inventory --verify
./deploy/ubuntu24/manage.py process_netbox_exports --limit 2
```

The explicit extension provisions a retained **tenant-owned VRF with enforced address uniqueness**, narrowly scoped Interface/VMInterface/IPAddress view/add/change permissions and the typed custom fields. It preserves the existing native service/token/expiry and validates its retained permission receipt on repeat. The global IP table is not guessed as the target. The native verification checks retained provisioning/host binding and configured policy; export completion is separate and visible on the Bearings asset page. Check NetBox's host Interfaces tab, the assigned IP in the configured VRF, and its **Bearings reported inventory** custom field. A successful host registration alone is not proof that inventory export succeeded.

Every newly accepted report queues a separate bounded worker export. The current Linux client adds an optional signed `host` field to reports, refreshing addresses on each collection. Deploy server support before rebuilding/publishing/upgrading clients using the existing central artifact workflow. Older clients remain accepted: software is exported, but enrollment-time network declarations are labeled with their original observation time and are not written to native IPAM once older than 12 hours. A client update is needed for recurring fresh network observations. Collection still makes no DNS/external-IP lookups or network probes.

### Customer-owned NetBox / configurable RW access

1. The platform operator creates an approved `NetBoxInstance` with the customer's HTTPS API endpoint, optional browser URL, dedicated organization or shared-tenant scope, separate `NETBOX_CUSTOMER_*TOKEN` environment reference, supported Token/Bearer scheme and explicit `read_write` capability. Token values remain in protected server configuration. The destination must pass the existing HTTPS/allowlist/private-network policy; per-customer input never creates arbitrary outbound URLs.
2. Bind that organization's one authoritative `InventorySource` to the instance and tenant using operator administration. Existing bound endpoint/tenant identities are immutable; this is setup for an unbound source, not permission to repoint an existing CIRCL source. Configure site/role/device-type defaults for new physical hosts and approved virtualization tag IDs if needed. Current read-only customers can keep import-only operation.
3. The customer's NetBox administrator provisions text custom field `bearings_id` on Device, VirtualMachine, Interface, VMInterface and IPAddress, and JSON custom field `bearings_inventory` on Device/VirtualMachine. Grant only the intended service account the required host/interface/IP view/add/change permissions, plus exact reference/VRF/tag reads. Constrain hosts by tenant, interfaces by parent tenant and IP writes by tenant plus chosen VRF. No delete or prefix allocation is required. Enable uniqueness on the tenant-owned VRF. The upstream permissions are an independent boundary, not replaced by Bearings filters.
4. Plan, then explicitly apply source-owned export (replace the illustrative source UUID and VRF ID with reviewed actual values):

```sh
./deploy/ubuntu24/manage.py configure_netbox_export --actor platform-admin --source SOURCE_UUID --vrf VRF_ID
./deploy/ubuntu24/manage.py configure_netbox_export --actor platform-admin --source SOURCE_UUID --vrf VRF_ID --apply
```

For a pre-existing imported host that already has an explicitly bound client, add `--bind-asset ASSET_UUID` to the plan/apply command. This authorizes setting an absent `bearings_id` on that exact source's already-confirmed external object. It never searches by hostname, creates a replacement host or overwrites a different UUID; unrelated custom fields remain. This is a per-host first-binding action, not recurring inventory work. Existing child interfaces/IPs still require separate reviewed ownership reconciliation.

`--inventory-only` exports OS/software/provenance without native interface/IP creation; `--disable --apply` revokes recurring export without deleting remote objects or changing the endpoint/token. The command requires a platform superuser, preserves source/tenant/credentials and rejects a foreign VRF, non-unique VRF or read-only/disabled connector. It also enables managed host registration for **new** fleet codes; existing observed-only codes keep their original mode. External NetBox custom fields/native permissions remain a customer-admin preparation step; Bearings never uses their administrative credential to grant itself access.

### Conflicts and limits

All writes recheck current source policy, device expiry/revocation, observation freshness, connector mode and exact host UUID/tenant/ID. Each created interface/address has a deterministic ownership marker. Existing unmarked interfaces or addresses, different assignment/tenant/VRF, ambiguous results or a changed host marker fail explicitly; they are not adopted by hostname or overwritten. Linking an already imported host does not by itself authorize adopting all existing unmarked child objects. Those associations need an explicit reviewed reconciliation workflow; automatic child adoption is not implemented.

There are no remote deletions, address moves, primary-IP changes, guessed DNS names, prefix allocations or writes to location/role/topology chosen in NetBox. Missing or down interfaces/IPs remain for review. The current collector reports only up interfaces with eligible addresses; absence is not a decommission instruction. A partial upstream failure can leave a subset created; retries recover by stable markers and validated parents. NetBox uniqueness and conflict refusal prevent duplicate/foreign IP claims. A dedicated tenant VRF is required for native IPAM export; global/multi-VRF mapping needs a separate explicit policy extension. A process-level 60-second request budget bounds one export (an in-flight transport timeout may extend the wall time). Failed exports retain their previous receipt and show a sanitized reason with a deferred retry, separately from host-registration health. Whole-fleet sustained export throughput is not established by two local hosts.

## Later move from CIRCL NetBox to a customer-owned instance (planned)

Prepare this as an **export/import migration**, not bidirectional replication or an endpoint edit beneath existing IDs:

1. Read a complete source snapshot for only the customer's tenant: hosts/VMs, owned interfaces, IPs/VRFs, software/provenance custom fields and required reference relationships. Include a manifest, source identity, schema version and hashes; exclude API tokens, unrelated tenants, private intelligence and internal reviews.
2. Preview the destination mapping for tenant, VRFs, sites, roles, hardware types, platforms, clusters and tags. Names are suggestions, never identity. Detect pre-existing UUID markers, address/VRF conflicts, unsupported models and incomplete source visibility before writing.
3. Import in dependency order with the customer's scoped RW credential, durable per-object receipts and stable Bearings UUIDs. Record old-to-new native object IDs because IDs differ between installations. Repeated runs must reconcile by UUID and stop on conflicting ownership.
4. Pause the source's import/export during a final delta and verify the destination from both APIs: identities, counts, relationships, software versions, IP scopes and retained local device/software/review links. Perform one explicit audited authoritative-source migration, preserving client keys and preventing two active writers. Retain the previous source receipt for rollback; do not delete CIRCL objects automatically.

This migration executor and its preview UI are **not implemented** by the inventory-export change. Their own reviewable acceptance tests and explicit target authorization are required before moving a real customer's inventory. The new export schema/UUID provenance support that future work without claiming that host/IP export is already a complete NetBox-to-NetBox migration tool.

### Network reports missing despite current software reports

The original Linux unit allowed only AF_UNIX/AF_INET/AF_INET6. Go enumerates local
interfaces through AF_NETLINK, so that sandbox prevented network collection even
with the newer binary. Software-only reports remained valid and enrollment-time
addresses were deliberately not refreshed or exported as current evidence.
The corrected unit permits AF_NETLINK without adding capabilities or root access;
network enumeration failures now appear in the client journal. The installer upgrades
only the exact previous reviewed unit hash, preserving identity, private queue,
service activation state and operator drop-ins; arbitrary edited units remain refused.
Rebuild/publish client artifacts and rerun the existing central installer, then check
a fresh report and the export receipt. Actual target systemd/NetBox acceptance is
separate from local regression tests.

Local validation for this correction: Go unit tests, eight unprivileged installer
tests, disposable installer containers (real file/account/TLS/signature checks,
controlled systemctl double), and `python3 scripts/linux_network_sandbox_smoke.py`.
The latter applies real seccomp socket-domain filters to the compiled client:
without AF_NETLINK it retains software and logs the omitted network observation;
with AF_NETLINK it includes the host field. It does not emulate the entire systemd
sandbox and does not contact NetBox.

## One machine card with assigned addresses (migration 0065)

The company page's **01 / Inventory & software** groups IP-address records under
their actual device/VM. NetBox still has separate native IP objects; these are not
additional machines. Import retains each address record, local assessment, software,
review history and external identity. The card links to those address records and
shows a bounded preview (16 per host); the host detail paginates all addresses at 100.
Standalone/unassigned IPs, unsupported assignment types and prefixes remain independent.
The raw inventory API continues to represent individual imported objects.

Grouping uses only NetBox's explicit `assigned_object_type` + interface identity +
nested device/VM ID within the same complete, authorized source snapshot. It never
joins by hostname, DNS, textual IP or matching IDs on another instance. A parent
outside the snapshot/tenant scope does not cause grouping. Reassignment/unassignment
updates the relation on a successful import. Missing objects retain last-known data
and visible missing labels; neither deletion nor current ownership is inferred.
Failures roll back the full source snapshot. This remains GET-only and requests no
new API permissions, interface lookups or upstream changes.

Upgrade using the normal backed-up frozen deployment procedure, apply migration
0065 and restart web/worker/national services. Run `sync_netbox --source SOURCE_UUID`
through the protected management wrapper for the intended authoritative source, or
use the existing company inventory refresh action/wait for its enabled import.
The next complete import relates already-imported IP records; the migration itself
does no network I/O or automatic deletion/merge. No client rebuild, re-enrollment,
new export permission, primary-IP selection or source/tenant change is needed.
