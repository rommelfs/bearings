# Bearings Windows reference client

SPDX: AGPL-3.0-or-later. [Source](https://github.com/rommelfs/bearings/tree/main/clients/windows), [license](../../LICENSE), [receiver and coverage contract](../../docs/integrations/windows-agent.md).

Implemented outbound authenticated Windows machine inventory: OS build including UBR, reported product name/edition/display release, and additional machine-installed software registered in the 32-bit and 64-bit uninstall registry views. Periodic reporting uses the existing Bearings device enrollment, Ed25519 HTTP signatures and verified HTTPS. This first reference requires **Windows, Python 3.12+, uv, a reviewed checkout with its frozen `uv.lock`, and an existing Bearings asset**. It is Python source, not a signed standalone executable or Windows service installer. Native Windows acceptance is pending; a Windows CI job is supplied.

From the reviewed checkout in PowerShell, under the Windows account that will also do the periodic reporting:

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

The enrollment prompt hides the registration code; never put codes in arguments, environment variables, screenshots or logs. For a private approved CA, append `--ca-file C:\Approved\bearings-ca.pem` to `enroll --code`. Normal Windows certificate trust is retained and the CA is added; certificate verification cannot be disabled. The grant's operator-configured HTTPS origin is the sole reporting destination. No redirects or server-supplied commands are followed.

`report` sends once. `watch` runs in the foreground every six hours by default; keep the process running or explicitly configure Windows Task Scheduler to call `report` periodically with absolute paths to the reviewed environment's Python and script. Run the scheduled task under the **same Windows account and profile**, with a consistent `--state-dir` if specified. No task/service is installed automatically; Task Scheduler deployment and service-account profile acceptance need target validation. Starting watch or scheduling report authorizes that periodic collection/delivery profile.

State defaults to `%LOCALAPPDATA%\Bearings\Windows`. Key, enrollment request, counters, queued report bytes and latest receipt are encrypted together with user-scoped Windows DPAPI. An exclusive Windows file lock serializes processes; encrypted state is flushed then atomically replaced. Updates must retain this directory and Windows profile. Never clear/copy state to repair connectivity or clone devices. An administrator or compromised reporting account remains trusted; DPAPI is not TPM attestation or protection against state rollback by that account.

Use `flush` to retry retained reports. Queue limits are 64 reports, 5000 components and 1 MB per report; exhaustion/failure stops new reporting without silently discarding pending input. Every successful receipt is checked against the exact report UUID, sequence and SHA-256 before removing local pending bytes. `pending` means durable receipt; `status` distinguishes processing from applied/rejected/superseded. A rejected receipt remains locally visible through encrypted state/status; previously applied inventory is retained. Watch logs only a fixed failure message and retries next interval.

Missing versions are empty/unknown. This is not a list of every installed file: per-user software, unloaded user profiles, MSIX/Appx/Store packages, portable programs, WSL, driver inventory, hotfix/KB enumeration, repository candidates, runtime state and Microsoft CVE/KB applicability are **not implemented**. No `Win32_Product` query, installer consistency/repair invocation, package execution, network scanning, uninstallation, software update or NetBox mutation is performed by collection/reporting.

Local acceptance on a Windows test endpoint (no report delivery):

```powershell
uv run --frozen python -m unittest discover -s clients/windows -p test_client.py
```

The separate Django Windows tests use synthetic registry fixtures and the real independent server signature verifier. Passing them on macOS/Linux does not validate Windows registry, DPAPI or scheduling behavior.
