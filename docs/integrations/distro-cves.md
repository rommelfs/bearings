# Automatic distribution CVE discovery

Standard packages from signed Linux reports are inventoried and evaluated automatically; company administrators do not map every package to a Vulnerability-Lookup vendor/product. This is a bounded vendor OVAL implementation, not complete vulnerability or remediation attestation. Public vendor definitions are cached once per distribution release and evaluated locally. No IP address, hostname, installed version, package list or company identifier is sent to these vendors.

## Supported inputs and sources

- Ubuntu 20.04/focal, 22.04/jammy, 24.04/noble and 26.04/resolute: Canonical `security-metadata.canonical.com/oval/com.ubuntu.<codename>.cve.oval.xml.bz2`, exact binary package and distribution EVR.
- Debian 11/bullseye, 12/bookworm and 13/trixie: `www.debian.org/security/oval/oval-definitions-<codename>.xml.bz2`, exact **source package name and source version reported by dpkg-query**, mapped to the installed binary. Never substitute a binary version for a source version, including binNMU suffixes.
- RHEL 8/9/10: `security.access.redhat.com/data/oval/v2/RHEL<major>/rhel-<major>.oval.xml.bz2`, exact RPM package/EVR. Signature, module-stream and other unreported predicates stay unknown. Rocky, AlmaLinux, CentOS and other derivatives are not silently treated as RHEL.

These are fixed operator-controlled HTTPS destinations. Availability/lifecycle of a release is still a vendor dependency. Unsupported platforms show missing coverage. An explicit `CONNECTOR_ALLOWED_HOSTS`/egress proxy list must permit the three hostnames above; default settings include them. Verified TLS, destination checks, no redirects, bounded requests and no tenant-provided URLs apply. Outbound DNS/egress enforcement remains necessary in production.

The updated client adds optional dpkg source metadata to the existing report schema. Deploy server dependencies and migration **0060** before rebuilding/publishing clients. Existing Ubuntu/RPM reports remain usable; legacy Debian reports show missing source metadata until an updated client reports. Reinstalling the official installer preserves host identity, registration, key and queues. Third-party repository origin/signature is not attested by a host OS label.

## Scheduling and failure semantics

`run_worker` invokes `sync_distro_cves` after agent processing by default (`BEARINGS_DISTRO_CVE_ENABLED=1`). The command refreshes at most one needed feed and evaluates at most five queued devices per invocation; `--limit` accepts 1–100. Reports and changed vendor generations queue evaluations. Successful feeds refresh after six hours, failures retry after fifteen minutes, and twelve-hour-old caches are marked stale. An indexed pending-device queue and feed/package lookup avoid an upstream request per package/host. Initial download, parsing and cache population happen in the background and can take minutes; registration/public pages do not wait for them.

A ten-minute feed lease prevents duplicate refreshes; downloads and parsing happen outside database locks. Bounds: 32 MiB compressed, 384 MiB expanded/normalized, 120-second download and parse budgets, six million XML events, 100,000 definitions, 4,096 CVEs/definition. DTD/entities, duplicate identities and incomplete/trailing compressed data are rejected. Parse/normalization must finish before atomic cache publication. Errors retain the last complete generation and its evidence. PostgreSQL is required for concurrent workers; SQLite is a single-worker fallback.

A device evaluation locks its current source/device and holds a shared feed-generation lock; contention uses NOWAIT and retries rather than blocking a refresh. It requires fresh authorized reports, current source binding, a live device and matching installation ownership. Evaluation is bounded to 30,000 relevant definitions, 10,000 package/definition/CVE results and 120 seconds. Exceeding a budget rolls back the whole evaluation, retains prior evidence and shows an error. These bounds protect processing; they are not a demonstrated national-fleet throughput SLA.

## Results and review

Native Debian and RPM comparators (`univers`) preserve epochs, vendor releases, backports, tilde/caret semantics and parallel installations. Supported OVAL AND/OR/NOT, package objects, inventory guards and finite architecture predicates use three-valued evaluation. Unsupported regex/object sets, runtime/file/module/signature facts and definition extensions remain unknown. Definitions with no indexable package are counted as uncovered rather than reported safe.

A matching vendor rule creates a scoped CVE finding with **potential** applicability; unresolved conditions create **unknown** applicability. Source revision and reported binary/source inputs are retained as immutable evidence. Vendor severity can be displayed without inventing a CVSS score. An update can change automated evidence to `not_affected`; removal becomes `not_observed`. Neither closes the analyst workflow or overwrites a human assessment. Unchanged definition semantics do not reopen review merely because another definition changed in the feed.

The Linux client page shows cache/evaluation freshness, queued work, partial/unsupported/error coverage and links to the asset's CVE reviews. Standard-package discovery pages describe this automatic path. **No matching rule is not proof of safety**, successful installation is not proof that running processes were restarted, and self-reported facts cannot prove a compromised host truthful. Remaining work includes broader OVAL predicates, repository/signature/module provenance, vendor lifecycle assurance and sustained fleet-scale publication benchmarks.

## Operator checks

```sh
/opt/bearings/deploy/ubuntu24/manage.py sync_distro_cves --limit 5
journalctl -u bearings-worker -n 60 --no-pager
```

The first command processes local queued evaluations and public vendor downloads only; it does not patch systems, scan networks, notify contacts or write to NetBox. Tests use synthetic local inventories; opt-in actual public XML regression is documented in `portal/test_distro_live.py`.

## Visible package association and compiler updates

Automatic discovery cards show each reported binary/version/architecture, optional reported source package, exact release/feed lookup name and the number of **indexed vendor definitions** for that package. These are candidate associations, not confirmed affectedness. Recorded potential/unresolved reviews have a direct installation-filtered link; product review links are also scoped. Pending evaluation, stale reports, unsupported releases, missing Debian source metadata and vendor-cache refresh are explicit. Device-wide `partial` coverage is explained separately instead of being presented as the individual package's mapping status. Standard-package cards do not ask the user to configure a generic product watch; existing explicit additional watches remain manageable without changing their identity or state.

Rendering performs no upstream requests or rule evaluations. Current authorized product IDs, source/asset/component consistency checks, five installation previews per product, grouped feed-index/review counts and batched edit/audit checks bound the page. A twelve-additional-package regression checks that query count does not grow per card. This is request-local display work, not a new claim about national-scale publication throughput.

Compiler version 2 recognizes Canonical's singleton Unix family and exact Ubuntu codename guards with `check="at least one"`, as used in the actual vendor feed. Only known OS-file expressions/constant values are recognized; unsupported patterns, operations and references stay unknown. Debian's known major-version expression is retained. Each complete feed records the compiler version. A newer compiler causes the worker to refresh/recompile even when compressed feed bytes and recent success timestamps have not changed; old compiled generations are pending until successful replacement, and the same complete-cache/error/lease protections apply. Publishing the new generation queues device reevaluation without client reinstallation. No database migration is needed for this version marker.

Software identity and CVE matching readiness are independent of current findings: cards distinguish a normalized reported package identity, recognition in indexed vendor definitions, automatic matching readiness/queue/cache state, and current retained reviews. A supported package can be monitored for future vendor advisories even when there are no current matches. Platform-disabled matching, stale inputs and evaluation errors do not claim ready status. CPE is optional additional identity; distro packages use exact PURL/release/native-version/source-package evidence to preserve backports instead of guessing an upstream CPE.

Inventory and asset software tables reuse these statuses for their bounded displayed installation lists, with no outbound calls or per-row evaluation. Exact-product discovery links preserve organization authorization. Scoped, raw-visible retained review counts are separate from coverage/readiness; zero does not establish safety. Manual known-CVE retrieval is a collapsed, explicitly optional editor action in machine details, not the default inventory action.


## Package-check results versus human reviews

Migration **0062** adds a server-owned `AgentComponent.distro_check` receipt and queues existing enabled devices for background reevaluation. A complete successful device evaluation atomically replaces each eligible package's receipt. No client update, new outbound destination or per-package watch is required. The receipt binds the installation, report ID, binary/source identity and version, OS, feed generation, rule hashes and evaluation/vendor-data timestamps. Failed evaluation retains the previous receipt; it is never presented as a current successful result after an error.

The UI distinguishes **potentially affected**, **unresolved**, **fixed by installed package version**, and **other vendor rules not matched**. A fixed result requires a supported native `version < fixed-version` predicate to fail for the reported package, all other leaf conditions to be true, non-package guards to be true, no negation, and a false overall vendor predicate. Architecture/signature/runtime mismatches and arbitrary false rules are not fixed-version proof. Debian source comparisons explicitly identify the compared source version rather than presenting the binary version as the comparison input. Multiple definitions for one CVE are deduplicated per package, preferring potential/unresolved over a negative result.

A rule not matching or being absent is **not an explicit manufacturer declaration of non-applicability**. The current vulnerability OVAL sources do not provide a complete list of such declarations; the UI does not invent “not affected” outcomes for omitted CVEs. An initially fixed package generates no finding merely to record a negative check. Existing finding revisions, analyst assessments and workflow states remain unchanged by these receipts and are displayed separately; an update does not close human reviews.

Each receipt retains complete outcome counts and up to ten recent CVE examples **per outcome**, with the definition identity/hash and fixed-version proof where available. It is a bounded latest-check summary, not an unlimited historical scan ledger. Evaluation additionally caps distinct package/CVE outcomes at 100,000 per device and rolls back on overflow. Existing 30,000-definition, 10,000 positive/unknown finding and 120-second budgets remain. Rendering reads stored receipts only. It requires current ownership, current report inputs, matching feed generation, live device/report/cache and enabled evaluation; a newer pending signed report also suppresses a current-success headline. Unsupported, queued, failed, stale and no-indexed-rule states are distinct. A usable retained cache after a failed vendor refresh displays a warning and its original verification time. Even an unalerted evaluated package is not proof of complete server coverage, trusted repositories or restarted running code.


## Local evaluation failures and capacity

The previous 2,000-match publication limit could reject an otherwise valid full
host inventory. The bound is now 10,000 package/definition/CVE associations per
host. A synthetic PostgreSQL regression publishes 2,001 associations, their
immutable revisions and a complete package receipt through the real publication
path; exceeding the bound still publishes nothing. This is a capacity bound,
not a count of distinct CVEs or confirmed vulnerable packages, and not a fleet
throughput guarantee. The 120-second transaction deadline and the separate
30,000-definition / 100,000-proof / 100,000-outcome limits remain enforced.

`ConnectorError` alone did not distinguish these local resource guards from
connector problems. New failed attempts persist an allowlisted `error_code`,
concrete reason and next action. Codes distinguish advisory/result/proof limits,
evaluation/publication deadlines and overlong source identities. Arbitrary
exception values, credentials and response bodies are not shown. Old errors
cannot be retrospectively classified; the next worker attempt supplies the new
diagnostic. The worker's existing fifteen-minute failure retry remains in place.
Failures retain earlier evidence, package receipts and human workflow; the
coverage panel does not display invented zero-match totals for a failed attempt.

Deploy the reviewed checkout and restart **bearings-web** and **bearings-worker**.
No migration or Linux binary rebuild is needed for the evaluator change. The
separate installer recovery fix requires republishing the installer and refreshing
the root-owned updater as described in [client updates](../operations/linux-client-updates.md).


## Batched evidence publication

A successful rule evaluation could still exceed the existing 120-second budget
while writing thousands of associations one at a time. Increasing the result
count bound alone did not address that publication bottleneck. The evaluator
now writes source revisions, findings, immutable match history and vulnerability
issue projections in batches of at most 200 associations. Current and retained
fixed-rule associations use the same batch path. Removed/rebound inputs retain
their conservative detached-match path. Eligible component/device relationships
are reused instead of lazily reloading the same host per component.

The entire device evaluation remains one transaction. A deadline failure after a
completed batch rolls back all batches, including issues/revisions; previous
package receipts, analyst assessments, workflow, sharing policy and existing
issue fields are retained. SourceRecord bulk updates explicitly recompute source
severity using the ordinary model-save rule and capture both previous and current
payloads. New issue projections use the same model validation and snapshot
format as ordinary issue creation, validating the scoped object chain before
assigning a new UUID; no existing issue is repointed.

Before taking evidence-record locks, publication locks the host's existing
findings in PK order. Human review/risk linking takes Finding before SourceRecord;
the whole host set is locked before batching because later batches can share an
evidence record. Within each batch, finding locks precede match locks. This avoids
introducing the opposite order and preserves concurrently saved human fields.

The 120-second deadline, 10,000-association bound and all rule/proof limits remain.
A publication-version marker retries old `publication_timeout` failures on the
first eligible worker pass after this upgrade. A failure under the current
publication version keeps the normal fifteen-minute retry backoff. Successful
package proofs retain evaluator version 2; this performance change does not
invalidate every current package proof or reopen unchanged analyst reviews.

Update the reviewed checkout and restart **bearings-web** and **bearings-worker**.
No migration, static rebuild, Linux client update or artifact republishing is
needed. Check the new evaluation timestamp/state/code on the affected host; local
synthetic query budgets are not proof of production latency or fleet throughput.

## Ubuntu source status and running-kernel coverage (compiler 4, receipts 3)

Canonical's OVAL package-presence rules alone do not prove whether an installed
version is affected. For a positively matched presence-only branch, Bearings now
consults the fixed official endpoint
`https://ubuntu.com/security/cves/<CVE>.json`. It requires the exact CVE, Ubuntu
codename and reported **source** package name/version. A `released` status supplies
a native Debian fixed-version comparison; `not-affected` supplies an explicit
vendor decision. Binary and source versions are not interchangeable. Unknown
Boolean guards, contradictory pockets, absent source identities, unsupported
versions and `needed`, `needs-triage`, `pending`, `ignored`, `deferred` or unrecognized
statuses remain unresolved. No fuzzy name or upstream version guess is used.

The shared cache retains normalized public release/source status, content hash,
verification time and safe error category. At most four fixed-URL HTTPS requests
run concurrently per worker pass, outside device/source transactions, with TLS,
no redirects, bounded JSON and twenty-second deadlines. Refresh starts after six
hours; twelve-hour-old evidence is stale; failed fetches retain previous data and
retry after fifteen minutes. Egress must allow **ubuntu.com** as well as the OVAL
host. Explicit `CONNECTOR_ALLOWED_HOSTS`/proxy policies must include it; the default
allowlist includes it. `BEARINGS_UBUNTU_STATUS_FETCH_ENABLED=0` pauses public JSON
refresh, not the age/currentness checks. Failed requests can be inspected by a
platform superuser in Django admin's read-only Ubuntu CVE statuses list.

Immutable package evidence includes the exact supplementary response hash,
selected release/source statuses and native comparison. Cached changes immediately
invalidate current verdicts in detail, receipts and SQL review queues. Persistent
dependencies also requeue initially fixed packages with no existing Finding;
staleness cannot leave those silently cleared. A new inventory or evidence result
never overwrites a saved human assessment/workflow. Lookup/result budget failures
roll back the complete device transaction. Pending cache population is displayed
as uncertainty, not as a completed successful check.

Compiler 4 recognizes only Canonical's exact `0:` + captured Ubuntu ABI local
variable and a bounded literal uname series/flavor grammar. It never evaluates
arbitrary vendor expressions/regexes. Every indexed runtime-kernel definition is
accounted for in separate matched/not-matched/unresolved counts. Versioned matches
retain all positive rules and comparisons in immutable kernel evidence, exposed
through the client's check and a scoped, paginated **Running-kernel evidence**
page. These technical kernel matches are separate from package CVE reviews and
saved analyst decisions; a positive match creates a visible review recommendation.
Evidence over 16 MiB or incomplete definition accounting aborts the whole device
transaction rather than publishing a truncated success.

The Linux client optionally reports `os.kernel_scope`: `host`, `shared` or
`unknown`, using a bounded fixed systemd container-detection command. Missing or
failed detection remains unknown. Explicit LXC/OpenVZ/container asset metadata
also forces shared scope, including for old clients. A container's distribution
feed cannot clear the host's kernel: assess the hosting system with its own
inventory/distribution. An unrecognized kernel flavor/build, presence-only kernel
rule or unsupported guard remains unresolved. Zero matching definitions does not
establish kernel safety. Kernel-only installations still appear in coverage and
positive-match recommendations, even without bound package software records.

Coverage displays counts by specific uncertainty reason plus current package and
version examples. Missing source-package metadata is a collection action; vendor
triage, shared host scope and unsupported conditions are explicit limits, not
instructions to reinstall packages. Full indexing is not full affectedness proof.
Read paths remain organization/source scoped and perform no upstream requests.

Deployment requires **migrations 0068–0071**, restart of **bearings-web** and
**bearings-worker**, and rebuilding/publishing the Linux client for automatic
kernel-scope reporting. Old clients remain accepted with unknown/shared scope.
No key rotation, new enrollment or NetBox policy change is needed. Publish only a
clean checkout with `python3 deploy/ubuntu24/ecosystem.py prepare-linux-client`.
Existing enabled update timers pick up the client; a manual check is
`systemctl start bearings-linux-update.service`. Inspect the new check's timestamp,
source-status reasons and kernel scope; initial JSON cache filling takes multiple
bounded worker passes. All remaining uncertainty stays visible.

Validation distinguishes synthetic correctness tests from public source checks:
compiler 4 indexed all 37,611 definitions in the retained noble vendor download
and all 25,983 in the fetched focal download on 2026-11-23, with zero unindexed
definitions. These are feed-specific observations, not a guarantee for future
feeds or a declaration that any production host is unaffected.
