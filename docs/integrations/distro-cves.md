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

A device evaluation locks its current source/device and holds a shared feed-generation lock; contention uses NOWAIT and retries rather than blocking a refresh. It requires fresh authorized reports, current source binding, a live device and matching installation ownership. Evaluation is bounded to 30,000 relevant definitions, 2,000 package/definition/CVE results and 120 seconds. Exceeding a budget rolls back the whole evaluation, retains prior evidence and shows an error. These bounds protect processing; they are not a demonstrated national-fleet throughput SLA.

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
