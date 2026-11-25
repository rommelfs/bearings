# Software coverage and CVE evidence

Start at **Infrastructure overview → Software coverage & evidence → Inspect every
software installation**. To inspect one host, open its inventory page and choose
**Inspect coverage for every installed software version**.

The workflow is **host → software and recorded version → mapping → version rule
and original CVE evidence → saved assessment and next action**. Pages read retained
local data. They do not fetch advisories, start scans, change mappings or create
assessment decisions.

## Understand what is counted

The installation ledger includes every retained installation in the permitted
company, including OS/firmware entries, inactive hosts and inconsistent ownership
links. Each installation belongs to exactly one inventory category:

- inventory link needs review;
- retained or unavailable observation;
- version missing;
- distribution package identity recorded;
- product watch configured;
- product watch missing.

The categories sum to the installation total. These are **inventory and mapping
prerequisites**, not a percentage of software fully evaluated or confirmed safe.
A configured product watch can still be paused, stale, unsupported or missing
version-rule evidence. The detail row explains those conditions separately.

Unlinked client observations have their own count and paginated list. They are
not included in installation totals; linked observations are not counted again.
Explicitly excluded observations remain visible. These are record populations,
not deduplicated physical programs: similar names do not authorize automatically
merging an unlinked report with a manual installation.

Search and the optional host scope apply to the installation total. Inventory
category filters narrow the displayed rows while keeping the full scoped category
breakdown. Pagination retains the search, category and host. The separate
observation list has its own host/name search and pagination.

## Read a software row

Each row shows the recorded version, original product identifier, mapping or
candidate, observation time when available, and evaluation evidence or a gap.
A manual/imported version without an observation timestamp is not presented as a
live client observation. Inconsistent company/source links retain an accounted
entry while withholding foreign identities and intelligence.

Supported Linux package results reuse the existing evaluator's input fingerprint,
feed generation, source/device binding, observation freshness and Ubuntu proof
checks. A current check covers its supported vendor rules, not all software or
all kernel/runtime conditions. Zero indexed rules is an explicit gap.

Application examples require a current enabled product watch, a complete fresh
source snapshot, the same installation/product/watch, matching immutable advisory
revision and evaluation snapshot, and unchanged evaluation inputs. A changed
version, vendor payload, Windows observation, mapping or Windows rule invalidates the
currentness claim. An advisory missing from the latest snapshot stays historical.

At most four visible automatic rule examples are previewed per installation.
Each identifies the CVE, **evaluated version**, evaluator rule, evaluation date,
explanation and separately saved analyst assessment/workflow. Explanations are
escaped and bounded to a 2,000-character preview; the original retained evidence
is unchanged. Open the original advisory/review link for manufacturer references,
full evidence and assessment actions. All visible reviews remain reachable even
when they are outside the preview or do not have an automatic rule.

A matching affected-version rule requires local applicability assessment. Unknown
conditions remain unresolved. Missing/hidden evidence, empty index results and
zero recorded reviews never establish absence of vulnerabilities. Saved human
decisions remain independent and are never changed by visiting the ledger.

## Recognize platform limits

The overview now labels its existing machine ratios as **Linux package checks**.
Their denominator is the permitted active-machine inventory; they do not measure
complete application or Windows coverage. Inventory gaps and recorded technical
coverage limitations are visible outside the monitoring diagnostics.

Windows OS servicing lines, Hotpatch/LTSC/ESU and unsupported application tracks
remain explicit gaps. This UI does not invent those facts or add manufacturer
rules. Cached KB inventory does not prove CVE remediation. See the
[Windows evidence contract](../integrations/windows-cves.md) and
[Linux vendor-rule limits](../integrations/distro-cves.md).

## Deployment and validation

Deploy the reviewed server commit using the existing upgrade procedure, collect
static files and restart `bearings-web`. No new migration, Windows/Linux client
upgrade, re-enrollment or worker reconfiguration is required. Preserve inventory,
source permissions, device keys and analyst decisions. Deployment does not enable
new upstream access or initiate production scans/notifications.

Tests use synthetic inventory and advisories, including Windows signed-report
fixtures and PostgreSQL. Local desktop/mobile browser checks use offline rendered
fixtures and do not establish what an authenticated production instance currently
shows. See [validation](../validation.md).
