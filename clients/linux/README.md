# Bearings Linux reference client

A native, dependency-free Go client for **outbound authenticated inventory observations**. SPDX: AGPL-3.0-or-later; see the repository [license](../../LICENSE). This is a bounded Linux reference implementation, not a patch installer, remote shell, complete endpoint scanner or proof that a compromised machine is truthful.

The receiver, permissions, threat model, limits and validation are documented in [Linux observations](../../docs/integrations/linux-agent.md). A separate [Windows reference](../windows/README.md) now implements OS/build and machine software reporting; native Windows acceptance remains pending. TPM, mTLS, automatic credential renewal, signed release packages and fleet-scale ingest acceptance are not implemented by this reference.

## Recommended: central download and installer

Open **Linux inventory reports → Install Linux client** in Bearings, or visit `/downloads/linux/`. The operator prepares the artifacts once; monitored hosts need **Python 3.8+, systemd and sudo**, not Go. The local lab download page is `https://localhost:9441/downloads/linux/`; localhost works only on the machine running that lab. Before remote roll-outs the operator must configure a reachable `BEARINGS_PUBLIC_URL`, allowed hosts and valid HTTPS trust. No public deployment is performed by this feature.

For automatic registration, create one expiring, quota-limited rollout key in the company's **Linux inventory reports → Automatic registration / fleet rollout**. Download the installer as below, then use:

```sh
sudo python3 bearings-install.py --server https://bearings.example --bootstrap-prompt
```

The hidden prompt accepts the company rollout key. Deployment jobs use `--bootstrap-stdin` and secret-manager stdin instead; no per-host key copy or asset creation is needed. Every host retains its own key. New hosts are self-reported Bearings observations, including with read-only NetBox; hostnames/IPs never auto-attach a key to an existing asset or grant NetBox writes. Expiry, quota, creator permission and revocation are rechecked. See [rollout/recovery/Ansible](../../docs/integrations/linux-rollout.md). Use `sudo python3 bearings-install.py archive-bootstrap` only after confirming that an abandoned local attempt has no server reservation. The command preserves the device key and refuses to archive a grant or enrollment.

For explicit single-host enrollment instead, replace the example origin with the trusted Bearings installation:

```sh
curl --fail --show-error --proto '=https' https://bearings.example/downloads/linux/install.py -o bearings-install.py
# Review the downloaded installer before running it with sudo.
sudo python3 bearings-install.py --server https://bearings.example
```

On a constrained LXC systemd container, explicitly add `--lxc-compatible` to the **install** command. This creates only `/etc/systemd/system/bearings-linux.service.d/bearings-lxc.conf`, disabling unsupported mount/device/kernel/UTS namespace isolation while retaining the dedicated non-root account, no-new-privileges, empty capabilities, syscall/address-family and resource limits. The main reviewed unit stays unchanged. Other drop-ins and later upgrades preserve the choice; an edited existing compatibility file is refused. It does not alter the outer LXC host policy. Do not add this flag to enrollment. Actual inner-systemd acceptance still needs a status/journal check on the target.

The installer downloads the architecture-matching client and bundled unit over verified HTTPS, refuses redirects/mismatched checksums, creates a dedicated non-login account and protected state, and prints **only the public key/fingerprint**. Copy the public key into the company's **Linux inventory reports** form. Approve the target host and copy the one-use registration code back into the terminal:

```sh
sudo python3 bearings-install.py enroll --code
```

The prompt hides the pasted code; never add the code to the command itself. No grant file travels between browser and SSH host. The installer uses a short-lived private internal file only to hand the grant to the unprivileged native client, removes it afterward, relocates an optional CA to `/etc/bearings-linux/ca.pem`, then enables/starts the unit. Add `--register-host` only when you explicitly approved a new host. For a private lab CA use an already trusted OS CA or `--ca-file /known/local/ca.pem` for HTTPS installation/enrollment; TLS is never disabled. A bootstrap HTTPS trust relationship is required before downloading the installer itself.

Re-run the same install command to update. The installer validates the candidate as the service account, publishes files atomically, keeps device keys/counters/outbox/configuration and systemd drop-ins, and preserves an intentionally stopped service. It refuses unexpected accounts, unsafe destination/state permissions, symlinks, mismatched architectures or an edited main unit rather than silently adopting/chowning existing data. Failure can leave the dedicated account/private state for retry; it never deletes or resets a device key. Already-enrolled devices use `start`, not another grant:

```sh
sudo python3 bearings-install.py identity   # public key/fingerprint + enrolled boolean; machine-readable JSON
sudo python3 bearings-install.py start
sudo python3 bearings-install.py status
sudo journalctl -u bearings-linux -f
```

Installation without a bootstrap option makes no enrollment request; `--server` downloads public artifacts. Starting the enrolled service authorizes its existing periodic reporting profile. The default unit collects system packages every six hours. Use reviewed systemd drop-ins for another scope; the installer preserves them.

For offline/local-source installation, build once below and use `sudo python3 clients/linux/install.py`, or copy the generated distribution directory to the target and run its `install.py`. `--binary /approved/local/client` explicitly selects another reviewed artifact. Build output includes installer, unit, license, checksums, source note and corresponding client/installer source archive. Checksums provide consistency over trusted HTTPS; they are not independent release signatures. This is not an automatic self-updater or an arbitrary downgrade/revocation/renewal mechanism.

### Existing roll-out processes

Ansible/deployment jobs use `--bootstrap-stdin` with one bounded company rollout key, protected stdin and bounded retries. Do not put secrets in argv, environment, images or cached facts. See the [reference playbook](examples/ansible-rollout.yml) and [rollout integration](../../docs/integrations/linux-rollout.md). Explicit per-host `enroll --code-stdin` remains compatible. Neither mode is an automatic credential renewal or a claim of sustained fleet ingest capacity.

## Build from reviewed source

Install the Go language compiler **1.24 or newer**, then from the repository root:

```sh
python3 scripts/build_linux_client.py
```

If `go` names another program, use `--go /path/to/the/go/compiler`. The build uses only Go's standard library, disables module downloads and produces static Linux amd64/arm64 binaries plus `SHA256SUMS` in ignored `.local/linux-client/`. Source revision and dirty state are embedded. Checksums detect changes; they are **not** operator release signatures. Preserve the source/license when distributing a build. ARM64 is cross-built; execute on intended ARM64 systems before accepting that deployment.

The manual examples below call the selected binary `bearings-linux`. Building alone does not install or start it; the explicit installer actions above perform those steps.

## Enroll once

On the actual Linux machine, under the account that will own its key:

```sh
bearings-linux init
```

This creates private state under `$XDG_STATE_HOME/bearings-linux` or `~/.local/state/bearings-linux` and prints **only the public key and fingerprint**. Repeating init preserves its key. Use `--state-dir /private/path` consistently for another location. State is mode 0700; key/config/grant files must be owned by that account and mode 0600. Do not enroll a reusable machine image.

In Bearings, open the company overview or an existing asset and choose **Linux inventory reports** (`/organizations/COMPANY/agents/`). A company administrator or platform administrator pastes the public key, selects the existing asset and copies a one-use registration code. File-based enrollment below remains available for legacy/manual automation. CIRCL analyst status alone cannot authorize devices. The grant expires after 30 minutes and is bound to this public key, company, asset and inventory source.

```sh
chmod 600 /private/bearings-enrollment.json
bearings-linux enroll --grant-file /private/bearings-enrollment.json
```

For the retained local lab's CA, add `--ca-file /path/to/netbox-ca.crt`. There is no insecure-TLS flag. The grant's HTTPS origin must be reachable from the reporting machine: localhost means **that machine**, not another Bearings server. Operators set `BEARINGS_PUBLIC_URL` and matching ingress/allowed hosts/certificates accordingly. No bearer secret is accepted as a command-line argument or written into client configuration/logs.

The enrollment request is saved before delivery, so retrying after a lost response uses the identical request, even if local DHCP data changes. Do not replace pending state blindly. If its grant expires before recovery, cancel/revoke it in Bearings and start a reviewed replacement with a fresh key.

## Optional first-host registration

The administrator may instead leave the existing asset empty and explicitly select one new VM/server/desktop/laptop. The source must allow writes. On that host:

```sh
bearings-linux enroll --grant-file /private/bearings-enrollment.json --register-host
```

This explicitly consents to sending the local hostname and at most 64 configured unicast interface addresses. No DNS lookup, external address discovery, MAC, scan or public-IP inference through NAT occurs. A new Bearings UUID is created once. A matching existing company hostname stops registration for review; names/IPs never auto-merge identities.

Manual inventory records the new asset locally. A writable NetBox source queues its device/VM creation through the existing source-locked, tenant-checked `InventoryWrite` workflow using the operator's site/role/device-type defaults. Read-only/disabled source capability is enforced again by the write worker. Pending/failed writes remain unconfirmed. Revoking a device does not undo an already approved hardware submission; manage that separate queue explicitly. **The initial IP declarations do not create/change NetBox interfaces, IPAM assignments or verified authority claims.** Those require a separate reviewed network workflow. Initial declarations are retained as such, not advertised as continuous network synchronization.

## Observe, report and verify the receipt

Preview explicitly selected data locally first:

```sh
bearings-linux collect --package nginx
bearings-linux collect --inventory
```

Then report after an update:

```sh
bearings-linux report --service nginx
bearings-linux report --package bash
bearings-linux report --inventory
bearings-linux status
```

Choose exactly one scope. `--package` can be repeated; it is exact, not a shell expression. `--service nginx` covers known distro NGINX package names and a fixed `/usr/sbin/nginx` systemd main-process check. Package/runtime profiles execute fixed collectors. The optional local binary configuration below authorizes specific additional native executables; no server-provided command or implicit shell runs. The profile compares executable inode identity with the on-disk file and checks process start time against PID reuse. `executable_matches` covers **only that executable of the main process**, not workers, libraries, configuration or effective remediation. Missing privileges/systemd/executable make runtime coverage unknown. A separately observed reboot indicator is not complete restart detection.

The receiver uses verified HTTPS plus the client's Ed25519 HTTP Message Signature (RFC 9421) and SHA-256 Content-Digest (RFC 9530). A receipt identifies the exact stored report/hash. `pending` confirms durable receipt, **not** completed evaluation; poll `status` for applied/rejected/superseded. A failed foreground report exits nonzero and retains pending input locally. It does not roll back a software update.

All newly observed packages remain separate observations until an administrator explicitly assigns a version field to an existing installation or creates a separate package software entry in the device page. Subsequent fresh reports update that version automatically and request reevaluation of an existing product watch. Product mappings, build/edition and analyst decisions retain separate ownership. Human version/CSV editing requires detaching its agent binding first. Unknown native package applicability stays unknown; Debian/RPM backports are not stripped into vendor SemVer guesses.

Full declared scope can mark a previous package as not observed. It never deletes software or resolves a finding. Partial reports do not refresh the age of other packages or full inventory coverage. Runtime observations retain their own time; an unrelated report does not erase them.

## Manually installed native binaries

A local administrator may explicitly authorize version queries for software outside dpkg/RPM, using [examples/binaries.json](examples/binaries.json). Adapt the paths and patterns to the actual installation; the example is not auto-discovery. One stable `id` identifies each configured installation, including multiple versions of the same software. `name` is a software label, not an assertion of CVE applicability.

```json
{
  "schema": "bearings.binary-probes.v1",
  "binaries": [{
    "id": "nginx-local",
    "name": "nginx",
    "executable": "/opt/nginx/sbin/nginx",
    "args": ["-v"],
    "version_pattern": "(?m)^nginx version: nginx/([0-9A-Za-z.+~-]+)$"
  }]
}
```

Keep the configuration at an administrator-managed readable location such as `/etc/bearings/binaries.json`, mode 0644 or stricter, owned by root/the system filesystem owner or the dedicated collector account. No file or parent may be group/world writable; system-owned sticky temporary directories are accepted only as ancestors. The same checks apply to the executable. Paths must be absolute, normalized and free of symlinks; obtain the actual target with `readlink -f` when configuring an installation. Native ELF files are supported; shell/wrapper scripts are refused. The reference intentionally has no server-editable command configuration. A rootless container's system filesystem owner may have a mapped nonzero UID.

Run as the dedicated **non-root** collector account:

```sh
bearings-linux collect --binaries-file /etc/bearings/binaries.json
bearings-linux report --binaries-file /etc/bearings/binaries.json
bearings-linux enqueue --binaries-file /etc/bearings/binaries.json
bearings-linux watch --binaries-file /etc/bearings/binaries.json --interval 6h
```

This is its own scope; do not combine it with `--inventory`, `--package` or `--service`. For systemd use an operator-reviewed `ExecStart` override with the same private state directory and `--binaries-file` in place of `--inventory`. The hardened unit hides home directories and has memory/task limits; install approved executables under accessible system paths. Its `MemoryDenyWriteExecute=yes` may prevent JVM/JIT startup even for a version query. A Java-specific unit may need an explicitly reviewed `MemoryDenyWriteExecute=no` override; that relaxation is not automatic. Test the intended runtime under its actual service restrictions. An existing package watcher may share that state/outbox, with the existing lock/admission/backoff rules; stagger runs and monitor failed collection.

The client executes a fixed argument array directly, without a shell, stdin, inherited HOME/secrets or supplied environment. At least one explicit argument is required, to avoid accidentally starting a service with no arguments. Combined stdout/stderr is limited to 16 KiB; a Go RE2 pattern with exactly one capture must produce exactly one version match. Only the parsed version, configured ID/name, architecture, canonical path and executable SHA-256 enter the signed report. Arguments, regex and raw output are not transmitted. The client fingerprints and executes the same open descriptor, verifies file/path identity afterward and refuses a changing executable. Limits: 16 probes / 64 KiB configuration, 256 MiB per executable, five seconds per started process and thirty seconds per collection including hashing. Linux `/proc` is required. No-new-privileges prevents set-ID/file-capability elevation, and process groups are killed on timeout/cleanup. Blocking or unresponsive filesystems remain an OS-level availability concern.

**Only configure trusted programs and reviewed version-only arguments.** Executing a version switch is not a sandbox or a guarantee that a program has no side effects. The program runs as the collector account and can access files available to that account, including device state; use the hardened dedicated service without capabilities, and isolate untrusted programs separately. The hash covers the executable file, not its dynamic libraries, whole JDK/application directory, running service or proof of remediation. JAR manifests, SBOM/container discovery and script-wrapper support remain separate work.

Any failed, excessive, nonzero, ambiguous or timed-out query fails the collection without publishing a partial success. Previous observations remain and become stale normally. Binary scope never claims full package coverage or marks unconfigured software removed. New records still need explicit version ownership in Bearings; only their versions may update afterward. Changing a bound binary's name/path requires releasing and reviewing that binding first. Keep its ID stable across upgrades, and do not reuse it for a different installation. Upgrade the server/apply migration 0057 before deploying this client feature; older package-only clients remain compatible.

## Outages and periodic collection

```sh
bearings-linux enqueue --service nginx
bearings-linux flush
bearings-linux watch --inventory --interval 6h
```

`enqueue` durably stages locally without network access, suitable for a nonblocking deployment hook. `flush` sends pending reports in sequence and removes each only after an exact durable receipt. Duplicate/lost-ack retries do not repeat publication. Watch checks the outbox roughly every 30–35 seconds, captures at the chosen interval with jitter, and retries failed delivery with bounded backoff. It releases its state lock between operations so foreground hooks can coexist. Busy locks defer work. Recovery from a backlog triggers a fresh capture instead of treating old data as newly observed.

Limits: 1,000,000 bytes / 5,000 components per report; 120 characters per native version; 64 pending local reports / approximately 64 MB with no silent eviction. The server admits at most ten pending reports, one new report per ten seconds and 200 reports / 32 MiB per UTC day per device. Exact idempotent retries do not consume another allowance. Larger scopes need a future paginated contract; no silent truncation is performed. An expired/revoked credential does not flush through a new identity automatically.

## Optional systemd service

Review [systemd/bearings-linux.service](systemd/bearings-linux.service), install the locally built binary under `/usr/local/bin`, create a dedicated `bearings-linux` system account and a mode-0700 `/var/lib/bearings-linux` owned by it. Initialize/enroll **as that same account**, consistently adding `--state-dir /var/lib/bearings-linux`. Install the reviewed unit and enable it with your normal service-management process. Keep a custom CA at an administrator-managed readable path such as `/etc/bearings/ca.pem`; the hardened unit cannot read home directories. The service has no Linux capabilities and does not grant ptrace or Docker access. NGINX runtime data may remain unavailable under this account; this is disclosed.

If elevated collection is operationally necessary, review that privilege separately. Do not make a private state directory world-readable to let another account use its key. Root compromise remains outside any self-report's truth guarantee. There is no self-updater; distribute reviewed builds through the organization's existing trusted software deployment.

## Expiry, revoke and replace

Device credentials expire after 90 days. Before replacement, stop the old service, revoke/cancel its authorization in Bearings, release its software bindings explicitly, initialize a **fresh private key/state**, and enroll against the same existing asset. Assign its package observations to the retained installations. Asset/finding identity and history survive; an old key is never silently reused. Snapshot/clone sequence rollback is refused and requires explicit recovery, not an automatic counter reset. Company administrators can cancel unused grants and revoke devices, including reports already waiting for processing.

## Checks

```sh
cd clients/linux
go test -race ./...
go vet ./...
```

Tests include a signature vector from the independent Python RFC library, TLS trust and redirect refusal, exact receipt/queue behavior, private-state permissions/locking, native versions and parallel RPM kernels, output quotas, and a real child process still executing the old inode after atomic file replacement. The Django PostgreSQL suite also executes the actual built Go binary against loopback HTTPS, including browser-CSRF grant issuance, first-host registration, lost acknowledgment, concurrent duplicate admission, revocation and explicit projection. See the validation record for actual outcomes and bounds.


## Automatic Debian/RPM software inventory

The receiver now inventories standard dpkg/RPM packages automatically after enrollment; no per-package button or client upgrade is needed. Existing fresh reports are backfilled after server migration 0059. Open the server's **Installed software** list (searchable, 100 entries per page) or the **Open installed software** button on its Linux report page. Reported package versions stay current on later reports; existing manual records are not matched by name or overwritten.

Native Debian epochs/revisions and RPM EVR remain intact. Stable package products use Package URLs, and observation metadata retains exact version, architecture and report-time host distribution/release. RPM install-only/kernel versions remain distinct slots. The reported host namespace does not prove official package repository/vendor or binary-to-source mapping. The background worker automatically evaluates supported Ubuntu/Debian/RHEL vendor OVAL rules with native version comparisons; this client reports optional exact dpkg source-package names/versions for Debian binary-to-source matching. Unsupported conditions remain unknown and human reviews are preserved. See [vendor advisory coverage](../../docs/integrations/distro-cves.md). Upstream SemVer guesses are not used for package affectedness. See [receiver normalization and limits](../../docs/integrations/linux-agent.md).

Per-device **Automatically add reported Debian/RPM packages** is enabled by default. Disabling stops new entries; existing version publishers remain. Explicitly releasing ownership excludes that package slot from automatic recreation while preserving its software/history. Custom binary observations still use reviewed mapping. New entries are created in bounded bulk batches. Missing/stale/expired/revoked source data does not erase software or resolve findings.

## Application release files and configurable profiles

Full inventory also reads approved local application version profiles, with
MISP `VERSION.json` autodetection at common paths by default. Local administrator
configuration in `/etc/bearings-linux/application-probes.json` supports
`misp-version-json`, `json-fields`, `file-regex` and `git-tag`. See the
[profile reference, permissions, examples and upgrade order](../../docs/integrations/linux-application-probes.md)
and [example JSON](examples/applications.json). These are bounded local metadata
observations; the client does not run application scripts or arbitrary shell
commands. Git commits, release tags and tracked-file changes remain distinct;
dirty/ambiguous checkouts do not become asserted release versions. Existing
manual software requires an explicit one-time version-ownership binding.


Company administrators can author these profiles under **Linux clients →
Application version profiles**, download reviewed configuration and export a ZIP
PR proposal with a reusable recipe, example configuration and software/explanation
text. Nothing is automatically submitted or deployed. Syntax-only validation:

```sh
bearings-linux validate-applications --config client-config.example.json
```

Reusable contribution recipes live in `profiles/`; they are not automatically
enabled by installation. See the [profile editor and contribution contract](../../docs/integrations/linux-application-probes.md#gui-editor-and-exporting-a-pr-proposal).


## Automatic client updates

After enrollment, opt in once with the reviewed installer:

```sh
sudo python3 bearings-install.py auto-update-enable --server https://bearings.example
```

A randomized daily systemd check uses verified HTTPS, skips unchanged binaries,
retains identity/state/profiles/drop-ins, and restores the previous version when
replacement/startup fails. Interrupted transactions have boot recovery, failed
publications are quarantined, and a failed client during 24-hour probation can
restore its previous version. The updater stays local and does not execute a
replacement installer downloaded from the server. Inspect/disable with:

```sh
sudo python3 /usr/local/lib/bearings-linux/update.py auto-update-status
sudo python3 /usr/local/lib/bearings-linux/update.py auto-update-disable
```

See [update operations, recovery and limits](../../docs/operations/linux-client-updates.md).


## Uninstall

On the Linux host, use the current installer with administrative rights.

```sh
sudo python3 install.py uninstall
```

The command attempts to deregister the device, stops reporting and updates,
and removes the managed program, systemd units, dedicated account, local key,
and unsent queue. It preserves administrator-managed profiles and drop-ins.
If the server cannot confirm deregistration, check the device in Bearings.

A company administrator can also choose **Deregister and uninstall** on
the device under **Inventory reports**. The device loses report access
immediately. The systemd timer installed by the current installer polls
for its own removal about every 15 minutes. Hosts installed before this
feature need the current installer to add the timer. The portal shows
the acknowledgment separately from local cleanup. Asset and report history
remain in Bearings.
