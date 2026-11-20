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

Reported interface/IP information remains a declaration in Bearings, not an automatic claim or allocation of NetBox IP addresses/prefixes. Software versions and CVE/human-review records remain in Bearings; this integration registers the host/VM in NetBox rather than inventing a NetBox software-inventory plugin. Hostnames are not identity proofs and existing external machines without the UUID marker are not silently adopted. No patches, probes, emails or changes to customers' existing read-only connectors are performed.

The native helper validates the retained receipt and fails closed on changed users, credentials, native permissions or owned reference records. The native database transaction is atomic; a subsequent Bearings failure can leave the explicit native managed capability provisioned but the host unconfirmed. Preserve the receipt and retry/inspect rather than resetting identities or replacing sources. Native token expiry and later renewal remain operational lifecycle work.

## Validation

Local acceptance uses the real pinned NetBox over verified HTTPS and an explicitly synthetic isolated tenant. It checks retained-host promotion, tag visibility, same-UUID import, repeated apply/verify, signed automatic registration/reporting for an Incus VM and a physical host, lost enrollment acknowledgement recovery, preserved software, foreign-tenant rejection and denied deletion. Independent native NetBox ORM queries verify one object per UUID and the expected tags. The normal bundled NetBox/FlowIntel/RT/RTIR smoke is rerun; no production host or credential is touched. Production acceptance occurs when the operator runs the commands above and inspects their receipts.
