# Windows 11 evidence pilot

The first pilot covers a Windows 11 Pro 22H2 ARM64 baseline and a later, separately
authorized OS upgrade. The implementation exports one scoped, retained observation
for diagnosis. It does **not** install Windows updates, certify patch compliance,
change a product watch or alter an analyst assessment.

## Install the current release first

Use the [server and Windows upgrade guide](windows-update-installation.md). Keep
the existing Windows account, DPAPI state, enrollment and task entry path. Choose
the **ARM64** package on ARM Windows, even when an x64 application runs through
emulation. Confirm `report` followed by `status` reaches `Report status: applied`.
Then enable/run the existing scheduled task once and confirm another applied
report. Client-update status, scheduled-task status and report status are separate.

Windows 11 Pro 22H2 (build branch 22621) reached end of updates on **2024-10-08**.
That is a lifecycle fact, not proof of a specific missing CVE fix. See the
[Microsoft announcement](https://learn.microsoft.com/en-us/lifecycle/announcements/windows-11-22h2-end-of-updates-home-pro).
Capture this baseline before planning an OS upgrade through your normal process.
The Bearings client does not perform that upgrade. A system-information screenshot
showing only build 22621 lacks the UBR needed for a version-rule comparison.

## Export one pilot observation

This command becomes available when the **separate Windows pilot change** is
installed; it is not part of software-coverage PR #139. On the native server, use
an existing active actor with access to the company. Find the device UUID in the
company's inventory-client detail URL. Do not substitute an asset UUID.

```sh
umask 077
/opt/bearings/deploy/ubuntu24/manage.py windows_pilot \
  --actor YOUR_AUTHORIZED_USERNAME \
  --organization YOUR_COMPANY_SLUG \
  --device YOUR_DEVICE_UUID > /protected/pilot-before.json
```

Choose an existing private output directory. The command reads one device and its
exact signed, retained report; it performs no network fetch, scan or inventory
write. Sensitive operator reads use the existing audit mechanism. Invalid tenant,
source, report or installation links stop the export with a generic error.

The JSON contains:

- observed full build/UBR, edition, release, role and native OS architecture;
- a reviewed architecture-specific MSRC ProductID and source document, when known;
- separately reviewed lifecycle status, or an explicit lifecycle gap;
- report UUID, sequence, observation time, body SHA-256 and currentness;
- this report's cached installed/pending KBs, query coverage and restart evidence;
- servicing-channel/update-line declarations and unresolved evidence gaps;
- a versioned diagnostic rule and fingerprint; `cve_compliance` remains
  `not_established`.

Hostnames, application names, update titles, network addresses, device public keys,
private keys and credentials are omitted. The export is still inventory metadata;
keep it private. Do not publish the original `collect` output or pilot exports in
the public repository. Tests use synthetic reports only.

## Interpret the results

`current: true` means the observation is fresh, source-consistent, applied and the
latest acknowledged report for that device. It does not mean Windows is fully
patched. Revoked, expired, stale, inactive, missing or pending observations remain
explicitly noncurrent. Retained last-success WUA rows are never promoted into this
report's evidence. Failed or partial queries and an unknown/old search-cache date
remain gaps. A zero pending-update count is not a patch-compliance verdict.

The finite catalog currently reviews Windows 11 22H2, 24H2 and 25H2 on ARM64/x64.
It requires a client role, a supported non-LTSC edition and agreeing release,
complete build, kernel and native architecture. An MSRC ProductTree CPE may encode
a particular serviced build; the pilot does not copy that build as the observed
version or infer a fixed threshold from it. The historical 22H2 IDs are retained
from the 2024-October document, rather than requiring a retired product to appear
in the latest monthly document. Other products stay unresolved.

Only 22H2 Home/Pro lifecycle dates are implemented in this pilot. Enterprise,
Education, LTSC, Hotpatch, ESU and other release lifecycle/entitlement rules are not
borrowed from that rule. Existing Windows CVE evaluation remains unchanged; see
[its evidence contract](../integrations/windows-cves.md).

## Compare after an authorized change

After a client/reporting fix or an OS update approved through your normal process,
send a fresh report, wait for `applied`, and export `pilot-after.json` using the
same actor, company and device. Compare the full build, native architecture,
report sequence/date, product ID, lifecycle and update-query outcomes. A changed
fingerprint identifies changed diagnostic evidence, not an automatic improvement
in security. Preserve both snapshots; do not clear enrollment or report history.

Acceptance needs an actual ARM64 task run, local WUA query, offline/outage recovery
and signed client-update activation. Synthetic server tests prove parsing,
ownership, revision and failure semantics, not those native operations. Existing
Windows updater CI validates synthetic activation independently of real registry,
WUA and fleet policy behavior.

## Reuse what the pilot teaches

Keep manufacturer identities, lifecycle facts, version comparisons and evidence
currentness as separate rules. Reuse the synthetic ARM64/x64 and conflicting-role
matrix for other Windows releases; adding one row requires its own manufacturer
source. Installing every OS is unnecessary for those pure rule checks. Native
collector/task/updater acceptance is still needed for materially different Windows
versions, architectures or policies; one ARM64 pilot cannot validate all of them.
