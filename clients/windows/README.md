# Bearings Windows client

SPDX: AGPL-3.0-or-later. [Source](https://github.com/rommelfs/bearings), [license](../../LICENSE), [receiver and coverage](../../docs/integrations/windows-agent.md).

## Install and enroll

Ask your administrator for the ZIP that matches **System type** in **Settings → System → About**. Use **x64** for 64-bit Intel or AMD Windows, **ARM64** for ARM Windows, and **x86** for 32-bit Windows. Windows 10 version 1709 or later, or a compatible Windows Server release, is required. Each ZIP contains a standalone console executable with its Go runtime. The endpoint uses Windows system libraries, the registry, DPAPI and its certificate store.

Compare the ZIP's SHA-256 with the supplied `SHA256SUMS`. The reference packages are unsigned. Extract `bearings-windows.exe` into a permanent directory writable only by the reporting account and trusted administrators. Run it as the ordinary Windows account that will send reports, with read access to the machine registry. The server needs migration `0073_windows_inventory` ([native server upgrade](../../docs/operations/ubuntu24.md#windows-inventory-upgrade-from-6acb4c8)).

Open PowerShell in the directory containing the EXE:

```powershell
.\bearings-windows.exe --version
.\bearings-windows.exe init
```

In the company's **Linux / Windows inventory reports** page, a company administrator or platform superuser approves this public key for an **existing asset** and creates a one-use registration code. Enter it at the hidden interactive prompt:

```powershell
.\bearings-windows.exe enroll --code
.\bearings-windows.exe report
.\bearings-windows.exe status
```

The grant contains the administrator-configured HTTPS origin. For a private approved CA, append `--ca-file C:\Approved\bearings-ca.pem` to enrollment. You can provide this file when retrying the same code after a certificate error. Keep codes out of arguments, logs and screenshots. The code expires after 30 minutes and the device credential after 90 days. If a code becomes unusable, have the administrator inspect the grant/device before canceling or revoking it as applicable. For a reviewed replacement, initialize a fresh key in a new private state directory and retain any prior queued reports for review.

`collect` prints local inventory only. Handle its output as confidential. `status` reports the latest acknowledged observation. `pending` means the server accepted it for processing. Check for `applied` before scheduling regular reports.

## Automatic reporting

`watch` sends a report at startup and runs in the foreground, repeating every six hours by default. For regular reporting via Windows Task Scheduler:

- Run under the **same account and profile** as enrollment. For an interactive pilot, select **Run only when user is logged on** and leave **Run with highest privileges** unchecked.
- Set a daily trigger that repeats every six hours for one day. Enable starting after a missed run and select **Do not start a new instance** for overlaps.
- Set **Program/script** to the absolute path of the extracted EXE and **Add arguments** to `report`. If you chose a private `--state-dir`, include the same absolute path as for enrollment.
- Run the task manually, then use `status` to verify that Bearings applied the report.

## State, coverage and validation

The default state is `%LOCALAPPDATA%\Bearings\Windows`. The same account can reuse the existing Python client's DPAPI state, key, sequence counter and queued report bytes. Stop the previous reporting task before switching its executable and retain the same state path. Keep the state local and private. It is protected with user-scoped DPAPI, an exclusive file lock and atomic replacement. Keep the original profile and directory when updating.

`flush` retries existing reports. During an outage, collection keeps saving complete samples up to 64 queued reports, with a 5,000-component and 1 MB limit per report. The client removes a queued observation only after the server acknowledges its exact UUID, sequence and SHA-256. Each report covers the Windows build and additional software registered in machine uninstall registry views. Per-user, Store, portable, hotfix and KB inventory, and automatic Microsoft CVE applicability, are outside this scope.

Linux cross-builds verify the three executable targets, with portable tests for signatures, HTTPS delivery and state compatibility. Native DPAPI, registry, locking and Task Scheduler acceptance require a Windows test endpoint. A [proposed Windows CI job](windows-ci.patch) is available for workflow-authorized activation.

## Build from reviewed source

On the build machine, use Python 3.12+ and Go 1.24+ from a clean reviewed checkout:

```sh
python3 scripts/build_windows_client.py --go /path/to/go
```

This writes architecture-specific EXEs and ZIPs, `SHA256SUMS` and a matching source ZIP into `.local/windows-client`. Distribute the source ZIP with the binary packages. For a native developer test, run `go test ./...` from `clients/windows` on Windows. The Python source remains available as a compatibility reference.
