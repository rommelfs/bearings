# Linux authenticated inventory reference

Status: implemented bounded reference, 19 November 2026. Native Go client under [clients/linux](../../clients/linux/README.md); Django receiver, company management UI, durable reports and bounded worker. This adds no remote shell, patch installation, Windows agent, automatic case closure or public deployment.

## Ownership and access

A company administrator/platform administrator authorizes one public key for an existing organization/asset/source, or explicitly grants creation of one new host of a chosen kind. CIRCL visibility alone cannot enroll/bind/revoke. The one-use enrollment secret is stored only as a SHA-256 digest, expires after 30 minutes and requires proof of the preapproved Ed25519 key. An identical lost-ack retry is idempotent within its validity; another request cannot consume it again. Grants can be cancelled; cancelling an already-redeemed grant revokes the device. Credentials expire after 90 days and require reviewed replacement with a fresh key. The device grant belongs to the organization independently of its creator after activation; offboarding a person alone does not revoke delegated device credentials. Device disable/expiry and current source/asset/company ownership are checked on every authenticated delivery and publication.

Each enabled device is limited to one current asset; source binding and asset UUID are pinned. Hostname/IP do not authenticate ownership, deduplicate globally or bypass grants. Initial opt-in host declarations remain separate from authoritative NetBox facts and verified infrastructure claims. New-host NetBox device/VM creation uses the existing approved source/write queue and operator defaults; interface/IPAM/DNS writes are not added. Revoking a device stops subsequent report publication; it does not undo an already approved hardware submission in the separate inventory-write queue. Device replacement preserves the asset and existing findings, with explicit release/reassignment of software version ownership. Unsupported company merges/provenance cleanup remain protected by the new non-disposable references and require reconciliation.

New package observations do not silently become authoritative software. A company administrator explicitly binds a package slot to the version field of one installation on that same asset or creates a separately identified package record. This delegates that version field, not product identity, edition/build, NetBox infrastructure, source configuration, risk acceptance or finding workflow. Manual/CSV editing cannot overwrite a bound version; stale/missing facts do not erase known software. Existing product watches are requested after fresh actual version changes; names do not create affectedness or arbitrary upstream lookups.

## Ingress contract

POST-only HTTPS endpoints:

* `/api/v1/agent/enroll/`: public-key-bound bearer grant plus signed request.
* `/api/v1/agent/reports/`: signed device observations; durable receipt before background processing.
* `/api/v1/agent/status/`: signed query for that device's own receipt only.

Cookies/SSO sessions do not authenticate these machine endpoints. They intentionally use signature authentication rather than browser CSRF. Management forms at `/organizations/<slug>/agents/` retain normal session authorization/CSRF and current organization scope; operator reads and all grants/bindings/revocations are audited. No CORS grant is added. Machine responses are private/no-store and do not return advisory intelligence.

Fixed RFC 9421 profile: `bearings` label, signed application tag `bearings.agent.v1`, Ed25519 only, components `@method`, `@path`, `@authority`, `content-digest`, `content-type`, `x-bearings-key`. Creation and expiry are bounded to five minutes with at most 30 seconds forward clock tolerance; exact URI queries, content encodings, incomplete coverage and unexpected parameters are rejected. Body SHA-256 Content-Digest is validated separately. Delivery signatures are fresh on retry while original observation time/report bytes remain unchanged. RFC verification uses frozen `http-message-signatures` 2.2.x; the Go encoder is a fixed emitter, not a second general signature parser. No JWT/algorithm fallback or disabling of certificate verification is accepted. This profile is not FIPS validation or TPM attestation.

The strict versioned JSON contract includes a random report UUID, monotonic signed device sequence, original observation time, explicit collection scope/completeness, OS/kernel/reboot-indicator facts, native package slots/versions and optional fixed NGINX runtime observations. Duplicate keys, nonfinite numbers, excessive nesting, unknown fields, duplicates and oversize input are rejected. All fields are untrusted display text; no supplied URL/command is fetched/executed. No username, environment, process command line, MAC, file contents or connector secret is collected. Hostname/interface addresses are an explicit enrollment opt-in, not an implicit package-report side effect.

A unique device/sequence and report UUID plus a locked device admission record make retries idempotent and reject rollback/conflicting bytes. A duplicate only receives its original receipt. Source metadata is never selected from a caller-provided company/asset ID. Limits: one-megabyte/5,000-component report, ten pending inputs, ten seconds between new reports, 200 reports/32 MiB per UTC day per device. Enforce ingress connection/rate/storage budgets at the reverse proxy as well; per-device limits do not replace global/company admission control against mass enrollment or denial of service.

## Publication, uncertainty and retention

The consumed enrollment also retains its exact signed body, signature parameters/signature and target without retaining the bearer secret. `AgentReport` retains exact body, body hash, original signature parameters/signature, signed target/content type and verification public key. Receipt IDs/status do not expose raw reports across devices. Database commit precedes acknowledgment. The client authenticates receipts through verified HTTPS; receipts are not independently server-signed and the deployment must trust its TLS termination/proxy path. The client retains local input until the response acknowledges the exact ID/sequence/hash. Bounded input is processed by `process_agent_reports --limit 25`; the bundled worker calls it independently of HTTP processing. For another deployment schedule it explicitly.

Publication and revocation share a device lock; source serialization and current ownership checks precede version changes. A transaction publishes package observations, owned version changes and applied sequence together. Package and owned-version changes are batched; a 500-binding regression enforces a bounded SQL count. Failures preserve previous state; validation conflicts become rejected reports; database interruption retains pending input. Older publication cannot overwrite a newer applied sequence. Backward observation clocks require review. Original signatures authenticate source statements, not the truth of a compromised OS.

Each component keeps its own observation time. Partial data does not refresh other components or full-snapshot age. Runtime observations retain their own timestamp even when another report omits service checks. Full scoped collection may flag a prior component missing; it never deletes installations or resolves findings. Software data older than twelve hours is explicitly stale and cannot overwrite an owned canonical version. Receipt time, observation time, complete-package coverage and runtime coverage remain separate. The human correctness/reactivity test is unchanged.

A native package version preserves epoch/vendor release/backports; stripping it into a vendor SemVer match would be unsafe. Unknown distro-specific applicability remains unknown. RPM parallel kernel instances remain distinct. NGINX comparison covers only the configured systemd main process executable and guards PID reuse; executable equality is not worker/library/configuration coverage or proof that a vulnerability is remediated. No restart is performed.

Exact report history is confidential inventory. No automatic retention deletion is introduced: agree retention, referenced-evidence preservation, backup encryption/access and storage quotas before a large operational deployment. Native package inventories can be large; this full-scoped-snapshot reference is not the proposed delta/partitioned fleet protocol. Existing 40,000-company read benchmarks are not ingest capacity evidence. Real target OS/proxy/privilege and sustained ingest/refresh tests remain deployment gates.

## Run

After updating this revision, rebuild the application image once because the frozen signature-verification dependency is new:

```sh
python3 scripts/dev.py up
python3 scripts/build_linux_client.py
```

In the retained lab, a focused Bearings image build followed by `up --no-build` is equivalent when reusing unchanged native-service images. Cloud proxy/CA environments have `scripts/cloud_image_build.py`; verification stays enabled. Production endpoints require correctly trusted HTTPS and operator-configured `BEARINGS_PUBLIC_URL`/allowed hosts. Run migrations 0054–0056 before serving the new endpoints.

See the [client guide](../../clients/linux/README.md) for commands, protected enrollment files, systemd, outage behavior and replacement procedure. Source implementation: `portal/agent_protocol.py`, `portal/agents.py`, `portal/agent_views.py`; tests: `portal/test_agents.py`, `portal/test_agent_client.py`, `clients/linux/client_test.go`. Build outputs stay under ignored `.local/`; no release binary, signing key, real customer report or enrollment secret belongs in Git.
