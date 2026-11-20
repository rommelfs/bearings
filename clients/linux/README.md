# Bearings Linux reference client

A native, dependency-free Go client for **outbound authenticated inventory observations**. SPDX: AGPL-3.0-or-later; see the repository [license](../../LICENSE). This is a bounded Linux reference implementation, not a patch installer, remote shell, complete endpoint scanner or proof that a compromised machine is truthful.

The receiver, permissions, threat model, limits and validation are documented in [Linux observations](../../docs/integrations/linux-agent.md). Windows, TPM, mTLS, automatic credential renewal, signed release packages and fleet-scale ingest acceptance are not implemented by this reference.

## Build from reviewed source

Install the Go language compiler **1.24 or newer**, then from the repository root:

```sh
python3 scripts/build_linux_client.py
```

If `go` names another program, use `--go /path/to/the/go/compiler`. The build uses only Go's standard library, disables module downloads and produces static Linux amd64/arm64 binaries plus `SHA256SUMS` in ignored `.local/linux-client/`. Source revision and dirty state are embedded. Checksums detect changes; they are **not** operator release signatures. Preserve the source/license when distributing a build. ARM64 is cross-built; execute on intended ARM64 systems before accepting that deployment.

The examples below call the selected binary `bearings-linux`. No installer is fetched/executed and no service is installed automatically.

## Enroll once

On the actual Linux machine, under the account that will own its key:

```sh
bearings-linux init
```

This creates private state under `$XDG_STATE_HOME/bearings-linux` or `~/.local/state/bearings-linux` and prints **only the public key and fingerprint**. Repeating init preserves its key. Use `--state-dir /private/path` consistently for another location. State is mode 0700; key/config/grant files must be owned by that account and mode 0600. Do not enroll a reusable machine image.

In Bearings, open the company overview or an existing asset and choose **Linux inventory reports** (`/organizations/COMPANY/agents/`). A company administrator or platform administrator pastes the public key, selects the existing asset and downloads a one-use grant. CIRCL analyst status alone cannot authorize devices. The grant expires after 30 minutes and is bound to this public key, company, asset and inventory source.

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
