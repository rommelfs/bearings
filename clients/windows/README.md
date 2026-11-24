# Bearings Windows client

SPDX: AGPL-3.0-or-later. [Source](https://github.com/rommelfs/bearings), [license](../../LICENSE), [receiver and coverage](../../docs/integrations/windows-agent.md).

## Install and enroll

Open `/downloads/windows/` on your Bearings server. Choose the ZIP that matches **System type** in **Settings → System → About**. Use **x64** for 64-bit Intel or AMD Windows, **ARM64** for ARM Windows, and **x86** for 32-bit Windows. The native Bearings publisher prepares the Windows and Linux packages together. If the server has no download links, ask your administrator to run the [client publisher](../../docs/operations/ubuntu24.md#client-downloads). Windows 10 version 1709 or later, or a compatible Windows Server release, is required. Each ZIP contains a standalone console executable with its Go runtime. The endpoint uses Windows system libraries, the registry, DPAPI and its certificate store.

Compare the ZIP's SHA-256 with the supplied `SHA256SUMS`. The reference packages are unsigned. Extract `bearings-windows.exe` into a permanent directory writable only by the reporting account and trusted administrators. Run it as the ordinary Windows account that will send reports, with read access to the machine registry. The server needs migrations `0073_windows_inventory` and `0074_windows_code_enrollment`. The server-built EXE contains the approved HTTPS origin.

```powershell
Get-FileHash .\bearings-windows-x64.zip -Algorithm SHA256
```

Substitute the ZIP you downloaded if using ARM64 or x86.

### Setup window

Double-click `bearings-windows.exe` under the account that will send reports.
Paste the same bounded rollout key used for Linux and choose **Register and
enable reports**. The client registers the computer as a new host in the
organization authorized by the key, sends the first report and creates a task
that runs every six hours while the account is signed in. The Windows hostname
is a self-reported label. Browsing reports and checking receipts stay in the
organization’s inventory workspace.

Open **Inventory clients → Rollout keys** if your administrator has not
already issued a key. The same key works for Linux and Windows. A rollout key authorizes a limited number of new hosts
and determines their inventory mode. Windows verifies HTTPS using the system
certificate store. For a signed-out schedule, use the manual setup and verify
that the reporting account can access its Windows profile and DPAPI state.

### PowerShell setup

Open PowerShell in the directory containing the EXE.

```powershell
.\bearings-windows.exe --version
.\bearings-windows.exe enroll --code
.\bearings-windows.exe report
.\bearings-windows.exe status
```

Keep codes out of arguments, logs and screenshots. The device credential
expires after 90 days. The administrator can review an expired credential
or cancel an unused grant in Bearings.

`collect` prints local inventory only. Handle its output as confidential. `status` reports the latest acknowledged observation. `pending` means the server accepted it for processing. Check for `applied` to confirm the first report reached inventory.

## Roll out to several computers

Pilot one Windows host first. Copy the reviewed EXE to the other devices using your software distribution tool. Each device uses the authorized rollout key and its reporting account to register a new host. Confirm its first applied report in Bearings. Keep the rollout key out of scripts, logs and reusable images, and keep device state on the original device.

## Automatic reporting

In the setup window, **Check status** shows the Windows task and the latest
report separately. If enrollment succeeded but the task could not be created,
choose **Enable automatic reports** to retry under the same account. The
client accepts an existing matching task and displays the Windows error when
creation fails. If the task has different settings or is disabled, review it
in **Task Scheduler** under **Task Scheduler Library**. Its name starts with
**Bearings Windows Inventory**. Check **Last Run Result** after running it.

`watch` sends a report at startup and runs in the foreground, repeating every six hours by default. For regular reporting via Windows Task Scheduler:

- Run under the **same account and profile** as enrollment. For an interactive pilot, select **Run only when user is logged on** and leave **Run with highest privileges** unchecked.
- Set a daily trigger that repeats every six hours for one day. Enable starting after a missed run and select **Do not start a new instance** for overlaps.
- Set **Program/script** to the absolute path of the extracted EXE and **Add arguments** to `report`. If you chose a private `--state-dir`, include the same absolute path as for enrollment.
- Run the task manually, then use `status` to verify that Bearings applied the report.

For signed-out operation, validate the task with the intended account’s loaded profile and DPAPI access before rolling it out.

## Update an enrolled client

1. Download and verify the new ZIP for the same architecture. Extract it into a staging folder and check the staged EXE with `--version`.
2. Pause the scheduled task and let active reports finish. Stop foreground `watch` if used. Keep a copy of the old EXE and replace it in `%LOCALAPPDATA%\Programs\Bearings`. If the earlier setup copied the executable but could not create a task, replace that copy as well, then choose **Enable automatic reports**.
3. Keep the account, profile and state directory so the enrollment and pending reports carry over. Run `report` and `status` and confirm the new report is applied before re-enabling the schedule.

For binary rollback, use the prior compatible EXE with the current state directory.

## State, coverage and validation

The default state is `%LOCALAPPDATA%\Bearings\Windows`. The same account can reuse the existing Python client's DPAPI state, key, sequence counter and queued report bytes. Stop the previous reporting task before switching its executable and retain the same state path. Keep the state local and private. It is protected with user-scoped DPAPI, an exclusive file lock and atomic replacement. Keep the original profile and directory when updating.

`flush` retries existing reports. During an outage, collection keeps saving complete samples up to 64 queued reports, with a 5,000-component and 1 MB limit per report. The client removes a queued observation only after the server acknowledges its exact UUID, sequence and SHA-256. Each report covers the Windows build and additional software registered in machine uninstall registry views. Per-user, Store, portable, hotfix and KB inventory, and automatic Microsoft CVE applicability, are outside this scope.

Linux cross-builds verify the three executable targets, with portable tests for signatures, HTTPS delivery and state compatibility. Native window rendering, DPAPI, registry, locking and Task Scheduler acceptance require a Windows test endpoint. A [proposed Windows CI job](windows-ci.patch) is available for workflow-authorized activation.

## Build from reviewed source

On the build machine, use Python 3.12+ and Go 1.24+ from a clean reviewed checkout:

```sh
python3 scripts/build_windows_client.py --go /path/to/go --server https://bearings.example
```

This writes architecture-specific EXEs and ZIPs, `SHA256SUMS` and a matching source ZIP into `.local/windows-client`. Distribute the source ZIP with the binary packages. For a native developer test, run `go test ./...` from `clients/windows` on Windows. The Python source remains available as a compatibility reference.
