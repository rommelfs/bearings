# Install or upgrade the Windows client with update inventory

This guide supplements the [Windows client guide](../../clients/windows/README.md)
and the [native Ubuntu server upgrade procedure](../operations/ubuntu24.md#updates-and-recovery).
It does not perform production actions automatically. Upgrade the server first,
then a Windows pilot. Preserve existing accounts, keys, databases and DPAPI state;
do not reinitialize or enroll an already registered client again.

## Upgrade an existing native server

As the responsible administrator, first back up the database, `/etc/bearings` and
private application state, and verify recovery. The procedure below applies to an
existing native installation in `/opt/bearings`; other installations should use
their established upgrade process.

Run as root. Review local changes separately; the procedure stops if the checkout
is not clean. Before stopping services, compare the displayed target commit with
the published merge. The checkout is pinned to that commit. Do not run first-time
installation or seed example data during an upgrade.

```sh
set -eu
cd /opt/bearings
test -z "$(git status --porcelain)"
git fetch origin main
reviewed=$(git rev-parse FETCH_HEAD)
git show --no-patch --oneline "$reviewed"
git merge-base --is-ancestor HEAD "$reviewed"
systemctl stop bearings-web bearings-worker bearings-national
git switch --detach "$reviewed"
/opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12
./deploy/ubuntu24/manage.py migrate --noinput </dev/null
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
./deploy/ubuntu24/manage.py check </dev/null
python3 deploy/ubuntu24/ecosystem.py prepare-clients --no-restart
systemctl start bearings-web bearings-worker bearings-national
systemctl is-active bearings-web bearings-worker bearings-national
```

Preserve existing integration permissions, customer/source bindings and systemd
overrides. If a step fails, inspect the cause and service logs before continuing.
This increment needs no additional schema migration after 0074; `migrate` also
applies any older outstanding migrations. After web/worker startup, verify the
public HTTPS pages and an authorized host view.

## Download and set up the Windows client

The server rebuilds and publishes client downloads when `prepare-clients` runs
during its upgrade. New signed publisher builds update the Bearings executable automatically after
report attempts. Older installed clients need **one manual bootstrap replacement**
below; they cannot install the updater themselves. Later releases are checked by
the same six-hour reporting task. See [automatic Windows client updates](../operations/windows-client-updates.md)
for signing-key backup, status, retry and recovery.

1. Open `/downloads/windows/` on the upgraded Bearings server. Download the ZIP
   for **x64**, **ARM64** or **x86**, and compare its SHA-256 with `SHA256SUMS`.
   The packages are currently not Authenticode-signed.
2. Extract the files under the account that will submit reports. For a **new
   installation**, start the EXE and select **Register and enable reports** using
   the existing shared Linux/Windows rollout key. Alternatively, use `enroll --code`.
3. For an **existing client**, pause its scheduled task, let active reports finish,
   stop foreground `watch` and retain a copy of the old EXE. Replace
   `%LOCALAPPDATA%\Programs\Bearings\bearings-windows.exe` with the new version.
   Keep the account, profile and `%LOCALAPPDATA%\Bearings\Windows` unchanged.
   If the task uses another executable path, replace that executable instead.
4. From the EXE directory, run under the same account:

```powershell
.\bearings-windows.exe --version
.\bearings-windows.exe report
.\bearings-windows.exe status
```

`Report status: applied` confirms the processed report. If it is `pending`, check
`status` again later; do not create duplicate hosts by enrolling again. Re-enable
the existing task and start it manually once. Check the task result and report
status separately. The corrected Task Scheduler definition and new WUA query still
require a real Windows pilot; cross-compilation does not validate native execution.

## Inspect update evidence

Open the host detail or select the host under **Inventory clients → Linux /
Windows inventory observations**. The **Windows Update** section shows:

- installed and locally cached pending software updates, with KB links, update
  IDs, revisions and hidden-update flags;
- query status, total count, bounded lists and incomplete results;
- the last successful Automatic Updates search as a separate cache-age hint;
- observed restart requirements and retained historical results after failures.

The client requires built-in **Windows PowerShell 5.1** and read access to the
local Windows Update Agent. It does not require an elevated login or bypass
execution policy. Application control, a disabled WUA service or a timeout produces
missing update evidence; registry reporting can continue. No online scan, download,
patch, restart or WSUS/update-policy change is performed. Missing or zero pending
updates do not establish a current patch level. Driver updates and the complete
CBS/MSI history are not included. Complete product-specific Hotpatch/LTSC/ESU/CVE
rules remain outstanding.
