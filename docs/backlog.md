# Implementation backlog

Canonical issue/milestone definitions are in [backlog.json](backlog.json). GitHub publication is authorized for the public `rommelfs/bearings` repository. `uv run python scripts/sync_backlog.py` publishes missing milestones and issues idempotently by exact title, checks the expected repository identity, and updates nothing already present. The backlog is published as [milestones](https://github.com/rommelfs/bearings/milestones) and [issues](https://github.com/rommelfs/bearings/issues?q=is%3Aissue). The first slice ([#1](https://github.com/rommelfs/bearings/issues/1)) is complete; current issue state is tracked on GitHub. A second publisher run created zero duplicate issues.

## Implementation update — 2026-10-20

The first lifecycle/RT/notification/Plum increments and bounded company snapshot federation are implemented. Their operational/scalability follow-ups remain open.

- **Implement Plum Island historical observation adapter**: Implemented bounded existing-data reader: approved HTTPS InfoIP GET contract with JWT reference, offline InfoIP/full JSON import, time-valid verified company claims, provenance, exact/ambiguous asset mapping, current source/company visibility, atomic idempotent partitions and retained failures. No blind range enumeration or target writes. Source reviewed at 06972ba8; deployed Swagger /v1/swagger could not be reached from the cloud, so live API auth/version remains unvalidated. Production-scale export jobs/checkpoints and deployed compatibility remain open. See docs/integrations/plum-island.md and docs/validation.md.
- **Generalize asset issues to lifecycle, support and entitlement risks**: Implemented AssetIssue for CVEs, EOL, support, licenses, maintenance, warranty and exposure with asset/optional installation, software/firmware type, source/uncertainty/observation/validity, entitlement vs product fact scope, owner, priority, event/action deadlines, immutable evidence/history and justified pinned MOSP links. Original CVE IDs/history/FlowIntel relationships and restrictions preserved. Filtered scoped UI/API and explicit synthetic exercise included. Automated vendor lifecycle feeds and MONARC assessment synchronization remain open. See docs/user-guide/asset-issues.md.
- **Compare Plum Island exposure observations over time with explicit coverage**: Implemented source/customer/IP/asset window comparisons preserving protocol/port/requested hostname. Shows newly/still observed, changed evidence, missing observations, unknown/filtered and explicit scan closure only. Earlier out-of-window first_seen withheld; co-observed tags never prove malware. Current scope/source revocation hides raw/derived evidence/counts. Mapped observations can create one durable reviewed exposure issue; no automatic affectedness, priority, outreach or scan. Synthetic real-browser example and contract tests; live national corpus and coverage certification remain open.
- **Deliver controlled notification and escalation workflow**: Implemented CVE and lifecycle/exposure filtered bulk previews, constrained templates, contact eligibility, creator approval, transport-bound idempotency, current sharing checks, company inbox/acknowledgment, changed-content subscriptions that prepare drafts only, and explicit non-development TLS SMTP alongside default local files. Relay acceptance is not confirmed delivery; uncertain attempts are retained without blind retry. SMTP validated with mocked transport only, no operational messages. Production bounce monitoring, reminders, escalation/routing and operational acceptance remain open; docs/user-guide/notifications.md.
- **Add optional RT and RTIR issue hand-off with scoped status feedback**: Implemented optional RT 5.x REST2 adapter based on public RT 5.0.10 source. Exact scoped issue/asset/risk preview, creator approval, queue ACL/scrip attestation, committed pre-I/O claims, single POST, source-bound ID/queue/subject/merge verification, lost-ack read-only reconciliation, separate status/owner/due feedback and retained failures. Company/CIRCL queues and token isolation; concurrent PostgreSQL workers tested. No implicit incident classification or remediation from closure. Live RTIR queue/type/custom-field/version acceptance remains open; no bundled RT service. See docs/integrations/rt-rtir.md.
- **Connect CIRCL master to independently operated company Bearings instances**: Implemented bounded read-only snapshot pilot: expiring company-admin grants with hashed bearer secrets/client binding, HTTPS-only export, current sharing/role checks, operator-managed connection credentials, complete bounded schema/identity validation, source-locked atomic imports, retained missing/failure history and isolated company-reported UI. No local authoritative inventory mutation or outreach from remote records. 500 issues/500 assets and 1.5MB server cap. Delta/partition/checkpoint scalability, live two-instance pilot, remote retention/revocation and production service operation remain open. See docs/integrations/federation.md.


## M1: Foundation and inventory

Complete inventory ownership and onboarding

- **Deliver first organization-to-installation slice**: Local first increment: login, memberships, operator policy, contacts/scope review, manual asset outbox, software and evidence UI/API. Validate tests and docs; track delivered status in docs/validation.md.
- **Validate central NetBox against an isolated live tenant**: Provision filterable bearings_id custom fields, least-privilege credentials and tenant/site/type/role defaults. Verify devices and VMs, lost-POST recovery, field permissions and tested release. No production inventory.
- **Completed [#3](https://github.com/rommelfs/bearings/issues/3): NetBox source refresh and reconciliation**: Four-type atomic import, periodic/manual refresh, freshness/source links, retained missing-object review, local assessment preservation and PostgreSQL concurrency validation.
- **Harden operator-assisted onboarding and product normalization**: Account/membership lifecycle, contact validation and history, explicit product identity normalization, network/service inventory topology, database tenant integrity, source binding migration controls.

## M2: Correlation

Add evidence-backed intelligence without unsafe inference

- **Validate live Vulnerability-Lookup and canonical aliases**: Live CVE retrieval and immutable evidence revisions are implemented. Canonical aliases, broader schema adapters, deployed-version capture and freshness remain in #5.
- **Completed [#18](https://github.com/rommelfs/bearings/issues/18): Connect NetBox assets, Vulnerability-Lookup evidence and MOSP risk scenarios**: Public CC0 catalog refresh, justified links, pinned evidence, withdrawal history and joined tenant-scoped views are implemented. See [contract and workflow](integrations/mosp.md). Scoring and MONARC assessment synchronization remain future work.
- **Implement explicit product/version applicability**: Use supported structured source capabilities; preserve unknown versions, vendor fixes, backports and configuration requirements. Keep severity, EPSS, catalog membership, exploitation sightings and applicability distinct.
- **Implement MISP ingestion with redistribution policy**: Inspect selected release API, paginate/retry safely, preserve event/object roles and markings. Enforce distribution, sharing groups and operator policy for raw and derived data. Test default-deny behavior and common origins.
- **Implement Plum Island historical observation adapter**: Verify authentication/permissions/schema and InfoIP time/404/empty semantics. Preserve tcp/udp, report-level tags, hostname context and uncertainty. Investigate network/domain export; never enumerate large ranges blindly or launch scans.
- **Generalize observations, relationships and explained priorities**: Keep categories and assessment dimensions distinct. Match historical/shared claims, preserve rule versions, observation/ingestion/evaluation times, evidence provenance and independent origins.

## M3: Operational workflow

Prepare controlled operational use

- **Deliver controlled notification and escalation workflow**: Keep development sink; require operational authorization for production transport. Add delivery failure state, reminder escalation, deduplication, handling policy and audited preparation history.
- **Complete organization remediation and CIRCL triage**: Review filters, acknowledgment/corrections, assignment, urgency summaries and freshness coverage. Test all counts/exports/notifications against visibility restrictions.
- **Security and recovery gate before deployment**: SSO/MFA, rate limits, source approval/egress enforcement, DB row-level integrity, least privilege, audit export, retention and PostgreSQL recovery drill. Approve WSGI/TLS configuration and production scheduler.
- **Complete security contact and release governance**: AGPL-3.0-or-later and public source publication are approved. Establish a verified responsible reporting destination/key and review dependency/integration notices. Operational deployment and data publication require separate authorization.

## Later: Imports and delegation

Extend without changing authoritative-source rules

- **Completed [#14](https://github.com/rommelfs/bearings/issues/14): organization-owned NetBox read-only sources**: Operator-approved connections import directly into the common organization-scoped model, with one authoritative source, isolated credentials and no central duplication or bidirectional synchronization.
- **Add SBOM, endpoint imports and delegated providers**: Reuse software identity boundaries and source provenance; scanner/agent/SBOM imports with isolation and explicit grants. Scanning remains separate authorization.

## Multi-instance NetBox increment

Named instances, isolated credential references, explicit read-only/read-write/disabled capability, shared tenant and dedicated ownership scopes, paginated GET-only queries and read health are implemented. The following import increment now completes bounded four-type inventory projection. The new milestone-1 item is defined in backlog.json; live mixed-capability validation remains in #2 and projection/reconciliation is implemented in #3/#14.

## Complete local environment

Completed in [#17](https://github.com/rommelfs/bearings/issues/17): a bundled real NetBox + Bearings lab and external-instance starter are implemented, with generated credentials, verified TLS, read-only/read-write examples, automatic job processing and retained data across mode changes. See development-stack.md. General four-type inventory imports are now implemented in #3/#14; live compatibility beyond the pinned bundled NetBox version remains in #2.

The starter now checks Docker CLI, Compose and engine availability before changing lab state, with actionable macOS installation/PATH guidance instead of a traceback.

## NetBox import and reconciliation

Implemented #3/#14: atomic paginated imports across multiple instances, source-local identities, periodic/manual scheduling, separate import health/freshness, source links, retained missing-object review and local assessment preservation. Broader topology, upstream snapshot consistency, monitored production scheduling and additional deployed-version compatibility are not implied.

## Exchange example and analyst review cues

Completed [#19](https://github.com/rommelfs/bearings/issues/19): an opt-in [Exchange CVE-2026-70571 exercise](user-guide/exchange-example.md) with real public evidence, explicit manual affectedness, a guarded bundled NetBox inventory write and a justified MOSP scenario. The start page now surfaces active visible findings, source severity, criticality/build/team and scoped direct links. Inventory-only CVE discovery, generalized applicability, business risk assessment and outgoing notifications remain separate work. The broader remediation/triage issue remains open.

## Locate affected assets and prioritize review

Completed [#20](https://github.com/rommelfs/bearings/issues/20): the [asset triage increment](user-guide/asset-triage.md) adds source IP/DNS/location/rack context, linked asset/evidence/actions, distinct severity styling, search/global severity filters and source-first ordering. A guarded opt-in Exchange fixture validates actual NetBox placement and the regular GET-only projection; no permissions are raised or external servers provisioned. Broader topology, source freshness workflows, risk scoring and notification delivery remain separate backlog items.

## Notification preparation and richer bundled inventory

Implemented [#21](https://github.com/rommelfs/bearings/issues/21), the first part of [#10](https://github.com/rommelfs/bearings/issues/10): CIRCL/company filters and sorting, constrained templates, reviewed per-contact previews, policy revalidation, local file approval, duplicate-attempt prevention, company inbox and acknowledgment. [Notification guide](user-guide/notifications.md) distinguishes existing-review cues from future automated feed/product matching and local file output from production delivery. Both bundled tenants now have IP/DNS/platform facts; physical starter devices also have room/rack/U/serial/tag. #10 remains open for bounce monitoring, reminders/escalation, routing and operational transport/recovery acceptance; draft subscriptions and opt-in SMTP are now implemented; #6 retains product/version correlation and #11 assignment/remediation workflows.

The notification guide now explicitly documents screenshot reproduction after updates: rebuild the Docker application, force an immediate GET-only import, seed optional reviews/contacts, choose the matching organization/severity and manually approve inbox messages. Git source updates do not distribute the screenshot database; native and Docker databases are separate.

The Exchange setup entry point now uses the complete `scripts/dev.py example-exchange` helper. The lower-level Django seed creates the case/evidence but cannot populate its network/location fixture; it now explicitly prints the `example-exchange --inventory-only` completion command before attempting MOSP. Existing-case completion performs placement and immediate import without another public lookup.

## Optional FlowIntel pilot (2026-10-20)

Implemented [#22](https://github.com/rommelfs/bearings/issues/22): [private case hand-off](user-guide/flowintel.md) with a compact pinned upstream source build, separate database/keys/TLS, optional retained lab profile, CIRCL-only approval, four follow-up tasks and read-only status feedback. Approved asset IP/DNS/rack/CVE/assessment/risk context stays source-bound. Durable claims, current visibility/content revalidation and bounded read-only reconciliation stop uncertain POST retries; case completion never resolves a finding or sends mail. Both synthetic RO/RW NetBox organizations were exercised against real FlowIntel, including unrelated-organization denial and browser navigation. [Source analysis](integrations/flowintel.md) and [validation](validation.md) record boundaries and exact outcomes.

Remaining work: MISP alert ingestion and severity semantics, assignment-name mapping, external-version compatibility, richer playbooks, remote retention/revocation process and production scheduling/egress/SSO/recovery. These are not enabled by the local pilot; notification/product matching and broader remediation remain in #6/#10/#11.

The #22 follow-up fixes startup on image-layer filesystems that reject directory renames with EXDEV. The adapter preserves the image tree before linking retained runtime data; regression checks cover EXDEV, repeat startup, existing backups and unexpected links. The guide documents recovery by updating the bind-mounted adapter without rebuilding or deleting volumes.

## Agreed lifecycle, response and Plum Island phases (2026-10-20)

The [roadmap](roadmap.md) records the agreed order: common asset/lifecycle issues and UI; optional RT/RTIR hand-off; production notification/subscription/escalation work (#10); independent company-instance federation; existing Plum Island observations/comparison; optional mandate-aware scan coordination. New definitions are in backlog.json; existing #8 remains the historical reader, not a scan-submission connector.

CIRCL reports a Luxembourg scanning mandate and a large existing observation corpus. The first Plum Island increment therefore reuses scoped historical data and can begin alongside the common issue model. Preserve protocol/port/hostname, source/report identity, comparable coverage and time-valid customer ownership; new or disappearing observations remain qualified review cues. Confirmed closure requires suitable scan evidence. Public source review at 06972ba8 establishes API/UI/agent and scheduling distinctions; a later read-only Swagger attempt timed out. No internal address, national/customer observations or credentials are published. The implementation update above records delivered pilots and remaining acceptance work.

The optional historical exposure seed now reports whether it skipped the target or retained visible/hidden snapshots, with exact windows and inventory-completion instructions. Existing source/scope decisions are preserved; see [the exercise guide](user-guide/asset-issues.md).

## Optional application SSO

**Add optional OIDC SSO with explicit identities and independent application roles**: Implemented: optional Bearings, bundled NetBox and bundled CIRCL FlowIntel OIDC with Keycloak 26.8.1, separate clients/secrets, POST/CSRF initiation, code + S256 PKCE, signed RS256 issuer/audience/azp/expiry/nonce validation, fixed verified HTTPS backchannels and explicit issuer+subject local account bindings. No login-driven user creation, email linking, role mapping or token persistence. The one-command combined starter adds FlowIntel to retained realms through an isolated one-off provisioner, without resetting existing client policies, users, passwords, disabled bindings or application roles. FlowIntel generation revocation, absolute sessions, profile-off fallback and retained restarts verified. The RT 5.x Apache/OIDC generator produces private, repeatable client/config/subject-map outputs with no remote mutation or automatic users; an existing RT authentication boundary and target-instance queue/overlay acceptance are required. Native FlowIntel Keycloak mode remains off. Full tests and real lab/Apache boundary evidence: docs/validation.md. Remaining: complete deployed RT/RTIR acceptance, independent FlowIntel version/deployment matrix, global/backchannel logout, IdP account lifecycle synchronization, enforced MFA/fallback policy and production operational acceptance. See docs/operations/sso.md and docs/operations/rt-sso.md.
