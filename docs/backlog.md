# Implementation backlog

Canonical issue/milestone definitions are in [backlog.json](backlog.json). GitHub publication is authorized for the public `rommelfs/bearings` repository. `uv run python scripts/sync_backlog.py` publishes missing milestones and issues idempotently by exact title, checks the expected repository identity, and updates nothing already present. The backlog is published as [milestones](https://github.com/rommelfs/bearings/milestones) and [issues](https://github.com/rommelfs/bearings/issues?q=is%3Aissue). The first slice ([#1](https://github.com/rommelfs/bearings/issues/1)) is complete; current issue state is tracked on GitHub. A second publisher run created zero duplicate issues.

## Implementation update — 2026-10-20

The first lifecycle/RT/notification/Plum increments and bounded company snapshot federation are implemented. Their operational/scalability follow-ups remain open.

- **Implement Plum Island historical observation adapter**: Implemented bounded existing-data reader: approved HTTPS InfoIP GET contract with JWT reference, offline InfoIP/full JSON import, time-valid verified company claims, provenance, exact/ambiguous asset mapping, current source/company visibility, atomic idempotent partitions and retained failures. No blind range enumeration or target writes. Source reviewed at 06972ba8; deployed Swagger /v1/swagger could not be reached from the cloud, so live API auth/version remains unvalidated. Production-scale export jobs/checkpoints and deployed compatibility remain open. See docs/integrations/plum-island.md and docs/validation.md.
- **Generalize asset issues to lifecycle, support and entitlement risks**: Implemented AssetIssue for CVEs, EOL, support, licenses, maintenance, warranty and exposure with asset/optional installation, software/firmware type, source/uncertainty/observation/validity, entitlement vs product fact scope, owner, priority, event/action deadlines, immutable evidence/history and justified pinned MOSP links. Original CVE IDs/history/FlowIntel relationships and restrictions preserved. Filtered scoped UI/API and explicit synthetic exercise included. Automated vendor lifecycle feeds and MONARC assessment synchronization remain open. See docs/user-guide/asset-issues.md.
- **Compare Plum Island exposure observations over time with explicit coverage**: Implemented source/customer/IP/asset window comparisons preserving protocol/port/requested hostname. Shows newly/still observed, changed evidence, missing observations, unknown/filtered and explicit scan closure only. Earlier out-of-window first_seen withheld; co-observed tags never prove malware. Current scope/source revocation hides raw/derived evidence/counts. Mapped observations can create one durable reviewed exposure issue; no automatic affectedness, priority, outreach or scan. Synthetic real-browser example and contract tests; live national corpus and coverage certification remain open.
- **Deliver controlled notification and escalation workflow**: Implemented CVE and lifecycle/exposure filtered bulk previews, constrained templates, contact eligibility, creator approval, transport-bound idempotency, current sharing checks, company inbox/acknowledgment, changed-content subscriptions that prepare drafts only, and explicit non-development TLS SMTP alongside default local files. Relay acceptance is not confirmed delivery; uncertain attempts are retained without blind retry. SMTP validated with mocked transport only, no operational messages. Production bounce monitoring, reminders, escalation/routing and operational acceptance remain open; docs/user-guide/notifications.md.
- **Add optional RT and RTIR issue hand-off with scoped status feedback**: Implemented optional RT 5.x REST2 adapter based on public RT 5.0.10 source. Exact scoped issue/asset/risk preview, creator approval, queue ACL/scrip attestation, committed pre-I/O claims, single POST, source-bound ID/queue/subject/merge verification, lost-ack read-only reconciliation, separate status/owner/due feedback and retained failures. Company/CIRCL queues and token isolation; concurrent PostgreSQL workers tested. No implicit incident classification or remediation from closure. A bundled RT 5 reference and optional native RTIR 5.0.10 coordination are now implemented; independently deployed RTIR acceptance remains open. See docs/integrations/rt-rtir.md.
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
- **Completed [#18](https://github.com/rommelfs/bearings/issues/18): Connect NetBox assets, Vulnerability-Lookup evidence and MOSP risk scenarios**: Public CC0 catalog refresh, justified links, pinned evidence, withdrawal history and joined tenant-scoped views are implemented. See [contract and workflow](integrations/mosp.md). Company-local scoring/treatment/acceptance is now delivered in [continuous review](user-guide/continuous-review.md); native MONARC assessment synchronization remains future work.
- **Implement explicit product/version applicability**: Scheduled explicit vendor/product watches and conservative exact/release-SemVer affected-release checks are implemented with separate automated input/evidence history and changed-review cues. Unknown versions, broader ecosystems, backports and configuration remain review work; severity, EPSS, exploitation and analyst decisions stay separate. [Workflow and bounds](user-guide/continuous-review.md).
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

Implemented [#21](https://github.com/rommelfs/bearings/issues/21), the first part of [#10](https://github.com/rommelfs/bearings/issues/10): CIRCL/company filters and sorting, constrained templates, reviewed per-contact previews, policy revalidation, local file approval, duplicate-attempt prevention, company inbox and acknowledgment. [Notification guide](user-guide/notifications.md) distinguishes recorded-review cues from the now-implemented explicit product-watch discovery and local file output from production delivery. Both bundled tenants now have IP/DNS/platform facts; physical starter devices also have room/rack/U/serial/tag. #10 remains open for bounce monitoring and operational transport/recovery acceptance; draft subscriptions, opt-in SMTP, structured role/DPO routing and timed approval-required reminder/escalation drafts are implemented. #6 retains broader version/backport/configuration support; #11 retains broader remediation workflows.

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

## Optional real RT 5 reference lab

Implemented in the RT/SSO follow-up: `up --sso --flowintel --rt` starts a real pinned Debian RT 5.0.7 security-patched reference with isolated PostgreSQL, verified HTTPS, automatic retained Keycloak client/subject binding, separate company/CIRCL queues and API keys, local recovery login and local-only mbox mail. Native/API/browser tests cover shared SSO, permitted/foreign tickets, disabled/unapproved identities, retained ACL revocation, stable credentials/tickets, local-password mode and GET-only lost-ack recovery. The adapter accepts native typed EffectiveId references and still rejects merged/foreign ticket identities. The external generator now resolves exact active account names to numeric IDs and upgrades only its known unmodified legacy overlay. Native RTIR coordination is now implemented; customer-specific queues/overlays/mail behavior remain acceptance work. See [RT lab](operations/rt-lab.md) and [validation](validation.md).

## Native RTIR coordination

Implemented: optional `--rtir`, real RTIR 5.0.10 queues/lifecycles, CIRCL-only coordinating Incidents and separately approved native linked Investigations for multiple assets/companies, source/lifecycle/parent verification, aggregate visibility withdrawal, independent bridge key, retained installation and synthetic example. Company accounts retain ordinary RT queues and cannot read RTIR evidence. Workflow closure remains separate from technical remediation. Independent customer RTIR acceptance, external graph/type import and version upgrades remain open. See [RTIR lab](operations/rtir-lab.md).

## Extensive exploration data and cleanup

Implemented: a default bundled 10-company/300-asset synthetic showcase with software, CVE/lifecycle/risk evidence, 180 historical exposure snapshots, offline case/task previews and rendered outreach drafts; scoped exploration page and visible synthetic banner. Explicit per-object provenance, reviewed removal plans, stale-plan/referral/live-conversion blockers, transactional PostgreSQL locking, audit preservation and a retained removal marker protect real data and stop automatic reseeding. A data readiness command separately reports old unregistered fixtures. Backend lab data/credentials and production deployment acceptance remain separate. See [operations](operations/synthetic-data.md).

## FlowIntel SSO discoverability and retained updates

Implemented: a primary visible SSO login card with separate expandable local recovery; `up` reloads the bind-mounted FlowIntel adapter and reports SSO mode. The actual pinned upstream login template is tested for independent CSRF forms, and the shared Keycloak browser flow is exercised against the full lab. Only explicitly linked CIRCL identities enter the CIRCL workspace. See [SSO troubleshooting](operations/sso.md#flowintel-still-shows-a-password-login).

## Workspace structure and visual hierarchy

Implemented after a running-lab UX review: grouped active navigation, mobile menu, direct scoped inventory entry, inventory-first company workspaces, Locate/Assess/Respond orientation, machine-first scan cards, consistent semantic risk colors and clearer outreach filters. Browser checks cover platform/company/CIRCL roles and 320–1440 px screens; new aggregate/visibility tests preserve access boundaries. Task-based user acceptance, consolidated response worklists and complete accessibility certification remain follow-ups. See the [review and screenshots](reviews/workspace-ux.md).

## Connected application canvas

Implemented: scoped application directory, sandboxed NetBox/FlowIntel/RT/RTIR views with Bearings navigation, top-level SSO/reconnect, explicit native framing policy and separate-tab fallback. The SSO lab supplies a trusted HTTPS Bearings entry without resetting retained clients/identities. Real Chromium verifies one IdP password prompt and native framing/denial; API credentials and application permissions remain separate. External acceptance, cross-site cookie limitations, deep links/draft continuity, global logout and complete native accessibility acceptance remain follow-ups. See [setup and screenshots](user-guide/applications.md).

## CIRCL multi-constituent campaigns

Implemented: [One reviewed CIRCL campaign across all matching constituents](user-guide/notifications.md#circl--organizations): all/selected audiences, complete readiness and explicit exclusions, grouped private previews, single bulk approval and bounded background dispatch. Company isolation, consent rechecks and uncertain-attempt retention remain enforced.

## Named MONARC scenario selection

Implemented: integrated local search, human-readable threat/asset/weakness preview, automatic identifiers and justified confirmation of the exact reviewed catalog revision. Upstream changes require re-review; outages preserve existing mappings. Bounded rule-based scenario recommendations are now delivered; automatic impact scoring remains separate. See the [scenario selection guide](user-guide/risk-scenarios.md).

## Guided entry and interchangeable examples

Implemented first CVE-case guide with Start here, searchable product/CVE/machine examples, five decisions and context-preserving risk selection. The PHP exercise uses two genuine public CVEs on one assumed installation. Known NetBox inventory references open exact objects in the canvas with scoped return links. Full onboarding, other issue domains and comprehensive follow-up remain separate work. See [guided cases](user-guide/guided-cases.md).

## HTTPS-only bundled SSO callback

Implemented: local Bearings sign-in returns to HTTPS on the workspace port, avoiding browser upgrades of HTTP localhost:8000 callbacks. A narrow retained-client migration preserves identities, credentials and native authorization; custom client policies are not overwritten. See [Safari callback troubleshooting](operations/sso.md#safari-cannot-open-the-callback-on-https-port-8000).

## Core inventory → discovery → contact → company-risk workflow

Implemented the three requested core gaps; [user guide](user-guide/continuous-review.md) defines configuration and bounds. Product watches now discover new/changed public CVEs with conservative structured version evidence and separate immutable automated explanations. Structured contact functions, direct accountable asset contacts, optional DPO recipients and timed reminder/management-escalation drafts are delivered. Organization-local MOSP-linked assessments now record business impacts, controls, treatment, residual judgments, deadlines and admin-only expiring acceptance; the scoped risk register shows each issue's latest assessment.

Remaining boundaries: broader ecosystem version/backport/configuration support and aliases; large-product incremental scalability; confirmed delivery/bounce ingestion/automatic escalation delivery; production scheduler/acceptance; native MONARC scoring/import/export. Existing analyst decisions, raw/derived source visibility and file-only development delivery remain preserved. The canonical definitions above are updated in backlog.json; external issue publication depends on available GitHub API access.

Company-risk tracking: [#36](https://github.com/rommelfs/bearings/issues/36).

## Automatic product setup and infrastructure entry

Implemented recognized-name/CPE/package mapping candidates and enabled-by-default watch enrollment during software creation, bundled initialization and the scheduled vulnerability worker. Exact known-name aliases cover Log4j, Exchange and FortiOS; conflicting identities wait for selection and existing pauses/sources/custom mappings remain intact. Unknown products use an authenticated scoped, bounded public manufacturer/product picker with explicit search and retained inputs on outages.

The login landing page now summarizes permitted companies and prioritized assets with action/review/coverage states, monitoring freshness/setup gaps, concrete next actions, overdue deadlines and current contact links. Automatic page refresh runs every 60 seconds and defers during text entry. The prior technical review queue remains at `/reviews/`; existing scope/redistribution protections also govern overview counts and priorities. See [guide](user-guide/infrastructure-overview.md).

Tracking: [#38](https://github.com/rommelfs/bearings/issues/38).

## Direct problem navigation and automatic scenario drafts

Delivered exact asset/attention filters and direct linked problem titles, dates, next actions and risk drafts on infrastructure cards. Overdue action counters no longer rely on expiry-date/name-search approximations; restricted evidence is excluded before selecting links and counts, including legacy CVE deep links. Local rule-based scenarios now describe conditional consequences and treatment by source weakness/text or lifecycle/exposure/entitlement kind. Compatible public MONARC catalog suggestions have explained asset/topic ranking, prefilled editable justification and explicit reviewed-revision/evidence confirmation. Withdrawn mappings remain respected; no automatic risk score, acceptance, process-deficiency claim or source-policy override is introduced. [Guide](user-guide/automatic-scenarios.md).

Tracking: [#39](https://github.com/rommelfs/bearings/issues/39).

Severity-first ordering now also applies consistently to organization findings, asset detail and joined intelligence views before pagination: Critical/High precede Medium/Low/None, and Unknown is last. Current evidence visibility is preserved.


## Infrastructure overview query performance

Delivered page-wide grouped counters, eager inventory source loading and bounded problem windows for the twelve displayed priority assets. Operator membership checks are batched while individual sensitive-read audit events remain intact. A query-budget regression verifies that adding companies/assets does not add per-row queries; current visibility and local source freshness remain evaluated on every request. No shared authorization/response cache or schema change is introduced.


## Verify overview performance through the running web process

Delivered unconditional web/worker restart plus health wait on explicit local starter `up`, including cached images without SSO. Overview responses now report local overview processing milliseconds through `Server-Timing`; the bundled smoke requires this marker so a successful new-process unit benchmark cannot stand in for verification of the retained server. Actual HTTP and HTTPS Chromium checks distinguish server processing, TTFB and full load. Local improvement is verified; the reported user-machine six-second delay still requires measurements from that machine.


## Isolate persistent SSO navigation latency

Added per-response SSO session/Django timings and a bundled-only `web-timing` command using real Keycloak login, current running HTTP/HTTPS services and existing synthetic identities. Output is sanitized numeric timing/status information, with no credentials or page contents. Both overview and Applications are measured, including a request after the proxy DNS cache expires. Existing revocation/expiry checks remain current, with no IdP request on normal navigation. Local SSO navigation is verified; the user-reported delay remains open pending measurements from that machine.


## Avoid overview query compilation stalls

User-provided measurements now locate the observed 9.5–9.7-second delay inside overview processing, with approximately 9 ms session checks and fast HTTP/HTTPS/Application responses. A local session-scoped PostgreSQL stress reproduction spent 11.5 seconds in the existing complex ORM queries under aggressive JIT thresholds. The overview now disables JIT only in its local transaction, restores the previous setting and measures individual view phases plus total/maximum database execute duration. Current source/organization/evidence policy is unchanged, and no authorization/response cache is introduced. The stress case falls from 11.7 to 0.68 seconds locally; the user's actual improvement still requires a post-update measurement.


## Narrow priority queries and avoid redundant legacy lookups

The post-JIT user measurements still spend 8.4–9.1 seconds in priorities, with one SQL execute taking 6.7–7.3 seconds. Reworked the query shape: rank narrow IDs, hydrate only bounded scoped previews, skip legacy lookup for full cards and use indexed correlated existence checks for common-issue and exposure visibility. Added ranking/issue/legacy preview timing ranges. Private common issues do not suppress public legacy CVE links; revoked exposure grants hide those issues while ordinary issues remain visible. A separate 90-asset/27,000-finding fixture shows an improvement for full cards; mixed legacy benchmarks overlap and do not establish the user-machine result.


## Reduce remaining counter and preview work

Delivered one inventory-hierarchy aggregate, request-local reuse of lazy scoped evidence querysets, correlated latest-risk visibility and bounded field loading for watches/scenario previews. No cross-request data or authorization cache. Paired local comparison reduces company-admin GET database executes from 40 to 33 and CIRCL from 52 to 45, preserving current policy, complete scenario output and counts. Absolute timing gains vary; the company-admin gain is modest locally. New regressions cover twelve complete CVE scenario previews without per-preview queries and dense installations with missing/retired/foreign-source assets.


## CIRCL national coordination overview and private inventory research

Delivered an operator-only national entry with permission-scoped outstanding/affected/accepted-risk reviews, exact cross-company evidence links, version prevalence, coverage and contact gaps, and genuine first automated evidence/resolution activity. Add transient local POST product/version investigation without a CVE, exact/custom-version and bounded release SemVer rules, unknown/non-comparable groups, pagination and assigned contact links. Criteria are not saved in advisories/audits/sessions or sent upstream; CSRF, private/no-store, same-origin referrer policy and CIRCL query-log redaction protect the flow. Every count/result remains under current source/company policy. Registered inventory is not a complete national census; missing remediation records are not verified unpatched systems. Historical version adoption and full TLP advisory/recipient lifecycle remain separate. [Guide](user-guide/circl-overview.md).

## Registration and national performance update — 2026-11-17

Implemented [#41](https://github.com/rommelfs/bearings/issues/41): [email-confirmed private registration and periodic data review](user-guide/reporting-registration.md), with subsequent CIRCL sharing approval, optional local assets/software, configurable owner reminders, durable local-first email delivery and explicit unverified authority. Existing-company invitations, automated ownership proof and operational SMTP/bounce acceptance remain open.

National activity now starts from discovery matches and uses indexed earliest-revision lookups and indexed closure events. The 27,000-finding / 270,000-revision synthetic PostgreSQL run improved from 2.03–2.22 s to 0.51–0.73 s; user-environment acceptance remains separate. Use `python3 scripts/dev.py web-timing --national` after applying migrations/restarting with `up --no-build`.

## Organization registration commitments — 2026-11-18

Implemented [#42](https://github.com/rommelfs/bearings/issues/42): **Register your organization** with required emergency telephone and explicit authorization, periodic email-check and immediate-update commitments, timestamped/versioned without retrospective legacy agreement. Applicants and company admins cannot choose review periods or disable mandatory service checks. Platform admins and CIRCL for currently shared companies configure periods; service-layer and revoked-sharing checks enforce this independently of form visibility. See [registration](user-guide/reporting-registration.md). [Low-friction technical/resource verification](user-guide/infrastructure-verification.md) is a documented proposal; no DNS/HTTP/RDAP challenge is yet automated.
