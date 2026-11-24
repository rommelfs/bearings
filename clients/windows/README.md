# Bearings Windows reference client

SPDX: AGPL-3.0-or-later. [Source](https://github.com/rommelfs/bearings), [license](../../LICENSE), [receiver and coverage contract](../../docs/integrations/windows-agent.md).

The client sends the OS build including UBR, reported product name, edition and display release, and machine-installed software from the Windows uninstall registry views. Periodic reporting uses existing Bearings enrollment, Ed25519 HTTP signatures and verified HTTPS. Setup requires **Windows 10 version 1709 or later (or a compatible Windows Server release), Python 3.12+, uv, a reviewed checkout with its frozen `uv.lock`, and an existing Bearings asset**. Use native ARM64 Python on ARM64 Windows so the reporting scope is consistent. Distribute the Python source and its locked dependencies through your approved channel. Native Windows acceptance is pending. The proposed [Windows CI patch](windows-ci.patch) requires workflow write permission to activate.

Open PowerShell from the reviewed checkout under the Windows account that will run scheduled reports. Use an unprivileged account with read access to the machine registry and exclusive write access to its local state and checkout, apart from trusted administrators.

Prepare the server with migration `0073_windows_inventory` before enrolling
the client. See the [native server upgrade from `6acb4c8`](../../docs/operations/ubuntu24.md#windows-inventory-upgrade-from-6acb4c8).

```powershell
uv sync --frozen
uv run --frozen python clients/windows/bearings_windows.py collect
uv run --frozen python clients/windows/bearings_windows.py init
```

`collect` prints local inventory only; review it as confidential. `init` prints the public key and enrollment flag, never the private key. Keep the source checkout, Python environment and its parent paths writable only by the reporting account and trusted administrators. Do not initialize reusable Windows images.

In your company's **Linux / Windows inventory reports**, paste that public key, select the **existing Windows asset**, and create a one-use registration code. The form requires a company administrator or platform superuser. Do not select new-host registration for this reference. Back in PowerShell:

```powershell
uv run --frozen python clients/windows/bearings_windows.py enroll --code
uv run --frozen python clients/windows/bearings_windows.py report
uv run --frozen python clients/windows/bearings_windows.py status
uv run --frozen python clients/windows/bearings_windows.py watch --interval 21600
```

Paste the code into the hidden prompt in an interactive PowerShell console. Keep codes out of arguments, environment variables, screenshots and logs. For a private approved CA, append `--ca-file C:\Approved\bearings-ca.pem` to `enroll --code`, including when retrying the same code after a certificate error. The client adds the CA to default trust and verifies HTTPS against the operator-configured origin in the grant.

`report` collects once and attempts delivery. `watch` runs in the foreground every six hours by default. For automatic reporting via Windows Task Scheduler, create a task and use these settings:

- Run under the **same Windows account and profile** used for enrollment. For an interactive pilot, select **Run only when user is logged on** and leave **Run with highest privileges** unchecked.
- Set a daily trigger that repeats every six hours for one day. Enable starting after a missed run and select **Do not start a new instance** for overlapping runs.
- Set **Program/script** to the absolute path of the checkout’s `.venv\Scripts\python.exe`. Set **Add arguments** to `"C:\path\to\bearings\clients\windows\bearings_windows.py" report`, replacing the example with the absolute script path. If you chose a state directory during enrollment, append the same absolute `--state-dir`.
- Run the task manually to check its result, then run `status` from PowerShell under the same account and verify that the report was applied. Task Scheduler and unattended account profiles still need native acceptance.

State defaults to `%LOCALAPPDATA%\Bearings\Windows`. Key, enrollment request, counters, queued report bytes and latest receipt are encrypted together with user-scoped Windows DPAPI. An exclusive Windows file lock serializes processes; encrypted state is flushed then atomically replaced. Updates must retain this directory and Windows profile. Never clear/copy state to repair connectivity or clone devices. An administrator or compromised reporting account remains trusted; DPAPI is not TPM attestation or protection against state rollback by that account.

Use `flush` to retry retained reports. During an outage, automatic cycles continue saving complete samples locally, up to 64 reports, with limits of 5,000 components and 1 MB per report. At capacity, delivery must make progress before a new sample can be saved. Each receipt must match the exact UUID, sequence and SHA-256 before the queued bytes are removed. `pending` means the server has durably accepted the report. Use `status` for its processing result and the portal for receipt history and ownership review. Watch reports errors without raw exception details and retries on the next interval.

The registration code expires after 30 minutes and the device credential after 90 days. If enrollment failed and the original code is unusable, check the grant and device in the portal before starting again. For controlled replacement, ask the administrator to cancel any pending grant or revoke the existing device as applicable, then initialize a fresh key in a new private state directory. Keep the old state for review if it contains pending reports.

Missing versions are empty/unknown. This is not a list of every installed file: per-user software, unloaded user profiles, MSIX/Appx/Store packages, portable programs, WSL, driver inventory, hotfix/KB enumeration, repository candidates, runtime state and Microsoft CVE/KB applicability are **not implemented**. No `Win32_Product` query, installer consistency/repair invocation, package execution, network scanning, uninstallation, software update or NetBox mutation is performed by collection/reporting.

Local acceptance on a Windows test endpoint (no report delivery):

```powershell
uv run --frozen python -m unittest discover -s clients/windows -p test_client.py
```

The separate Django Windows tests use synthetic registry fixtures and the real independent server signature verifier. Passing them on macOS/Linux does not validate Windows registry, DPAPI or scheduling behavior.
