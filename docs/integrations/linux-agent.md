# Linux authenticated inventory reference

Status: implemented bounded reference, 19 November 2026. Native Go client (including explicitly configured native binary version probes) under [clients/linux](../../clients/linux/README.md); Django receiver, company management UI, durable reports and bounded worker. This adds no remote shell, patch installation, Windows agent, automatic case closure or public deployment.

## Ownership and access

Company fleet admission is now implemented as a separate path: one expiring/quota-limited rollout secret authorizes each freshly generated device key through signed bootstrap and one-use redemption. The installer supports hidden prompt/protected stdin; no per-host browser/key exchange is required. Observed-mode fleet hosts remain self-reported Bearings observations, including with read-only NetBox. Explicit operator-enabled managed sources can issue new codes that register native hosts; no mode attaches by hostname. Existing explicit managed-host enrollment retains its own permissions. See [fleet contract/recovery](linux-rollout.md).

A company administrator/platform administrator authorizes one public key for an existing organization/asset/source, or explicitly grants creation of one new host of a chosen kind. CIRCL visibility alone cannot enroll/bind/revoke. The one-use enrollment secret is stored only as a SHA-256 digest, expires after 30 minutes and requires proof of the preapproved Ed25519 key. An identical lost-ack retry is idempotent within its validity; another request cannot consume it again. Grants can be cancelled; cancelling an already-redeemed grant revokes the device. Credentials expire after 90 days and require reviewed replacement with a fresh key. The device grant belongs to the organization independently of its creator after activation; offboarding a person alone does not revoke delegated device credentials. Device disable/expiry and current source/asset/company ownership are checked on every authenticated delivery and publication.

Each enabled device is limited to one current asset; source binding and asset UUID are pinned. Hostname/IP do not authenticate ownership, deduplicate globally or bypass grants. Initial opt-in host declarations remain separate from authoritative NetBox facts and verified infrastructure claims. New-host NetBox device/VM creation uses the existing approved source/write queue and operator defaults; host registration alone adds no interface/IPAM/DNS writes. The separate opt-in export below adds scoped interfaces/IPs, never DNS or prefix allocation. Revoking a device stops subsequent report publication; it does not undo an already approved hardware submission in the separate inventory-write queue. Device replacement preserves the asset and existing findings, with explicit release/reassignment of software version ownership. Unsupported company merges/provenance cleanup remain protected by the new non-disposable references and require reconciliation.

Standard dpkg/RPM observations now become separate software inventory entries automatically, enabled by default for enrolled devices. Their exact native versions remain device-owned and update without per-package clicks. Products use deterministic versionless Package URLs by package family, reported host distribution namespace, name and package architecture; a versioned observation PURL retains the report-time distribution release and exact version (RPM epoch is a qualifier). Debian names/namespaces are lowercased; RPM names retain case. Parallel install-only RPM/kernel slots remain separate installations. No manual/CSV installation is claimed by name or overwritten; missing packages keep their last-known records and provenance. Custom binary probes still require reviewed explicit version ownership.

The worker backfills fresh already-applied reports after migration 0059, without client upgrade/resending. Work is bounded to 25 devices per worker call and 5,000 unbound package slots per device batch, with partial work indexes and bulk writes. Unsupported identities remain observations and are reconsidered on a new report. The original component report supplies legacy OS context, so a later unrelated report cannot relabel old packages. Manual release excludes that component from future automatic creation; retained software/evidence are not deleted. A company administrator can disable new automatic entries per device; already assigned version fields retain their existing publisher. Re-enabling processes fresh unbound observations. Device/source locking serializes import, processing, manual mapping and revocation. A change to the package distribution namespace behind an existing automatic binding is refused for review; a normal release upgrade within the same distribution keeps product identity and updates report-time release metadata.

Package namespaces are derived from the reported host OS (including `rhel` → `redhat`) and are **not** attestation of the package's repository, official vendor, or source package. Third-party packages may run on these hosts. No source-package name is fabricated. The normalization follows the public [deb definition](https://github.com/package-url/purl-spec/blob/main/types/deb-definition.json) and [rpm definition](https://github.com/package-url/purl-spec/blob/main/types/rpm-definition.json), consulted 20 November 2026. Versionless product identity intentionally stays stable across version/release updates; exact installed version/release/epoch remain separate evidence.

Inventory assignment and CVE applicability are separate: dpkg/RPM versions are never reduced to upstream SemVer, and the generic automatic watch enrollment excludes distro package PURLs rather than guessing upstream products from display names. Existing explicit watches/bindings remain. Automatic supported Ubuntu/Debian/RHEL OVAL evaluation now runs in the worker with exact native version comparisons and reported Debian source-package versions. See [distribution advisory matching](distro-cves.md) for release support, cache health and partial/unknown conditions. Repository provenance and running-code verification remain unproven; this is a bounded OVAL subset. Manual/CSV editing cannot overwrite owned version fields, and no observation closes findings or sends notifications.

## Frequent inventory checks

The Linux system inventory service captures locally every 15 minutes with up to
90 seconds of added jitter and the watcher's normal polling delay. The first
capture after service start is randomized. An older receiver keeps the full
inventory cadence at six hours or the configured interval, whichever is longer.
Explicitly scoped foreground probes and Windows keep their existing protocols.

A receiver advertises support with `Bearings-Inventory-Check: 1` on the usual
report receipt. The watcher first establishes a full baseline with explicit
coverage (`gaps`). It hashes the observed inventory and coverage locally without
the report UUID, sequence or observation timestamp. A changed payload is queued
as a full report. An unchanged capture queues a signed
`bearings.agent.inventory-check.v1` message containing the full report UUID,
the capture time, its coverage gaps and its own report identity and sequence.
Full and compact messages use the same signature, exact-byte receipts,
deduplication, device admission limits and durable outbox.

The receiver accepts a check against the device's latest applied eligible full
report and matching coverage. A snapshot received too late to project bound
versions cannot serve as that baseline. A rejected check with `Full inventory required`
clears the client's baseline so the next attempt sends a new full snapshot. A
package collection failure can be recorded without a baseline after negotiation.
Network and application probe failures disclose their coverage categories. The
receiver retains evidence, and only components present in the verified full
snapshot gain freshness from a check. The compact receipt and device status
are recorded without rewriting components, exporting to NetBox or requesting
CVE evaluation. Vendor advisory changes can still trigger evaluation. Receipt
`applied` means that the check status was recorded, including when the run had
a coverage gap.

Host and client pages show the last successful check, the last inventory change
and gaps from the latest capture. An unreachable client cannot deliver its gap
status. The previous last-known inventory stays visible.

Deploy the reviewed server first with migration 0080. Publish the matching
client artifacts afterwards. The managed systemd unit changes, so existing
automatic updaters require one reviewed installer refresh; their existing
device keys, configuration, queue and drop-ins are preserved. See
[Linux client updates](../operations/linux-client-updates.md#upgrade-to-15-minute-inventory-checks).
Before manually downgrading the client to a pre-check build, stop its watcher and
flush its queue with the current binary so pending compact messages are handled.

## Ingress contract

POST-only HTTPS endpoints:

* `/api/v1/agent/bootstrap/`: bounded company rollout bearer plus proof of the new device key; returns a one-use grant only.
* `/api/v1/agent/enroll/`: public-key-bound bearer grant plus signed request.
* `/api/v1/agent/reports/`: signed observations and inventory checks; durable receipt for both, with full inventory processed in the background.
* `/api/v1/agent/status/`: signed query for that device's own receipt only.

Cookies/SSO sessions do not authenticate these machine endpoints. They intentionally use signature authentication rather than browser CSRF. Management forms at `/organizations/<slug>/agents/` retain normal session authorization/CSRF and current organization scope; operator reads and all grants/bindings/revocations are audited. No CORS grant is added. Machine responses are private/no-store and do not return advisory intelligence.

Fixed RFC 9421 profile: `bearings` label, signed application tag `bearings.agent.v1`, Ed25519 only, components `@method`, `@path`, `@authority`, `content-digest`, `content-type`, `x-bearings-key`. Creation and expiry are bounded to five minutes with at most 30 seconds forward clock tolerance; exact URI queries, content encodings, incomplete coverage and unexpected parameters are rejected. Body SHA-256 Content-Digest is validated separately. Delivery signatures are fresh on retry while original observation time/report bytes remain unchanged. RFC verification uses frozen `http-message-signatures` 2.2.x; the Go encoder is a fixed emitter, not a second general signature parser. No JWT/algorithm fallback or disabling of certificate verification is accepted. This profile is not FIPS validation or TPM attestation.

The strict versioned JSON contract includes a random report UUID, monotonic signed device sequence, original observation time, explicit collection scope/completeness, OS/kernel/reboot-indicator facts, native package slots/versions and optional fixed NGINX runtime observations. Duplicate keys, nonfinite numbers, excessive nesting, unknown fields, duplicates and oversize input are rejected. All fields are untrusted display text; no supplied URL/command is fetched/executed. No username, environment, process command line, MAC, file contents or connector secret is collected. Hostname/interface addresses are an explicit enrollment opt-in, not an implicit package-report side effect.

A unique device/sequence and report UUID plus a locked device admission record make retries idempotent and reject rollback/conflicting bytes. A duplicate only receives its original receipt. Source metadata is never selected from a caller-provided company/asset ID. Limits: one-megabyte/5,000-component report, ten pending inputs, ten seconds between new reports, 200 reports/32 MiB per UTC day per device. Enforce ingress connection/rate/storage budgets at the reverse proxy as well; per-device limits do not replace global/company admission control against mass enrollment or denial of service.

## Publication, uncertainty and retention

The consumed enrollment also retains its exact signed body, signature parameters/signature and target without retaining the bearer secret. `AgentReport` retains exact body, body hash, original signature parameters/signature, signed target/content type and verification public key. Receipt IDs/status do not expose raw reports across devices. Database commit precedes acknowledgment. The client authenticates receipts through verified HTTPS; receipts are not independently server-signed and the deployment must trust its TLS termination/proxy path. The client retains local input until the response acknowledges the exact ID/sequence/hash. Bounded input is processed by `process_agent_reports --limit 25`; the bundled worker calls it independently of HTTP processing. For another deployment schedule it explicitly.

Publication and revocation share a device lock; source serialization and current ownership checks precede version changes. A transaction publishes package observations, owned version changes and applied sequence together. Package and owned-version changes are batched; a 500-binding regression enforces a bounded SQL count. Failures preserve previous state; validation conflicts become rejected reports; database interruption retains pending input. Older publication cannot overwrite a newer applied sequence. Backward observation clocks require review. Original signatures authenticate source statements, not the truth of a compromised OS.

Each component keeps its own observation time. Partial data does not refresh other components or full-snapshot age. Runtime observations retain their own timestamp even when another report omits service checks. Full scoped collection may flag a prior component missing; it never deletes installations or resolves findings. Software data older than twelve hours is explicitly stale and cannot overwrite an owned canonical version. Receipt time, observation time, complete-package coverage and runtime coverage remain separate. The human correctness/reactivity test is unchanged.

A native package version preserves epoch/vendor release/backports; stripping it into a vendor SemVer match would be unsafe. Unknown distro-specific applicability remains unknown. RPM parallel kernel instances remain distinct. NGINX comparison covers only the configured systemd main process executable and guards PID reuse; executable equality is not worker/library/configuration coverage or proof that a vulnerability is remediated. No restart is performed.

Exact report history is confidential inventory. No automatic retention deletion is introduced: agree retention, referenced-evidence preservation, backup encryption/access and storage quotas before a large operational deployment. Native package inventories can be large; this full-scoped-snapshot reference is not the proposed delta/partitioned fleet protocol. Existing 40,000-company read benchmarks are not ingest capacity evidence. Real target OS/proxy/privilege and sustained ingest/refresh tests remain deployment gates.

## Run

After updating this revision, rebuild the application image once because the frozen signature-verification dependency is new:

```sh
python3 scripts/dev.py up
python3 scripts/build_linux_client.py
```

In the retained lab, a focused Bearings image build followed by `up --no-build` is equivalent when reusing unchanged native-service images. Cloud proxy/CA environments have `scripts/cloud_image_build.py`; verification stays enabled. Production endpoints require correctly trusted HTTPS and operator-configured `BEARINGS_PUBLIC_URL`/allowed hosts. Run migrations 0054–0057 before serving the new endpoints.

See the [client guide](../../clients/linux/README.md) for commands, protected enrollment files, systemd, outage behavior and replacement procedure. Source implementation: `portal/agent_protocol.py`, `portal/agents.py`, `portal/agent_api.py`, and `portal/agent_views.py`; tests: `portal/test_agents.py`, `portal/test_agent_client.py`, `clients/linux/client_test.go`. Build outputs stay under ignored `.local/`; no release binary, signing key, real customer report or enrollment secret belongs in Git.


## Configured native binary extension — 20 November 2026

A separate `configured-binaries` scope accepts at most sixteen `binary:<local-id>:<architecture>` observations and never asserts completeness/runtime coverage. The strict component contract adds only `binary.path` and `binary.sha256`; package components retain their original exact field set and cannot impersonate this scope. The server stores per-component evidence in `AgentComponent.binary` (migration 0057) alongside the exact historical signed report. It never opens the submitted path, executes supplied commands or infers applicability from it. Old package clients/reports remain valid; upgrade the server before enabling the new scope.

Local administrator/collector-controlled configuration authorizes absolute native ELF paths, fixed argument arrays and one-capture RE2 extraction. Non-root execution, trusted paths, no shell, clean environment, no-new-privileges, descriptor-bound execution/hash, post-execution identity checks, process-group cleanup and bounded file/output/time/count limits reduce accidental execution/inventory errors. Raw stdout/stderr, arguments and patterns stay local. This remains trusted local code running with the collector's file access, not a sandbox or host-compromise protection. The executable hash is not a directory/library/runtime attestation. See the [client guide](../../clients/linux/README.md#manually-installed-native-binaries) for exact limits/examples.

Each stable configured ID is distinct from its display product name and any dpkg/RPM slot. Explicit version bindings retain the existing authorization/source checks; bound binary name/path changes reject the publication for review. Fresh hash/version changes at the same identity are accepted; native package and other binary timestamps/coverage are not refreshed by omission. Failed/partial collection does not remove software or close findings. New binary software entries use a generic package identity rather than falsely claiming a Debian/RPM identity.


## Installer and copy/paste enrollment — 20 November 2026

Company management now defaults to a private/no-store one-use registration code instead of moving a grant file across SSH/browser boundaries. The code is an encoded transport for the same thirty-minute, public-key-bound grant, not a new credential model or an encrypted/signed release ticket. The legacy JSON response remains available to existing direct integrations. The installer hides pasted terminal input or reads bounded stdin for approved automation, then performs native signed HTTPS enrollment as the dedicated account. Its internal private grant file is removed after success/failure; no device private key leaves the target.

Reviewed build output is public only through fixed `/downloads/linux/` artifact names, matching manifest hashes and bounded regular files. Production explicitly configures an operator-approved artifact directory; development uses the local generated build. Verified HTTPS and checksums establish distribution consistency, not independent code-signing. The installer requires Python 3.8+/systemd/root for account/files/service setup, runs the candidate/client as the dedicated non-root account, keeps keys/outbox/configuration/drop-ins and does not restart a deliberately stopped service on upgrade. Input reads use the invoking sudo user's privileges; CA publication accepts certificates only. Local CLI issuance uses current actor/company/source rules in a transaction. A bounded customer-facing company fleet bootstrap API is now implemented; arbitrary delegated existing-asset issuance remains separate. See [roll-out integration](linux-rollout.md) and the [client guide](../../clients/linux/README.md).


Managed NetBox registration is optional server-side policy, separate from signed inventory reporting. New managed rollout codes register the host in the configured tenant and may declare a VM technology tag. Existing observed-only codes remain observed-only, and switching policy does not change device keys or software bindings. Bearings retains package/CVE processing; the separate exporter below copies reported software into a NetBox JSON field and can create scoped interface/IP records. IP declarations alone do not silently allocate addresses. See [managed NetBox operations](../operations/managed-netbox.md). The public website now explains the optional Linux client in all four languages: recurring version inventory, signed HTTPS reports, central rollout and distribution-aware CVE checks.


### Recurring NetBox export

Migration 0064 and the optional signed report `host` field support operator-enabled export to central or customer-owned NetBox. Supported addressed interfaces/IPs become native objects in an explicitly selected tenant VRF; OS/software/version/provenance become a host JSON inventory field. Old clients still report software but do not refresh enrollment-time addresses; deploy server support before updating clients for fresh network observations. No deletion, prefix allocation, primary-IP selection or guessed topology occurs. See [managed export and customer RW preparation](../operations/managed-netbox.md#reported-inventory-export-migration-0064).

### Rollout keys on the download page

Open `/downloads/linux/`, sign in and select the organization. An organization
administrator (or platform superuser) can create a limited rollout key directly
there and copy it into the installer's hidden bootstrap prompt. A single eligible
organization is selected automatically. Readers, editors, analysts without company
admin membership and anonymous visitors cannot create or inspect rollouts.

The secret appears only in the successful creation response, with no-store caching.
Existing keys cannot be recovered because only their hashes are retained. Reloading
shows rollout metadata and revocation controls, not the key. Creating a replacement
does not silently revoke existing rollouts or change enrolled device credentials.
The existing company fleet page uses the same authorization, validation and service.

Deploy this server UI change with the usual frozen production dependency sync,
Django checks and restart `bearings-web`. No migration, client rebuild or restart
of `bearings-linux`, workers, NetBox or Keycloak is required.

The creation form targets `#rollout-result`: after submission the browser jumps
to the result immediately below the form. A successful response contains the
read-only key field; validation failures show an explicit failure notice. A reload
still cannot recover the secret. This presentation update requires restarting only
`bearings-web`; no migration, static rebuild or client restart is needed.

The download page and one-time rollout-key result share complete installation
blocks: verified HTTPS download followed by installation with `&&`, interactive
hidden prompt, a complete LXC alternative, reporting service status, and root-only
automation using a pre-provisioned secret-manager file through stdin. The automation
path `/run/secrets/bearings-rollout-key` is an explicitly labelled example. Commands
use the configured public origin and never interpolate the key.

This instruction/CSS update requires `collectstatic --noinput` and a restart of
`bearings-web` after updating the checkout. No migration or client restart is needed.

### Host and virtualization choices

For an LXC/Incus container or other VM, choose **Virtual machine**. With managed
NetBox registration, the virtualization field then offers only the types configured
on that source’s NetBox instance. Physical server/desktop/laptop choices hide and
clear the virtualization selection. Sources without managed write access or
configured virtualization types omit that selector. A VM may remain unspecified.

JavaScript updates the field immediately; without JavaScript, the visible field’s
help explains its VM-only purpose. Server-side source-scoped choices reject
unconfigured VM types and clear stale physical-host selections. The service still
enforces write capability and source policy; no NetBox request runs on form display
or rollout creation. Existing rollout modes/tags and enrolled devices are unchanged.

Deploy with `collectstatic --noinput` and restart `bearings-web`; no migration or
client rebuild/restart is needed.

### Python 3.8 installer compatibility

The monitored host requires Python 3.8+ (including the Ubuntu 20.04 system
interpreter). The installer drops UID, GID and supplementary groups in an isolated
Python child before exec instead of passing Python-3.9-only `subprocess` options.
It uses no shell or threaded `preexec_fn`; bounded source reads still run as the
invoking sudo user and client commands still run as the dedicated account. Older
interpreters stop with a clear message before system commands. This compatibility
does not change the server’s Python requirement or operating-system support policy.

For an existing server, update its reviewed checkout and run
`python3 deploy/ubuntu24/ecosystem.py prepare-linux-client`. This rebuilds the
checksummed immutable download bundle and restarts only `bearings-web`; editing
the source or restarting web alone cannot replace previously published artifacts.
Then download `install.py` again on the monitored host and retry the same installation
command. Retain existing client state and keys; do not remove or re-enroll them.
The reported Python 3.8 `TypeError` occurs before account/client installation; the
root-owned installer lock file can already exist and is reused safely.

Validation: `python3 scripts/linux_installer_smoke.py --python38` adds a digest-pinned
legacy interpreter to a disposable test-only image; it never changes the application
runtime. Both manual and automatic registration use real verified loopback HTTPS
and signatures, with simulated systemd, no external network and disposable accounts.

### Installation with noexec temporary filesystems

Executable candidate checks now run in a temporary root-owned directory next to
`/usr/local/bin/bearings-linux`, on the destination filesystem. `/run` remains the
lock/download location and may keep `noexec,nosuid,nodev`. The installer never
remounts it or relaxes mount policies. Validation still runs as the dedicated
service account before replacing a running client. Candidate files are removed
on both success and failure; keys, queues and drop-ins are retained. Candidate
version/init failures identify the phase and exit code without printing raw
stdout/stderr or credentials.

After updating the server checkout, republish downloads with
`python3 deploy/ubuntu24/ecosystem.py prepare-linux-client` (restarts web) and
redownload the installer on affected hosts. No migration or manual client restart.
The disposable installer smoke now mounts `/run` with `noexec`, verifies direct
execution there is actually denied, and exercises manual/fleet installation on
both current Python and Python 3.8. The bundled-stack CI runs this regression.

### Finding the client download

Open **Inventory clients → Linux** or go directly to `/downloads/linux/`.
The download page provides **Download Linux installer** when a complete build
is published. Use **Inventory clients → Rollout keys** for shared Linux and
Windows registration and **Inventory clients → Profiles** for the Linux
application version profile editor.

The public website also links **Linux client** in its header, and its client-section
button opens the download page instead of registration in all four locales.
Anonymous downloads remain public; organization rollout permissions are unchanged.
This navigation change requires only source update and `bearings-web` restart.
No migration, static rebuild, client rebuild or client restart is needed for the
integrated website. Standalone static sites need a normal website rebuild.

### Deregistration and uninstall

On a standard systemd installation, run `sudo python3 install.py uninstall`
from the current reviewed release. The command attempts to notify Bearings,
then removes the managed client, service, account and local queue. Reviewed
administrator profiles and custom drop-ins remain on disk.

The portal can also revoke the device and request uninstall. The current
installer adds a root-owned systemd timer. Its helper uses the dedicated
unprivileged account to check and acknowledge the fixed per-device action
over the existing signed HTTPS protocol. The privileged phase uses only
the installation's fixed local paths. A protected checkpoint lets an
interrupted cleanup finish after its credential files have been removed.

### Deterministic package-version CVE results

Supported distribution version rules now yield an explicit affected/fixed package
verdict with the actual compared versions, operator and result. Presence-only
entries and unsupported required predicates stay unresolved with a precise cause.
A CVE can describe a library embedded in another distributor package; compare the
distributor package version with the distributor rule, not an unrelated upstream
library version. Package verdicts and human/local risk assessments are separate.

Receipts use evaluator version 2 and vendor compilation version 3. Fresh devices
are automatically requeued on upgrade; old/stale proofs are not presented as
current. Source/binary version facts, OS context and rule fingerprints participate
in invalidation. See the [case audit](../audits/2026-11-21-package-cve-correctness.md).

After source update, restart `bearings-web bearings-worker bearings-national`.
No schema migration or Linux client rebuild/restart is needed. Allow the background
worker to recompile the cached vendor feed once and reevaluate current reports.

### Application versions beyond the OS package database

The optional `applications` report section carries up to 16 independent partial
application observations (`manager=manifest`) without changing complete Debian/
RPM coverage. The receiver validates known methods, paths, safe version and
product identifiers, bounded fingerprints and Git status metadata; it does not
execute those methods. Manifest evidence has its own field introduced by
migration 0066. See [configurable application profiles](linux-application-probes.md)
for JSON fields, RE2 extraction, fixed Git queries, MISP defaults, explicit
manual-version ownership and failure semantics. Upgrade server before client.


### Asset update presentation

The asset page highlights current, authorized package matches with documented vendor fixes and displays vulnerability reviews separately. Repository update availability remains unmeasured. Missing, stale, or restricted evidence cannot supply a current fix count. The technical synchronization states are shown as icons with hover and keyboard-focus explanations.
