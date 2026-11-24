# Windows product mapping and CVE evidence

Status: first integrated increment, 2026-11-24. This is **partial coverage**,
not a complete Microsoft update compliance engine. No production evaluation,
deployment, notification, patching or merge is part of this change.

## Evidence path

The existing Windows registration identity (`pkg:generic/windows-registration/…`)
and installation remain unchanged. The vulnerability worker's existing product
enrollment uses `windows-vendor-rules/v3` only when every active installation of
that product has one unambiguous, current mapping. It inspects at most 101
installations and refuses automatic enrollment above 100. It never adopts a
manual installation by name, changes an existing watch or re-enables a pause.
Unrecognized registrations cannot fall back to generic product-name suggestions.

A mapping is separate from a CVE decision. The existing CVE-JSON-5 product-watch
pipeline evaluates structured affected-product/version rules from its configured
public Vulnerability-Lookup source. Manufacturer references must use an explicitly
allowed HTTPS hostname with no credentials or alternate port. References are
links in the retained CNA evidence, **not independently downloaded, verified
patch contents** or proof that the manufacturer signed the registry publisher.
Only public vendor/product keys leave Bearings; inventory stays local.

Each Windows discovery revision retains the exact component/report identity,
observation time/version, registry facts, mapping version, CPE or MSRC product
candidate, gaps, reference links and original advisory revision. Its explanation
includes the observed version, rule, manufacturer reference and matching numeric
range. Unchanged inputs are idempotent. The same fingerprint function is used
for publication and currentness; a publisher, source, inventory age, observation
or rules change can invalidate a retained result without changing its version.

Missing observations, expired/revoked devices, mismatched tenant/source/asset,
foreign report references and manually maintained build/edition qualifiers
cannot establish a positive result. A source mismatch is rejected before copying
report metadata into a local review. Separate automatic evidence and immutable
history preserve human applicability, resolved workflow, private source records,
explicit watch identity and pause settings. Client pages show mapping gaps and
manufacturer links alongside the observed registration without network access.

## Initial application catalog

| Registry product and publisher | Canonical application CPE | Current behavior |
| --- | --- | --- |
| Microsoft Edge / Microsoft Corporation | `microsoft:edge_chromium` | Exact browser CNA product and numeric four-part rule required; Beta/Dev names excluded |
| Google Chrome / Google LLC or Google Inc. | `google:chrome` | Exact CNA product and numeric four-part rule required |
| Mozilla Firefox ESR / Mozilla | `mozilla:firefox_esr` | Explicit ESR name required; compare only within one ESR major, two/three numeric parts |
| Mozilla Firefox / Mozilla | `mozilla:firefox` | Candidate only: ordinary uninstall names do not distinguish ESR from release |
| 7-Zip / Igor Pavlov | `7-zip:7-zip` | Exact name with optional numeric version/architecture label; two-part numeric rule |
| Microsoft Edge WebView2 Runtime | None asserted | Own runtime product/rule required; shared Edge CPE cannot establish browser applicability |
| Office / Microsoft 365 | None asserted | Exact suite/release, MSI vs Click-to-Run and update channel missing |
| Adobe Acrobat / Reader | None asserted | Exact product and Classic/Continuous track missing |

The full CPE form is `cpe:2.3:a:<vendor>:<product>:*:*:*:*:*:*:*:*`.
CNA vendor/product aliases are explicitly curated too. A matching CPE alone does
not allow a different CNA product (especially WebView2) to become an Edge rule.
If CNA CPEs exist, the exact unqualified catalog CPE must be present; qualified
track/edition CPEs are not stripped. Generic Windows platform lists are supported;
other configuration/architecture constraints remain unresolved. No fuzzy name,
registry-view-to-executable-architecture or publisher-substring matching occurs.
Unknown versions, wildcard/default status, unsupported version types, status
changes, conflicting rules, configuration predicates and cross-ESR-major ranges
remain unknown. A nonmatching range never establishes a fixed/safe installation.

Catalog references reviewed for this increment:

- [Microsoft Edge security notes](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security)
  and [NVD's WebView2 advisory demonstrating the shared CPE](https://nvd.nist.gov/vuln/detail/CVE-2024-29049).
- [Chrome vendor release notes](https://chromereleases.googleblog.com/).
- [Mozilla Firefox advisories](https://www.mozilla.org/en-US/security/known-vulnerabilities/firefox/)
  and [separate ESR advisories](https://www.mozilla.org/en-US/security/known-vulnerabilities/firefox-esr/).
- [7-Zip vendor history](https://www.7-zip.org/history.txt) and
  [NVD CPE example](https://nvd.nist.gov/products/cpe/detail/cfa7785d-23d8-4f2e-8c48-a348465ba7da).
- [Adobe track-specific CPE example](https://nvd.nist.gov/products/cpe/detail/434081)
  demonstrates why removing `continuous` would lose a relevant constraint.

## Windows OS and update lines

The Go collector additionally reads `InstallationType` from the same native
CurrentVersion registry snapshot as edition, release and build/UBR. Old reports
remain accepted with this field absent. Roll out the receiver before the new
client. `ProductName` is not authoritative for the family: Windows 11 can retain
a Windows 10 label, and Server 2025 shares build 26100 with Windows 11 24H2.

The pure resolver jointly checks role, edition, release, build and native OS
architecture against a finite table. Client candidates cover Windows 10
1507/1607/1809/21H2/22H2 and Windows 11 21H2/22H2/23H2/24H2/25H2; server candidates
cover 2016/2019/2022/2025, distinguishing Server Core. Unsupported editions,
Server releases/architectures, Windows 11 x86 and inconsistent facts stay open.
These are **MSRC CNA product labels**, not a verified numeric MSRC ProductID
registry or an assertion that all those versions are still serviced.

The receiver accepts optional explicit OS `servicing_channel`
(`gac`, `ltsc`, `unknown`) and `update_line` (`regular`, `hotpatch`, `esu`,
`unknown`) declarations. The shipped collector **does not invent either field**.
Consequently, current ordinary client reports show OS candidates and missing
servicing evidence, but do not automatically enroll an OS watch. A fully declared
regular GAC client can be evaluated against its exact MSRC CNA product,
architecture and same-branch four-part `10.0.build.UBR` range. No comparison
crosses a Windows build branch. Manual build/edition qualifiers remain review
requirements rather than being overwritten by collector declarations.

**Hotpatch, LTSC and ESU remain unresolved**, including explicitly declared lines.
Higher UBR values are not used as proof across update lines. Dedicated per-product
rules still need baseline cycles, installed KB evidence, lifecycle dates,
entitlement/ESU evidence, Azure editions and exact applicability. Relevant vendor
references:

- [Supported Windows client releases and servicing options](https://learn.microsoft.com/en-us/windows/release-health/supported-versions-windows-client)
- [Windows 11 release/build information](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information)
- [Windows Server release/build information](https://learn.microsoft.com/en-us/windows/release-health/windows-server-release-info)
- [Hotpatch prerequisites and baseline behavior](https://learn.microsoft.com/en-us/windows/deployment/windows-autopatch/manage/windows-autopatch-hotpatch-updates)
- [Windows 10 ESU requirements](https://learn.microsoft.com/en-us/windows/whats-new/enable-extended-security-updates)

Historical Windows versions can retain imported installations and dated advisory
records through existing workflows. This increment does not add an importer,
historical OS/MSRC mapping or lifetime entitlement assumptions. Importing an old
product name alone does not enable this signed-observation evaluator.

## Validation and remaining work

Tests use synthetic registry data, signed admission through the real receiver,
synthetic CNA rules and an isolated PostgreSQL 17 database. No real-host inventory
is used. Native Windows installation, corrected Task Scheduler execution and
fleet acceptance remain separate. Manufacturer research is read-only; live
Vulnerability-Lookup coverage/completeness for each new key and future manufacturer
schema variations need independent acceptance. Missing index results do not prove
absence of vulnerabilities. No schema migration is introduced by this increment.

The Windows Update increment now supplies cached KB/update identities, pending software updates, restart evidence and a cache-age hint. Rule v2 retains this evidence in OS evaluation snapshots and uses native Windows architecture keys `arm64`/`x86`. It still does not infer servicing channels or fixed CVEs from KB presence. See [Windows Update evidence](windows-agent.md#windows-update-cache-inventory).

Manufacturer URLs are bounded to 2,048 characters without controls. Explanations contain only the evaluated version-rule fields and at most ten matching rule samples, with the total match count. Arbitrary extra CNA fields cannot be amplified into every installation review; the full original advisory remains retained separately.

Rule v3 rejects explicitly malformed interval bounds (including empty/zero values) instead of treating them as absent; exact-version rules do not need an ordering type. Unknown extra fields are retained only in the original advisory, not in repeated explanations.
