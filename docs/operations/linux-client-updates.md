# Automatic Linux client updates

Automatic updates are an explicit, per-host administrator choice. They update the
installed Linux inventory binary from one trusted Bearings HTTPS origin; they do
not upgrade the server, operating system, packages or configured applications.
Publish only reviewed client artifacts after upgrading the server. Existing
installations and newly enrolled hosts use the same enablement command.

## Enable, inspect and disable

First publish the current installer on the Bearings server:

```sh
cd /opt/bearings
python3 deploy/ubuntu24/ecosystem.py prepare-linux-client
```

On an installed/enrolled client, download outside the source checkout and enable:

```sh
cd /root &&
curl --fail --show-error --proto '=https' \
  https://bearings.circl.lu/downloads/linux/install.py -o bearings-install.py &&
python3 bearings-install.py auto-update-enable --server https://bearings.circl.lu
```

Add `--ca-file /path/to/public-ca.pem` when the fixed update origin requires a
private CA. The public PEM is validated and copied to a separate root-readable
updater file. Certificate and hostname checks stay enabled; redirects and origin
URLs containing credentials, paths or queries are refused. Do not use insecure
TLS options. No rollout key or re-enrollment is required.

Enablement installs a root-owned **local** updater under
`/usr/local/lib/bearings-linux/update.py`, private configuration at
`/etc/bearings-linux/update.json`, a daily timer with up to four hours of jitter,
an additional randomized check after boot, and local recovery services. The timer
is persistent, so missed calendar checks are caught up. Failed runs first invoke local recovery and then schedule a separate retry after
15–20 minutes, subject to the unit's three-starts-per-hour budget; the daily timer
continues to provide later checks. This spreads load across large deployments.

```sh
sudo python3 /usr/local/lib/bearings-linux/update.py auto-update-status
sudo systemctl list-timers bearings-linux-update.timer
sudo systemctl start bearings-linux-update.service
sudo journalctl -u bearings-linux-update.service -u bearings-linux-update-recover.service --no-pager -n 60
sudo python3 /usr/local/lib/bearings-linux/update.py auto-update-disable
```

Status includes the configured origin, actual timer enabled/active flags, last
attempt/success/failure and rollback/quarantine fingerprints. A successful check
with unchanged checksums downloads only the small manifest, not the binary, and
never restarts reporting. Disabling the timer also persists disabled policy;
already scheduled retry processes exit without downloading. Ordinary reporting
and boot recovery remain installed. No web command channel is added.

## Transaction and recovery contract

The manual installer, scheduled updater and recovery actions share the same
root-owned exclusive lock. Downloads use verified HTTPS, timeouts, no redirects,
bounded responses and manifest SHA-256 checks. A candidate must be the native ELF
architecture and pass the existing version/identity checks as the dedicated
unprivileged account. The main unit must match a locally reviewed unit digest;
unknown future unit changes require refreshing the reviewed local installer.

Before changing installed files, save the prior binary/unit and a durable
transaction marker under `/var/lib/bearings-linux-updater/`. Atomic file writes,
file/directory fsync and checked backup hashes support recovery after interruption.
Enrollment key, configuration, queue, local profiles and custom drop-ins are not
part of the replaced files. A paused client stays paused. An active client's
replacement must remain active across checks after 1, 2 and 4 seconds; otherwise
restore prior files and restart the previous client. This is a startup check,
not report-delivery, process/runtime or full application-health attestation.

The updater has an OnFailure recovery service. A separate recovery unit runs
before the client at boot; the client requires that unit, so an unresolved
recovery failure prevents starting an uncertain replacement. A successful update
retains a 24-hour probation record and previous files. A later failed client
service triggers local recovery too, provided its binary still matches that
publication. Deliberately stopping reporting does not trigger probation rollback.
Each replacement creates one current rollback baseline, not unlimited history.

Recovery runs locally before network access. A failed publication is quarantined
by binary/unit fingerprints: scheduled checks cannot repeatedly reinstall it.
A different publication is eligible automatically. After diagnosing a local
cause, an administrator can explicitly retry the quarantined publication:

```sh
sudo python3 /usr/local/lib/bearings-linux/update.py auto-update-retry
```

A pending interrupted update can be repaired without contacting the server:

```sh
sudo python3 /usr/local/lib/bearings-linux/update.py auto-update-recover
```

Missing/corrupt backups, unsafe ownership/paths and conflicting customized files
fail closed for review. Do not delete transaction markers or override the main
unit to force an update. Correct the filesystem/service problem and retry recovery.
Disk, kernel, hardware and total network failures cannot be made impossible;
recovery also needs readable backups and a writable destination filesystem.

The updater never downloads/executes a new installer as root and never updates
itself automatically. Refresh it explicitly using a reviewed current installer
and `auto-update-enable`. This keeps the recovery logic independent of a faulty
client release. HTTPS establishes trust in the configured publisher; manifest
checksums are integrity checks, not independently signed releases or downgrade
protection. Publication selection, release signing and fleet canary policies
remain operator responsibilities.

## Deploy this feature

No database migration or dependency change is introduced. On the server, collect
static files/templates via the ordinary deployment and restart `bearings-web`
when deploying the changed instructions. Publish from a clean reviewed checkout
with `prepare-linux-client`. Enable the updater once per enrolled host as above;
no manual client-service restart is needed. Key/state/drop-ins are preserved.


## Activation from a root shell retaining sudo identity

An older installer could fail with `Input must be a readable regular file within
its size limit, without a symlink` when copying its own `/root/bearings-install.py`
while the root shell retained `SUDO_UID` from an earlier sudo session. Its generic
input reader correctly drops to that user, who cannot traverse `/root`; using
that reader for the already-running installer was incorrect. The fixed self-copy
reads only the script already executing as administrator, with bounded regular
file/no-symlink checks. Binary, grant and CA inputs retain their invoking-user
read restrictions. Existing installed recovery drop-ins use the root-owned
installed-file reader too. Self-copy failures now identify that activation step.

For a direct root shell using the older downloaded file, this narrowly scoped
retry removes the inherited sudo identity for that invocation only:

```sh
env -u SUDO_UID -u SUDO_GID python3 /root/bearings-install.py \
  auto-update-enable --server https://bearings.circl.lu
```

For the permanent correction, deploy the fixed source and republish using
`python3 deploy/ubuntu24/ecosystem.py prepare-linux-client`. Re-download the
installer on the client and repeat `auto-update-enable`. No database migration,
server service restart or manual reporting-service restart is required for this
installer-only correction. Repeating enablement refreshes the local updater and
reloads/enables its units while retaining enrollment and reporting state.


### Activation lock and boot recovery

The initial activation also held the installer lock while synchronously starting
the boot recovery unit, whose installed CLI requires the same lock. The server
journal identifies this as `Another installer is running`. Configuration writes
and daemon reload remain under the exclusive lock; the configuring process now
closes its lock descriptor before asking systemd to start recovery and enable the
timer. The success message is printed only after both commands succeed. Failures
name the fixed systemctl operation/unit without exposing captured diagnostics.

If an older activation has already written configuration and failed in this
step, after its process exits complete activation with:

```sh
systemctl reset-failed bearings-linux-update-recover-boot.service
systemctl start bearings-linux-update-recover-boot.service &&
systemctl enable --now bearings-linux-update.timer
python3 /usr/local/lib/bearings-linux/update.py auto-update-status
```

`timer_active: true`, `timer_enabled: true` and no pending transaction establish
activation. `result: configured` does not establish a successful update check;
`systemctl start bearings-linux-update.service` performs one, then inspect status.
The fixed installer makes these recovery steps unnecessary for new activations.
The acceptance systemctl double now executes the actual nested recovery child
rather than merely returning success for its startup; it therefore detects lock
recursion. This still is not a complete real-systemd boot/power-cut test.
