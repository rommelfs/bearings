# Automatic Windows client updates

Operator-built Windows clients check for a signed Bearings client release after
an inventory report attempt. Checks run at most once an hour; the normal Windows
task reports every six hours while its account is signed in. The update activates
an immutable versioned executable in the private program
directory. The existing task entry path verifies its signed activation record
and starts that version. The next invocation uses the new client.
Foreground `watch` starts the new executable and resumes after its normal interval.
An open setup window keeps running its loaded version until closed and reopened.

This updates **the Bearings executable**, not Windows, drivers or applications.
Windows Update inventory continues to read the local WUA cache without patching.
The updater preserves enrollment, DPAPI protection, the device key, report counter
and exact queued report bytes. A failed update does not fail an inventory report.

## Activate on the server

Use the normal reviewed server upgrade, frozen production dependencies and client
publisher from a clean checkout:

```sh
python3 deploy/ubuntu24/ecosystem.py prepare-clients
```

The native publisher builds Linux and Windows before switching their download
directories together. For Windows it uses the repository's production virtual
environment, creates `/etc/bearings/ecosystem/windows-release.key` once with mode
0600, and embeds its public Ed25519 key, the approved HTTPS origin, commit and
release sequence in all three executable architectures. It signs `update.json`,
which covers the exact ZIP and executable hashes and sizes. The key is separate
from rollout keys and device signing keys. The source ZIP contains public build
flags, never the private release seed.

Back up this private key with protected server configuration **before the first
client rollout**. Keep access restricted to the publisher and trusted
administrators. Losing or changing it prevents already installed clients from
trusting future releases. If a signed current release exists but its key is
missing, publication stops. Restore the original key; do not generate a
replacement to work around the error. Rotation requires a separately reviewed
bootstrap of clients with the new public key.

Publication verifies the previous signed manifest with that same key and origin.
The new sequence is at least the current build time in UTC seconds and exceeds
the preceding sequence as necessary. This handles a clock moving backwards. Build
failures leave active download pointers unchanged. A server rollback to an older
release is visible to clients as `server_older`; it never downgrades a client.

For a separate authorized publisher, use Python with the frozen production
`cryptography` dependency and an existing private base64 32-byte Ed25519 seed
outside the checkout:

```sh
.venv/bin/python scripts/build_windows_client.py --go /path/to/go \
  --server https://bearings.example \
  --signing-key /protected/windows-release.key \
  --previous-manifest /previous/windows/update.json \
  --output /new/windows-release
```

Omit `--previous-manifest` only for the first signed release. The optional
`--release-sequence` must exceed the previous sequence. Publish the complete
immutable output directory, including the source ZIP and `SHA256SUMS`, through
`BEARINGS_WINDOWS_CLIENT_DIR`. Do not put the private key in that directory.
Developer builds without a signing key have no self-update trust anchor.

## Bootstrap existing computers once

Older clients cannot install their own updater. Download and verify the reviewed
ZIP once from the upgraded Bearings server, pause the existing task, finish active
reports, stop `watch`, retain the old EXE and replace its executable at the
existing task path. For the setup-created task this is
`%LOCALAPPDATA%\Programs\Bearings\bearings-windows.exe`. Keep the same account,
profile and state directory. Do not enroll again. Re-enable the task, run it and
confirm an applied report. New signed publisher builds enable client updates by
default; later releases then install automatically on a report attempt.

Under that same Windows account, from the installed EXE directory:

```powershell
.\bearings-windows.exe --update-info
.\bearings-windows.exe update --auto-update=status
.\bearings-windows.exe update
.\bearings-windows.exe update --auto-update=disable
.\bearings-windows.exe update --auto-update=enable
```

`--update-info` is an offline build probe. `update --auto-update=status` reads
local update state without network access. `update` forces a check and may install
a newer release even when automatic checks are disabled. `enable` and `disable`
persist only the local preference. Use the same `--state-dir` as reporting if it
is customized. Task status, report status and client update status are independent.
`current` means there is no newer signed release, not that the report was applied.

## Trust and failure handling

Downloads use only fixed paths on the enrolled and embedded HTTPS origin, retain
system/approved CA validation and reject redirects. They send no rollout key,
device credential or inventory. The client verifies the Ed25519 signature before
using metadata, enforces increasing release sequences, bounds downloads and ZIP
contents, and verifies the executable's hash, PE architecture and offline build
identity before installation. An operator with the private signing key can
publish executable code; protect that key accordingly. Initial ZIP verification
uses the administrator's trusted HTTPS download and checksum review. These
packages do not have Authenticode signatures.

The original executable remains a stable bootstrap. Each update stages and
synchronizes a separate `bearings-windows-release-<sequence>-<sha256>.exe`, checks
its offline build identity, then atomically switches
`.bearings-windows-current.json` using Windows `MoveFileEx` with write-through.
This avoids overwriting a running Windows process image. The bootstrap verifies
the activation signature, origin and executable digest before forwarding the
original command, input/output and exit status. It performs no network request
or registry/WUA collection during forwarding. `--update-info` deliberately probes
the specific file without forwarding; `--version` shows the effective client.

A directory-wide update lock prevents concurrent activation through different
profiles or executable versions. Links/junctions are rejected. The prior signed
activation is synchronized to `.bearings-windows-current.json.previous` before
switching. A failed protected-state save restores that record; the initial
bootstrap remains usable if there was no prior activation. If restoration fails,
the previous record and validated executable remain available for administrator
recovery. The signed active sequence also provides the rollback floor when a
crash commits activation before its DPAPI metadata save. Partially staged files
are never activated. Missing/corrupt active files produce a visible fallback to
the bundled client, whose normal report attempt can retry the update.

The current and previous activated releases are retained. Cleanup only attempts
to remove older generated release files; Windows keeps images that are still in
use. Keep the original task/shortcut entry path rather than pointing it at a
generated release filename. The stable bootstrap itself is retained: replacing
its trust key or refreshing its bootstrap runtime requires a reviewed manual
replacement. Application/client versions used for reporting update automatically.

An unwritable program directory, unsupported filesystem/Windows operation,
application control, unavailable server, bad signature/hash, wrong architecture
or startup-probe failure leaves an explicit error and preserves report state.
No elevation, service creation, reboot, remote command or Windows Update policy
change is attempted. Restore access or investigate the error, then run `update`
to retry immediately; automatic retries wait for the next eligible report.
Functional regressions after a successful startup probe still need operator
review. An intentional rollback must be reviewed and republished with a higher
sequence and compatible state; never erase DPAPI state or its rollback record.

Native synthetic tests exercise activation while a bootstrap stays running,
real HTTPS signed-release installation and command forwarding, DPAPI/outbox
preservation, and rollback with and without a prior activation on state-save
failure. A Windows pilot is still needed for the target fleet's
NTFS/application-control behavior and its actual reporting task. The atomic
metadata switch uses Microsoft
[MoveFileEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw).
