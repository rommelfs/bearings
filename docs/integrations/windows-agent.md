# Windows machine inventory observations

Implemented reference increment, 24 November 2026. See [client setup and commands](../../clients/windows/README.md). This extends the existing [authenticated Linux observation receiver](linux-agent.md); its organization/source ownership, current authorization, expiry, revocation, replay and analyst-decision protections remain in force. No production rollout or operational data publication is performed.

## Collection and ownership

The standalone Windows client reads `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion` for reported product name, edition, display release, build and UBR. Build plus UBR is the observed OS version. ProductName is retained as reported; it is not normalized into a Windows 10/11 marketing identity or a Microsoft security product ID. Reboot requirement and effective remediation remain unknown.

Additional software comes from named entries under `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` in both explicit Windows registry views. View 32/64 describes the registration location, not verified binary architecture: component architecture is `all`. All named registrations, including entries hidden from Add/Remove Programs, are eligible; publisher/version may be unknown. Empty names are skipped. No install/uninstall command, executable path, username, user SID, product key or serial is collected. Per-user/Store/portable/WSL and KB/update inventories remain future capabilities.

The implementation follows Microsoft's documented [uninstall registry metadata](https://learn.microsoft.com/en-us/windows/win32/msi/uninstall-registry-key). Registration is self-reported evidence, not proof of complete software coverage, trusted publisher or vulnerability applicability. Windows DPAPI uses [user-scoped CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata) and [CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata) to retain confidential state; Windows administrators and the reporting account remain trusted.

A `windows-machine` report uses the existing `bearings.agent.v1` envelope with OS id `windows`, exactly one OS component, manager `win-reg`, no services/application probes and bounded `windows` evidence. OS component identity is `win-reg:os:all`. Program identity hashes the case-folded complete uninstall key and registry view; two views/installations are never merged just because names match. Receiver recomputes identities and validates paths, evidence, OS build consistency, counts and text bounds. Missing DisplayVersion is retained as an empty unknown version, never guessed.

Automatically inventoried registrations become separate installation records when the device's existing automatic-software policy allows it; OS receives the operating-system flag. Generic registration identifiers deliberately assert no vendor/CPE mapping. Existing manual software is not adopted by name. Subsequent reports own only their assigned version field. A product-name change or disagreement between two known publishers under a bound registry identity stops publication for explicit ownership review instead of silently retargeting an installation. Human assessments, build/edition ownership and evidence history remain separate. Reported Windows edition/release are retained in observation evidence, not adopted into manually maintained installation fields. A first curated application/MSRC-candidate increment is described in [Windows CVE evidence](windows-cves.md). Missing update-line/channel evidence and unsupported products remain unresolved; automatic Microsoft KB remediation/compliance is unavailable and no clean security result is inferred.

## Authorization and failure semantics

Windows reuses the Linux rollout protocol and limited rollout keys. Company administrators manage keys under **Inventory clients → Rollout keys**. **Profiles** opens the organization’s Linux application version profile editor. The EXE is built for the public HTTPS origin and validates it using Windows trust. During bootstrap it signs a request with its locally generated device key. It redeems the returned one-use grant for a new host using its self-reported hostname. Windows sends an empty address list in the initial host claim. The server retains the rollout’s company, source, host type, capacity limits and observed-only or managed NetBox policy. Existing assets are never joined by hostname, and the grant and exact enrollment body are retained locally for a retry without persisting the shared rollout key. Previously issued Windows single-asset codes remain redeemable for compatibility.

An organization administrator can request removal of a specific client. The next scheduled report uses a signed HTTPS exchange for that one fixed action. The helper acts only in the reporting account’s standard profile. The portal records acknowledgment before cleanup. HTTPS certificate trust is verified, redirects refused and request/response sizes and socket timeouts bounded. Enrollment retry preserves the request identity; report retry preserves exact signed body bytes, with a fresh transport signature. Public keys are printed; private keys/codes/raw transport exceptions are not logged.

“Complete” covers only successful reading of the declared **machine registry + OS** scope. A missing uninstall root is an empty scope. Access errors, detected concurrent edits or disappearance of an enumerated key, malformed/oversized fields, missing OS build metadata or count/body limits abort collection; no partial complete snapshot is transmitted. Delivery/admission failure retains pending bytes and last-known server inventory. Missing registrations from a later successful complete snapshot are flagged as not observed; they are never deleted and do not resolve findings. Unknown versions remain unknown even if a previous report had a version. Registry reads span multiple keys and can observe changes between reads. Failed collection does not refresh coverage timestamps.

## Validation and rollout boundary

Migration **0073** retains Windows component evidence and **0074** retains compatibility with previously issued Windows single-asset enrollment codes; apply it before restarting web/worker. The Windows EXEs bundle the Go runtime. The Python reference remains available for compatibility. Synthetic tests exercise registry views, Unicode/unknown versions, real signature admission, automatic OS/software projection, changes/missing retention, revocation, schema refusal, enrollment retry, explicit CA recovery, exact receipts, offline sampling and durable outbox behavior. A proposed native Windows CI job in [windows-ci.patch](../../clients/windows/windows-ci.patch) runs DPAPI tamper detection, state persistence/corruption refusal, concurrent locking and actual local registry collection, without printing/uploading inventory. That patch is supplied, not applied or executed: the current GitHub OAuth access lacks workflow permission. Apply through a workflow-authorized operator before relying on Windows CI.

The user reported `Report status: applied` from the Windows client, confirming one successfully processed real Windows report. Execution of the corrected Task Scheduler definition on real Windows remains pending. Endpoint ACL/account/profile behavior, independent Windows 11/Server/ARM64 installations and fleet acceptance remain **unvalidated** until exercised on those targets. Architecture-specific unsigned EXEs and ZIPs are built from reviewed source. The portal's `/downloads/windows/` guide supports operator-approved ZIP downloads, with checksums and matching source. The setup window reports the latest inventory receipt separately from the six-hour Task Scheduler task. Task setup verifies the stored definition for the same interactive account, reuses a matching task and displays a Windows diagnostic when task creation fails. Existing tasks with different settings or a disabled schedule are left for review in Task Scheduler. Authenticode signing and a Windows service remain planned. This is a reviewable first reference, not a fleet deployment acceptance claim.

## Windows Update cache inventory

The Go client now includes a fixed, embedded Windows PowerShell helper (built-in
Windows PowerShell 5.1 is required). It reads the local Windows Update Agent COM
cache with `Online=false` and `CanAutomaticallyUpgradeService=false`; it does not
contact an update server, install/download updates, change settings or bypass
PowerShell execution policy. Application control or a missing/disabled WUA service
may prevent collection; this is explicit unavailable/error evidence, not a clean
result. The registry inventory continues even when the optional query times out
(after 45 seconds), emits invalid/oversized data or exceeds the 1 MB report budget.

Optional `os.windows_update` evidence separately records installed and pending
**software update identities**, their revision/title, up to 16 KB identifiers,
hidden status, and at most 250 entries per query. Counts describe WUA identities,
not unique KBs. Superseded/hidden updates may appear. `ok`, `partial`, `error`,
`unavailable` and `timeout` remain distinct. Null counts denote failed queries;
truncated/partially successful queries cannot become complete results. Driver
updates, the complete CBS/MSI/hotfix history and install dates are not claimed.

WUA `SystemInfo.RebootRequired` supplies a separate three-state restart indicator.
The last successful Automatic Updates search date is retained as a separately
labelled UTC cache-age hint (it may not reflect other update tools); unknown or
older-than-24-hours cache dates are visible. Successful local cache queries, zero
pending updates and a negative restart indicator never prove full patch compliance
or CVE remediation. Per-product regular/Hotpatch/LTSC/ESU manufacturer/KB rules
remain a separate incomplete capability in [Windows CVE evidence](windows-cves.md).

Signed reports use the existing admission and source/device locks. The receiver
validates all bounds, UUID/revision/KB identities, counts, dates and restart
consistency. Clients cannot submit server-owned retained receipts. Last complete
installed/pending queries and last known restart evidence survive failed/partial
queries. Old clients remain accepted; a later report without update data retains
old evidence without refreshing its observation time, and labels it historical.
Changed builds, expired/revoked clients and changed source bindings also prevent a
current presentation. Raw signed report history retains the exact observation.

Both the authorized host detail and client observations page show this evidence,
including escaped titles and numeric-only Microsoft KB links. The CVE observation
fingerprint retains optional update evidence; rule v2 also corrects native Windows
architecture keys to `arm64` and `x86`. It does not infer a servicing line, ESU
entitlement, Hotpatch baseline or MSRC fix from a KB name. There is no new schema
migration after 0074. Upgrade web/worker before publishing the new client.

Microsoft API references:

- [Local-only search setting](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-uamg/31a1923c-fb3a-416c-825d-168a79ef5c95)
- [Search criteria and superseded updates](https://learn.microsoft.com/en-us/windows/win32/api/wuapi/nf-wuapi-iupdatesearcher-search)
- [Restart indicator](https://learn.microsoft.com/en-us/windows/win32/api/wuapi/nf-wuapi-isysteminformation-get_rebootrequired)
- [Automatic Updates search timestamp](https://learn.microsoft.com/en-us/windows/win32/api/wuapi/nf-wuapi-iautomaticupdatesresults-get_lastsearchsuccessdate)

Synthetic PostgreSQL admission/retention/rendering and Go tests/cross-compilation
validate the contract. Native WUA COM/PowerShell collection and corrected Task
Scheduler execution still need a real Windows pilot. See the
[German installation/upgrade guide](../user-guide/windows-update-installation.de.md).


## Asset update presentation

The asset page leads with pending Windows Update cache entries and visible vulnerability reviews. Positive historical counts are labeled as last recorded. Unavailable or partial empty observations leave the backlog unknown. The technical cache query and synchronization statuses use labeled icons with explanations on hover and keyboard focus.
