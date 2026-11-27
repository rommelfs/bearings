# Linux installation and fleet registration

Implemented 20 November 2026: company-scoped automatic Linux registration, central HTTPS downloads and a local installer. A company administrator authorizes one bounded rollout; deployment jobs need no per-host public-key exchange, enrollment code, manual asset creation or Bearings server shell access. Existing explicit single-asset/new-managed-host enrollment remains available.

## Once per rollout

Open the company's **Linux inventory reports → Automatic registration / fleet rollout**, or `/organizations/COMPANY/agents/fleet/`. Specify a name, host kind, device limit (1–100,000) and expiry (1–168 hours). Accept the explicit hostname/network/software reporting scope. The company administrator or trusted platform administrator receives one secret, shown once. Store it in the deployment secret manager. CIRCL analyst status alone is insufficient.

New hosts are **self-reported Bearings observations**, including when the authoritative NetBox connection is read-only. No NetBox object or IPAM assignment is created. Hostnames/IPs are declarations, not proof of ownership or a basis for attaching to existing assets. Two fresh keys with the same hostname create distinct observations; only the same retained key/retry context is deduplicated. Do not initialize keys or copy enrolled state into reusable images. Reconciliation with existing native devices needs a separately authorized identity mapping.

## On each Linux host

Download and review the installer from the trusted installation, then run it as root:

```sh
curl --fail --show-error --proto '=https' https://bearings.example/downloads/linux/install.py -o bearings-install.py
sudo python3 bearings-install.py --server https://bearings.example --bootstrap-prompt
```

Paste the rollout key at the hidden prompt. For deployment automation, replace `--bootstrap-prompt` with `--bootstrap-stdin` and pipe the secret manager's output into the process. The token is never an argv/environment value and is never written to device state. Do not put it in shell history, images, CI logs or cached Ansible facts. Use `no_log` around secret-bearing tasks. Initial host identity and all package observations remain local until explicitly authorized enrollment/reporting.

Add `--lxc-compatible` to the installation command only on constrained LXC systems. The dedicated non-root account, no-new-privileges and capability/resource/syscall limits remain; unsupported namespace isolation is explicitly omitted for that service. Actual target systemd acceptance still requires checking `systemctl status bearings-linux` and its journal. For an enterprise CA use normal OS trust deployment or `--ca-file /known/local/ca.pem`. HTTPS verification and redirect refusal remain mandatory; downloading the installer itself already requires trusted HTTPS.

The installer downloads and checks the matching amd64/arm64 binary/unit against the HTTPS manifest, preserves or generates a host-local Ed25519 key, registers and starts the system-package watcher. It uses 15-minute inventory checks with a compatible receiver. Watch startup has jitter. It does not install patches, execute server commands, discover adjacent machines or prove a compromised machine truthful. Standard dpkg/RPM packages automatically create and update separate inventory entries; explicit bindings remain necessary to change a preexisting manual/CSV software record or adopt a custom binary. Exact native versions, package architecture and report-time distribution/release are retained. A package version alone does not prove CVE applicability or remediation; the worker now evaluates supported vendor OVAL rules automatically with native version comparisons and exact Debian source metadata. See [distribution advisory matching](distro-cves.md); unsupported conditions remain unknown and human workflows are preserved.

The operator prepares artifacts once on the native server with `python3 deploy/ubuntu24/ecosystem.py prepare-linux-client` after deploying the reviewed code/migration. Downloads are public fixed allowlisted artifacts, independent of private inventory/credentials. Builds contain both architectures, installer, unit, checksums, license and tracked corresponding source. Manifest hashes provide consistency over trusted HTTPS, not independent release signatures. See [native operation](../operations/ubuntu24.md) and [client reference](../../clients/linux/README.md).

## Existing deployment processes

A concrete [Ansible playbook](../../clients/linux/examples/ansible-rollout.yml) uses verified `get_url`, bounded batches/concurrency and `command` with protected stdin. Keep `bearings_rollout_key` in Ansible Vault or an approved secret lookup. It is a reference integration pattern, not a published Ansible collection or evidence of a production 10,000-host rollout.

Use bounded retries with delay/jitter in your deployment runner. The native ingress deliberately retains 10 agent requests/second per source IP plus a burst of 30; bootstrap and redemption each use a request and later reports share that budget. Coordinate NAT fleets instead of removing that protection. HTTP 429/503 and network failures retain the same local key/request/grant for retry. No automatic endless retry loop runs in the installer; permanent denial must be reviewed rather than hidden. Rollout reservations are indexed by device public key; no full inventory scan or hostname lookup is needed per observed host.

## Protocol, recovery and revocation

`POST /api/v1/agent/bootstrap/` accepts only HTTPS, a bounded strict JSON body (`bearings.agent.bootstrap.v1`, `public_key`, `request_id`), an expiring rollout bearer and an RFC 9421 Ed25519 proof from that public key. The signing identity is `fleet:ROLLOUT-UUID`. The bearer authorizes admission; proof of key possession does not identify the host or attest its security. The endpoint cannot read inventory/intelligence, replace an existing device or change roles/native source permissions. Existing ingress rate limits cover it. Fleet secrets are stored as hashes only and never in audit output.

Authorization rechecks the current creator's company-admin permission, active company, rollout expiry/revocation/quota and original organization/source/tenant/endpoint binding. Admission locks company then rollout before reserving quota; concurrent jobs cannot exceed the limit. Each reservation yields the existing 30-minute one-use public-key-bound grant, whose expiry cannot exceed the rollout's. Deterministically derived grant secrets permit exact lost-response retries without storing plaintext; application secret-key rotation needs the corresponding `SECRET_KEY_FALLBACKS` for still-pending grants. Never refresh an expired/cancelled reservation silently.

The client durably keeps a public `bootstrap.json` correlation context and, while redemption is pending, a private 0600 `bootstrap-grant.json`. It retains its exact signed enrollment body/request identifier through a lost reply, removes the one-use grant after acknowledgment, and never stores the reusable rollout bearer. Repeating the same installer/bootstrap on an enrolled host preserves identity and a deliberately stopped service. A changed origin or pending rollout is refused. If a key is rejected, check its validity, expiration and rollout settings. When the original key is unavailable or expired, ask the Bearings administrator to verify that the device has no server-side enrollment or reservation. Then archive the abandoned local attempt:

```sh
sudo python3 bearings-install.py archive-bootstrap
```

The command leaves the device key and all other local state in place. It refuses to archive an attempt when the client already has a grant, a pending enrollment request or a registered device. With a newly issued key, run the installer again with `--bootstrap-prompt`. Older installations need the current installer and matching client binary before using this command. Download the current installer and run it once with `--server` to refresh the binary while keeping the unregistered state.

Revoking the rollout stops new and pending registrations. Enrolled devices use individual credentials and must be revoked individually when required; rollout expiry does not disable their reports. Device credentials currently expire after 90 days. Automatic renewal, external hardware attestation, signed release artifacts, authoritative NetBox reconciliation and sustained fleet-wide ingest/retention acceptance remain separate work. Existing read-path tests with 40,000 companies do not establish write/report ingestion capacity.

## Explicit single-host alternative

The previous `identity` → company UI → hidden `enroll --code` flow remains supported for binding an already imported asset or an explicitly managed new host. `enroll --code-stdin` and `--grant-file` remain available. The operator-only `issue_agent_enrollment --organization COMPANY --actor ADMIN --asset UUID --public-key KEY` command still creates one public-key-bound grant inside the trusted server administrative boundary. `--new-host-kind` requires an explicitly writable source; `--register-host` supplies client consent. Neither actor attribution nor rollout admission grants a customer shell access to the server.


## Managed NetBox mode

A platform operator may enable managed registration on an existing writable, tenant-scoped source. New rollout codes then record managed mode; existing codes keep their observed-only mode. VM rollouts can declare LXC, Incus, Proxmox, VMware, KVM or Hyper-V using the operator-provisioned tag taxonomy. The enrollment snapshots this declaration and queues a guarded NetBox job with the same local asset UUID. Standard clients need no rebuild. Source read-only/disabled policy, managed-policy revocation and revoked/expired devices are rechecked before writes; hostname matching never replaces UUID identity. See [native managed NetBox plan and verification](../operations/managed-netbox.md).
