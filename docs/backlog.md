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
- **Add SBOM, endpoint imports and delegated providers**: Implemented bounded Linux reference: native standard-library Go client, public-key-bound one-use enrollment, RFC 9421 Ed25519 signed HTTPS reports, private durable outbox, source/device serialization, explicit same-asset version bindings and separately dated package/runtime facts. Explicit first-host registration creates a local host or queues a tenant-scoped writable NetBox device/VM; initial hostname/IP declarations are unverified and do not create IPAM assignments. PostgreSQL and actual Go/TLS/native-lab tests cover replay, lost acknowledgment, revocation, source ownership, partial/stale data and batched changes. See docs/integrations/linux-agent.md and docs/validation.md. Windows, SBOM, delegated providers, signed releases, automatic renewal, retention/delta/fleet ingest acceptance and verified network reconciliation remain planned. Scanning remains separate authorization.

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

## Optional company address — 2026-11-18

Added one optional address field during signup and a scoped company-admin address editor. Mailbox confirmation copies the original application address to the private organization; subsequent changes preserve the original submission and invalidate open data-review confirmations. Existing CIRCL visibility applies; no coordinates, map, external geocoding or automatic authority challenge. A future map must distinguish company locations from physical asset locations. Technical ownership-verification options remain under discussion to keep onboarding accessible.

## CIRCL severity map — 2026-11-18

Implemented an independently loaded [company map and optional heat overlay](user-guide/circl-map.md), highest-current-severity markers, exact problem links and accessible table. Local Luxembourg postal/place centroids and explicitly saved manual points send no addresses externally. Current sharing/source/exposure rules and signed address-bound positioning apply. Unlocated and omitted-company coverage is explicit; map points describe firms, not physical assets. A bounded 2,000-point response prioritizes severity/counts and leaves existing problem lists independent. Public geographic assets and permissive/CC/public-domain notices are retained. Global geocoding, broader response-capacity acceptance and physical asset maps remain separate work.

## Isolate National Overview latency — 2026-11-18

After a reported minute-long blank document and an inconclusive diagnostic failure, removed aggregate queries from the National Overview document. Summary, problem ranking, version distribution and history load independently with current policy, explicit missing-data states and retry. PostgreSQL per-statement timeout and section time budget prevent a slow history/ranking query from holding the whole page. The local failing/slow-section browser acceptance and genuine query cancellation/restoration pass; affected-environment phase diagnostics remain necessary to identify its database bottleneck.

## Luxembourg showcase, team mail and federation design — 2026-11-18

Implemented safe one-time local Luxembourg addresses for existing/fresh provenance-owned showcase companies, without overwriting user addresses/points/decisions or resurrecting removed data. Optional independently confirmed shared notification mailboxes are separate contacts and never grant a user/login/role; existing outreach policy remains required. End-to-end periodic mail review is verified and same-pass delivery cutoff fixed. The [company synchronization proposal](decisions/0008-company-synchronization-proposal.md) explains the implemented read-only snapshot pilot and proposed stable-ID/resource/delta/outbound-agent work; these protocol changes are not yet implemented.

## Agenda: AIL, company keywords and Honeytokens — 2026-11-18

Planned in [#47](https://github.com/rommelfs/bearings/issues/47): an [AIL](https://ail-project.org) connector and optional company-specific monitored keywords during registration/later configuration, with a **separate Honeytoken indicator**. These fields and the connector are not implemented yet. Decide supported API/version/authentication, indicator matching and secure storage/display first. Keep search values confidential and company-scoped, preserve source/TLP handling and evidence provenance, and do not interpret a match as proven breach or authority. No real monitoring values or leaked content belong in this public backlog.

## National query planning and single-company demo — 2026-11-18

Delivered bounded PostgreSQL join planning within national panel/map transactions, keeping current authorization and the existing 3-second query timeout. Local paired EXPLAIN measurements identify planning overhead; larger synthetic comparisons retain identical results, with history execution still dominating its large-data timing. Actual affected-machine acceptance requires a new timing run.

Bundled `company-admin` now retains only its existing read/write lab company, including safe narrowing of older managed lab/showcase grants. Standalone showcase creation assigns at most one company. Passwords, SSO, unrelated accounts, CIRCL policy and explicit revocations are preserved; external deployments and unexpected grants are excluded. See [synthetic data](operations/synthetic-data.md).

## Resumable company configuration and manual AIL handoff — 2026-11-18

Implemented [#48](https://github.com/rommelfs/bearings/issues/48), [company configuration](user-guide/company-configuration.md): optional public PGP/S/MIME material replaces mandatory scope entry at registration; legacy declarations remain. CIRCL approval unlocks a four-part, freely navigable guide, with independently accessible private settings, server-side autosave/resumption, conflict protection and reviewed-section progress. Scope updates preserve history/verified claims; registered manual inventories can save local assets/software without upstream jobs. Contact, address and existing inventory editors remain available.

**AIL decision supersedes the earlier connector proposal:** no direct integration is currently needed. Save separate keywords/Honeytokens and an optional different-team mailbox; explicitly download custom-YARA configuration for trusted manual AIL import. Analysts review matches/false positives and choose Bearings or AIL notification workflows. No synchronization, automatic alerts or verified recipient claim is introduced. Public keys are format-checked only; no automatic mail encryption.

## Registration delivery visibility and administrative activation — 2026-11-18

Implemented [#49](https://github.com/rommelfs/bearings/issues/49): explicit local-vs-SMTP registration delivery status, platform-only local outbox inspection and retry controls. Django admin now exposes registrations through controlled review links. Platform superusers can activate private access with a recorded reason before mailbox proof and hand the owner a one-use password setup link; email confirmation/reachability remains unasserted and CIRCL sharing is a separate review. Existing passwords/privileges are preserved; public resend throttling remains. See [registration operations](user-guide/reporting-registration.md#pending-registration-local-mail-and-administrative-override).

## Distinguish platform-admin local login from SSO — 2026-11-18

Implemented [#50](https://github.com/rommelfs/bearings/issues/50): made `platform-admin` the first explicit Bearings entry in starter credentials output, with the local form/Sign in route and retained-password explanation. The SSO-enabled login page now labels local administrator sign-in and explains the lab account's distinct identity store. No account/password/group/binding reset or IdP provisioning is introduced.

## Complete credentials account/URL directory — 2026-11-18

Implemented [#51](https://github.com/rommelfs/bearings/issues/51): service-grouped managed login accounts, current Bearings usernames/active flags and concrete URLs under `python3 scripts/dev.py credentials`. Actual Docker published ports support custom mappings; local/SSO/recovery and unassigned access are explicit. Print retained generated initial passwords per service (including separate Keycloak bootstrap), without tokens or account/password mutations. External mode and disabled/unavailable profiles remain explicit; no external login probing is performed.

## Bearings administration appearance — 2026-11-19

Implemented [#52](https://github.com/rommelfs/bearings/issues/52): Bearings branding/browser titles and matching system font, teal/navy palette, surfaces/sidebar/forms for the administration backend. Add direct workspace/registration/outbox links while preserving native forms, permissions, CSRF, filtered selectors, popups and light/dark controls. Use an explicit portal template search directory so mounted lab code also receives the override. See [platform administration](user-guide/platform-administration.md).

## Registration first/last name and company title — 2026-11-19

Implemented [#53](https://github.com/rommelfs/bearings/issues/53): explicit required first/last names and declared company role/job title. Persist names on the local account and submission; copy the combined name/title into the company contact through both mail-proof and administrative-activation paths. Free-text titles do not grant privileges or verify contact roles. Legacy full names/contacts remain intact without inferred splits or invented titles. See [registration](user-guide/reporting-registration.md).

## Registered company SSO and own-inventory native access — 2026-11-19

Implemented [#54](https://github.com/rommelfs/bearings/issues/54), [company SSO](user-guide/company-sso.md): explicit approved-owner local reauthentication plus signed provider identity linking, unchanged local roles/passwords, and a bundled-lab operator plan/apply for new IdP accounts and dedicated NetBox own-inventory view/add/change permissions. Existing demo grants stay unchanged; nonempty manual inventories require separate migration or `--without-netbox`. Private receipts support owned stage retries without restoring disabled accounts/bindings/policies. Credentials list managed native human accounts. Production provider provisioning, centralized lifecycle/revocation and populated source migration remain separate.

An optional unique, platform-attested MISP organization UUID anchors future company correlation; it never grants personal login/membership, auto-merges companies or invokes a MISP connector. Applicant forms cannot set it.

## Vulnerability-Lookup and MISP ecosystem proposal — 2026-11-19

Planned [#55](https://github.com/rommelfs/bearings/issues/55), [ecosystem integration](integrations/ecosystem-accounts.md): keep company watches and remediation inside Bearings, add source-linked public Vulnerability-Lookup community evidence, and offer native shared SSO only where contributors need it. Start MISP with CIRCL-only read/search and explained, restricted company/asset correlations, including no-CVE research. Feedback/publication is a separate reviewed step. Current upstream OIDC support was source-reviewed for both projects; deployed versions, service capabilities, account mapping and lifecycle remain unvalidated. No key, live MISP access, account provisioning or external write was used for this proposal.

## Restricted MISP cache and next product priorities — 2026-11-19

Implemented a bounded [MISP cache pilot](integrations/misp.md): configurable source (proposed URL misppriv.circl.lu), disabled-by-default hidden-key setup, background complete read searches, UUID/timestamp/digest identity, atomic retained failure handling, source leases/freshness, explicit exact-revision analyst recipients and local current verified IP/domain assignment research. No participant exposure, automatic outreach, upstream mutation or native MISP replication. Real private deployment/key/version acceptance, software/historical matching, large-corpus deltas and reviewed outreach remain open.

The [whole-product review](product/next-priorities.md) prioritizes [minimal useful setup/safe bulk entry #56](https://github.com/rommelfs/bearings/issues/56), [a short evidence-backed company action list and reachability/nonresponse follow-through #57](https://github.com/rommelfs/bearings/issues/57), plus operational/revocation/recovery acceptance. Reuse existing wizard/issues/mail workflows; avoid new mandatory accounts or duplicating tasks. Direct AIL automation stays deferred.


## Minimal company entry, actions, response follow-through and personal MISP access — 2026-11-19

Implemented [#56](https://github.com/rommelfs/bearings/issues/56): [minimal company entry and manual CSV import](user-guide/company-first-steps.md), including stable identities, preview/explicit commit, preserved local edits, atomic/replayed/concurrent behavior and 24-hour private preview retention. Implemented [#57](https://github.com/rommelfs/bearings/issues/57): grouped current-authorized company actions using existing evidence/history, plus [due-review follow-through](user-guide/review-followups.md), recipient-safe previewed repeats, separate transport/delivery/response states and explicitly operator-reported SMTP bounce/recovery. No implicit upstream writes, automatic closure, DPO escalation or live provider webhook.

Implemented [#58](https://github.com/rommelfs/bearings/issues/58): the [MISP cache](integrations/misp.md) now uses isolated personal analyst keys and pinned native user IDs; another analyst or platform account cannot read that cache through a Bearings grant. Shared-key caches are quarantined, not reassigned. Native permissions are checked before each bounded snapshot, with visible permission freshness; firms need no MISP key. Production private-service/provider acceptance and broader replication remain open.


## Customer-native MISP permissions — 2026-11-19

Implemented [optional personal customer MISP connections](user-guide/personal-misp.md). Universal CIRCL rights remain internal investigation rights and cannot stand in for customers. Customers supply their own key against an approved fixed endpoint; setup pins its native user, encrypts the key, and refreshes a separate owner/company cache. No staff-key fallback, manual reader grant, same-company inheritance or platform raw-event bypass. Current membership, endpoint approval and bounded freshness apply. CIRCL investigation and company-safe outreach stay separate; no new MISP account is mandatory for the core product. Real private-service distribution/version validation and large-corpus replication remain open.


## Company membership and consolidation

Implemented OrgAdmin-managed invitations for existing/new users and reviewed platform-only local company consolidation. Existing target roles win on overlap; source/history are archived. Native identities, sources, delivery state and data collisions require separate reconciliation. See [company members guide](user-guide/company-members.md).

Membership administration now uses readable user/company/role labels and separate searchable list columns with a role filter.


## Project communication, FAQ and local static website

Added a documentation index and shared nineteen-question FAQ; reconciled stale overview/policy statements. A local-only static website in English, German, French and Luxembourgish explains immediate company benefits and free registration with synthetic product images. Five real vulnerability examples (including November 2026 NGINX2Root and Java/Java4Shell) have source links and visibly fictional humorous quotes. Public deployment is deferred at the owner’s request. See [website guide](../website/README.md), [source review](product/website-examples.md) and [next acceptance steps](product/next-priorities.md).

Local website recovery: `python3 website/serve.py` builds before serving the absolute output path, avoids working-directory 404s, reports occupied ports and accepts `/en/` as an English alias.

The fictional vulnerability testimonials now have a prominent hero link in every language and the stable `#testimonials` anchor.

Marketing scope: focus on the CIRCL-operated SaaS and free company registration. Removed self-hosting promotion, local-start CTAs and technical local-mail messaging from public copy; retained local-only preview instructions in the operator/developer guide.


## Fast registration entry

Registration no longer silently sends signed-in visitors through dashboard aggregates. Anonymous form display has no showcase/inventory query; existing sessions get a bounded account entry and explicit account-switch form. Numerical Server-Timing and `web-timing --registration` separate public HTTP/HTTPS from SSO request times. See [registration guide](user-guide/reporting-registration.md).

Website follow-up: all four closing headlines explicitly include continued free use of the CIRCL-operated service. `python3 scripts/dev.py website --language de` builds and opens the local preview; `--no-open` supports headless use. The HTTP numeric loopback address avoids localhost HTTPS upgrades in Safari. See [website guide](../website/README.md).

The use-case headline now adds the benefit to Luxembourg as a third line in EN/DE/FR/LB, retaining the existing company and CIRCL lines.

Branding: the website now uses a CIRCL-derived Bearings design with a connecting ring, the original supplied CIRCL operator logo and nine original project logos hosted locally. Source/checksum provenance and ownership notes are in [branding documentation](../website/branding/README.md); integration maturity descriptions remain unchanged.

## Measured 40,000-company scale acceptance

Executed an isolated PostgreSQL test with 40,000 companies, 1.2 million assets/installations, 240,000 findings and 360,000 issues. The company overview is fast, but action/national aggregate timeouts, unbounded global review prefetch (>3 GiB), per-company issue loops (>1,000 queries) and 14-second software research block this scale. Four-client HTTP traffic produced three failures in twelve requests. Eleven of twelve function/scope checks passed; summary availability failed. Benchmark scripts, actual samples, query-plan evidence and independent local reminder delivery are documented in [scale acceptance](performance/scale-test.md). Follow-ups are bounded global pages, scoped-query redesign, current-policy national read models and repeated/longer scale acceptance; these application fixes are not implemented by the benchmark.


## Implemented scale follow-up — 2026-11-19

The earlier baseline failure above is historical. Global pages/audit work are now bounded; company queries retain ownership checks in a planner-friendly form; national projections refresh transactionally in a dedicated worker, disclose pending coverage and apply current permissions. Confidential version research combines prepared/live data consistently. Cache/write races, cleanup/merge/reset and overload handling have regression coverage. The same 40,000 companies and 1.2 million assets were retested repeatedly, including multiple owners and committed updates. Passing four-core measurements and the retained failing two-core workload are documented in [iterative scale results](performance/scale-improvements.md). Operational deployment acceptance remains distinct from this tested local workload.


## Four-language website editorial review — 2026-11-19

Removed automatic outer blockquote punctuation that doubled the Java quotation mark. Reviewed EN/DE/FR/LB landing pages, all 76 translated FAQ pairs and all twenty fictional quote/fact/benefit sets; corrected mixed German address, awkward French/Luxembourgish wording, French spacing and previously English-only labels. The FAQ now consistently states continued free use, the current schedule-management roles and measured scale evidence with its limits. Browser checks cover all eight pages at four widths and no-JavaScript FAQs. See [website maintenance](../website/README.md) and [validation](validation.md).


## Configured Linux binary version probes — 2026-11-20

Configured native ELF probes are now implemented as an additional bounded Linux scope: reviewed local config, non-root execution, fixed argv/RE2 extraction, safe paths/no-new-privileges, descriptor-bound SHA-256, time/output/count limits and explicit canonical version ownership. Signed reports retain path/hash only; no raw output/commands, remote execution, silent identity retarget or inferred remediation. Existing package clients remain compatible. See clients/linux/README.md and migration 0057.


## Linux installer and roll-outs — 2026-11-20

Implemented central reviewed artifact downloads, local systemd/account installer, hidden clipboard and bounded stdin enrollment, machine-readable public identity and authorized operator-side one-use issuance. Keys, queues, protected configuration, service drop-ins and deliberate stops survive upgrades. See [roll-out integration](integrations/linux-rollout.md). A SaaS customer-facing company-scoped issuer API, actual customer/Ansible acceptance, automatic key renewal and signed releases remain planned. No shared universal fleet bootstrap credential.


## Native Ubuntu 24.04 deployment — 2026-11-20

Implemented a separate systemd/Gunicorn/PostgreSQL/Nginx first-install path for `bearings.circl.lu`, with protected state/secret, peer authentication, strict trusted-edge policy, independent workers and no demo/bootstrap/public signup. See [Ubuntu installation](operations/ubuntu24.md). Real target apt/systemd, DNS/certificates, SMTP/SSO/connectors, backup/restore and operational load remain acceptance steps; no remote server deployment is performed by local tests.

LXC deployment recovery: corrected the root-only sandbox preflight to test unprivileged execution with the service capability restrictions. Added a writable-path probe after target logs exposed a second namespace denial; documented explicit per-service compatibility with reduced filesystem isolation, without resetting data or globally disabling container confinement; startup readiness requires a socket/HTTP check. See [Ubuntu operations](operations/ubuntu24.md#lxc-502-with-systemd-226namespace).


## Native NetBox, FlowIntel and Keycloak — 2026-11-20

Implemented a staged extension for the existing Ubuntu server: pinned separate runtimes, service identities/databases, private Redis sockets, ACME bootstrap and verified HTTPS/SSO activation. Retain Bearings data/key and existing source bindings; no demo companies, automatic email linking or claim-based role grants. Explicit LXC compatibility omits inner mount protection while preserving ordinary user/capability restrictions. First install is resumable with retained credentials and refuses reuse after activation. Native company/tenant/API provisioning, actual operator connector permissions, MFA/SMTP/recovery and sustained workload acceptance remain separate. See [native ecosystem operations](operations/native-ecosystem.md).

Native static recovery: corrected NetBox’s ignored `STATIC_ROOT` configuration to supported staticfiles storage options. Actual upstream regression now reproduces the old error and verifies collection outside a read-only source tree. Resume preserves completed migrations and retained keys; no source ownership change.

Native IPv6 recovery: explicit IPv4/IPv6 ACME and TLS listeners for all three services prevent default-vhost certificate mismatches; activation reports sanitized transport failures while retaining CA/hostname/issuer verification. Reuse existing certificates and retry activation.

Native activation readiness: target IPv4/IPv6 probes and a repeated activation passed, followed by local NetBox administrator creation. Bound retries across Nginx worker transitions without relaxing certificate/issuer checks. Human SSO links and company/API rights remain explicit next steps.

Native NetBox SSO link recovery: replace unsupported Django admin logging with atomic binding audit metadata and a local system-log event. Actual command regressions preserve passwords/tenant grants and refuse invalid actors, disabled users, existing/revoked links and identity reassignment. Retry the failed NetBox step without reinstalling or repeating the successful Bearings link.

FlowIntel browser SSO recovery: narrowly allow the configured HTTPS IdP origin in login/begin form-action, preserving CSRF/framing and other policies. Real Chromium/WebKit regressions reproduce the old blocked redirect and complete corrected SSO. Update the deployed native adapter copy and restart FlowIntel without resetting identities or data.

## Native CIRCL pilot and controlled mail readiness — 2026-11-20

Implemented the explicit CIRCL pilot: missing company creation without registration/consent inference, separate tenant-scoped read-only NetBox credentials, a non-admin FlowIntel service bridge, protected receipts, safe retries and source-locked binding. Added bracketed relay normalization, reviewed subject prefix and staged verified SMTP readiness/testing. Actual server import, controlled case, SMTP/inbox acceptance and delivery enablement remain separate operator steps; no production emails or customer exports were sent by local validation. General native constituent lifecycle and key renewal remain planned. See [operations](operations/native-ecosystem.md#first-circl-inventory-and-case-bridge).

## Explicit SMTP transport-encryption exception — 2026-11-20

Implemented the operator-requested self-signed relay acceptance through a dedicated SMTP SSL context and `configure-mail --allow-self-signed`, bound to cped.circl.lu. Keep mandatory STARTTLS, verified defaults, HTTPS/SSO trust, staged delivery and reviewed SMTP policy fingerprints. Actual self-signed local TLS and no-STARTTLS denial are tested. Target probe/inbox acceptance remains operational validation.

## CIRCL company/platform workspaces and duplicate merge — 2026-11-20

Implemented stable company labels and bounded searchable merge/workspace selectors, explicit archived personal-MISP retirement (retain keys/cache without transferring access), preserved native target bindings and mandatory review schedules/consent, busy-lock refusal and atomic rollback. Company/platform header navigation uses existing permissions; it is not impersonation or privilege reduction. Remembered company access is rechecked and archived duplicate names no longer block native pilot retries. See [members and merges](user-guide/company-members.md). Actual target merge and independent native-role acceptance remain operator actions.

## Merge confirmation recovery and production diagnostics — 2026-11-20

Reproduced and fixed an unbound form error-handler crash after stale merge confirmation; membership action errors use the same safe rendering. Refused transactions remain atomic. Ignore append-only audit and bounded background status/scheduling in preview hashes; actual facts, roles, source policies and credentials remain pinned, with active refresh/lock denial. Add sanitized production django.request journal diagnostics with exception types/code positions only. The reported server journal contained startup lines, so actual target state/remaining failures need target verification. See [merge recovery](user-guide/company-members.md#if-a-merge-confirmation-fails).

## Visible organization archive status — 2026-11-20

A successful merge retains both records. Improve the misleading generic admin list with explicit status/destination columns, stable IDs, search and active/archive filters; show readonly status and canonical target link on details and archive suffix in organization labels. Preserve registration/audit/disabled-connection history and existing authorization. This is presentation, with no merge replay or deletion. See [company merge administration](user-guide/company-members.md#active-company-versus-archived-source-in-administration).

## Personal MISP account context — 2026-11-20

Show the authenticated Bearings account and linked-SSO explanation, replace an empty company/key form with actionable membership guidance, and preselect the current account in platform-admin membership links. Company memberships and personal key ownership stay explicit and distinct across accounts; archived companies are excluded from the selector. Validated 72 relevant PostgreSQL tests, including alternate-owner POST isolation and no implicit platform membership.

## Native Linux client publication and LXC target support — 2026-11-20

Implement clean-source native artifact preparation with checksum-pinned Go, immutable release output and protected environment activation, plus explicit installer LXC compatibility retaining the main unit, keys/state, other drop-ins and non-root/capability/resource restrictions. No inventory or privilege creation during publication. First enrollment against a read-only native source selects a previously imported NetBox asset. Actual target systemd/report acceptance remains a rollout step. See [native Linux preparation](operations/native-ecosystem.md#prepare-linux-client-downloads-on-the-native-server).

## Company-scoped automatic Linux registration — 2026-11-20

Company administrators can now authorize a rollout once (1–100,000 reservations, 1–168 hours). The installer accepts its secret via hidden prompt or protected stdin, generates each host's own key and registers without per-host UI steps. Lost-response retries retain identity/quota. Expiry/revocation/current permissions/source binding are checked; observed hosts work with read-only NetBox without writes or hostname takeover. The central downloads UI, company fleet UI, installer and Ansible reference describe the same flow. See [rollout contract](integrations/linux-rollout.md).

Follow-up **Validate sustained Linux fleet ingest and credential renewal** separates proven bounded admission/replay/concurrency from 10,000-host sustained package-report capacity. Device credentials remain 90-day, with explicit revocation/replacement; automatic renewal and independent release signing remain planned. Explicit managed NetBox reconciliation is now implemented; see the managed NetBox section below. Existing read benchmarks are not agent ingestion evidence.

## Automatic standard package inventory — 2026-11-20

Default dpkg/RPM package-to-inventory assignment is implemented, including already-processed fresh report backfill, exact native versions, deterministic Package URLs, parallel install-only slots and automatic subsequent updates. No per-package binding clicks are needed; manual/CSV software is kept separate, explicit release is respected and custom binaries still need reviewed mapping. UI/software pages are searchable/bounded. See [Linux contract](integrations/linux-agent.md).

**Add distro-aware security advisory and binary-to-source package matching** remains the next layer: package identity is now automated, but official-repository provenance, source-package matching, native version comparisons and distro CVE feeds are not fabricated from upstream product names. Standard package PURLs are excluded from generic automatic upstream-name watch enrollment. Existing explicit watches remain.


## Automatic vendor CVE discovery and public entry point — 2026-11-20

Supported distribution packages are evaluated automatically using shared bounded Canonical/Debian/Red Hat OVAL caches, exact Debian source metadata and native EVR comparisons. Scoped CVE findings preserve manual review, immutable evidence and explicit partial/unknown/failure coverage. See [the implementation contract](integrations/distro-cves.md). Repository/runtime/signature predicates and sustained fleet throughput remain follow-ups.

The existing web service serves the multilingual marketing website at `/`, with same-origin Login/Registration; private overview is `/infrastructure/`. All four translations link CIRCL’s statutory NIS2/CSIRT/CVD role and describe scanning and voluntary sharing. No production deployment, scans or notifications are performed by local validation.


## Native management terminal completion — 2026-11-20

Batch management now uses systemd pipes even from SSH terminals. Interactive account/password/shell commands retain PTYs; non-interactive NetBox and FlowIntel work uses pipes. Protected environment parsing, service identity, wait/exit status and security properties are preserved. See the [native recovery guide](operations/ubuntu24.md#completed-management-command-with-a-stuck-terminal).


## CIRCL corporate identity — 2026-11-20

Public marketing in all four languages, workspace/login and Django admin now follow CIRCL’s Raleway/blue/red/white identity. Fonts, mark and provenance/license notices are hosted locally; semantic risk colours, accessibility and existing authorization are retained. See [branding reference](../website/branding/README.md#circl-corporate-theme--20-november-2026).


## Domain-based invitations and clear workspace navigation — 2026-11-20

Company admins can issue a bounded reusable code for one exact email domain; every member must still confirm a personal mail challenge. Reader/editor only, quotas, expiry, creator/role/domain rechecks, CSRF and rate limits preserve access boundaries. Source merges revoke codes; no keys or native roles transfer. Invitation notices now report actual SMTP submission or local/error state. A visible company/national selector names the selected company and highlights the matching view, retaining current permissions. See [membership guide](user-guide/company-members.md#shared-code-for-an-exact-email-domain). Migration 0061 is required.


## Concrete package mappings and actionable review errors — 2026-11-20

Automatic discovery shows exact package/release/feed associations, candidate-definition counts and scoped CVE review links. Software recognition, matching readiness and current reviews are separate statuses; identities without indexed advisories remain explicitly monitored. Server-wide partial coverage is separate, default manual-watch prompts are removed for distro packages, and batched queries preserve authorization. Canonical singleton guards are interpreted correctly and versioned cache recompilation queues reevaluation. Registration review identifies actual company/role, visible memberships and explicit correction links instead of a generic 403 for missing applicant admin membership; access controls remain intact. No role/sharing restoration or new schema/client rollout is performed automatically.


## Self-explanatory software and CVE actions — 2026-11-20

Company and machine software tables distinguish installed software, cached automatic matching status and scoped recorded CVE reviews. No per-package setup links are shown for distribution packages. Exact-product links open automatic coverage; manual retrieval is a collapsed optional known-CVE action in machine details with no example identifier. Readiness and retained reviews remain distinct; no role, assessment or automatic job policy changes. See [asset triage](user-guide/asset-triage.md#installed-software-versus-cve-reviews).


## Package-check receipts and map restoration — 2026-11-20

Migration 0062 adds bounded current package-check receipts, including native fixed-version proof, report/feed provenance, outcome counts and recent examples. Discovery/inventory separate technical results from retained human reviews; stale/failed/pending/unsupported checks do not imply safety. Existing devices are queued without client reinstallation. Nonmatching/absent rules do not imply explicit manufacturer non-applicability. See [distro integration](integrations/distro-cves.md#package-check-results-versus-human-reviews).

Company maps repair canvas/vector geometry after container resize, font loading and hidden-page restoration while preserving center/zoom. Singular/plural company summaries are corrected. Local real-renderer browser validation covers resizing, restoration and heatmap; target Safari idle acceptance remains to be confirmed.


## Company inventory latency and readable CVE summary — 2026-11-20

Replace the unbounded company CVE/history/form dump with a scoped workflow summary and dedicated review link. Bound contact/scope pages, avoid full snapshot payloads and whole-inventory count joins, and reuse request-local authorization. Synthetic single-asset and larger PostgreSQL evidence is recorded in [company inventory performance](performance/company-inventory.md); production network latency is not inferred. Local-only agent hosts are identified without changing connector capabilities.


## Managed native NetBox registration and optional public Linux client — 2026-11-20

Migration 0063 adds explicit managed fleet policy and declared virtualization. The native helper preserves tenant, source, token and host UUID; enables narrow Device/VM capabilities; registers the existing host as VM+lxc; and verifies the upstream object and complete GET-only import. New managed codes support Incus/Proxmox/VMware and other explicit tags, while old codes remain observed-only. Real isolated HTTPS, signed registration, independent NetBox ORM and both application UIs validate the connection. Production activation remains operator acceptance. See [managed NetBox operations](operations/managed-netbox.md).

The public website and FAQ describe the optional Linux client in all four languages, including recurring package versions, central rollout, signed reports and conditional NetBox integration. Browser checks cover desktop/mobile without external assets or tenant data. No production deployment is inferred from local validation.


## Customer-owned RW NetBox and richer Linux inventory export — 2026-11-20

Migration 0064 adds explicit source-owned export, bounded worker scheduling and receipts/errors. Native interfaces and IP assignments use a tenant-owned unique VRF and deterministic ownership; OS/software/runtime/provenance become a host JSON field. Existing unrelated inventory is never adopted implicitly, deleted or moved. A per-customer operator command configures existing isolated RW credentials, inventory-only mode, revocation and explicit first marking of a confirmed client-bound host. Native CIRCL provisioning optionally extends its retained policy without replacing keys/tenants. Updated signed reports refresh network declarations; old clients keep their original network age. See [operations](operations/managed-netbox.md#reported-inventory-export-migration-0064).

A later CIRCL-to-customer NetBox move is documented as a separate planned export/import, mapping, verification and source-cutover workflow. Its executor and preview UI are not implemented; changing an existing endpoint is not a migration.


## First production UI and isolated security audit — 2026-11-21

Read-only production inspection covers 24 public layouts; local synthetic authenticated checks verify visible disabled/export/host/client states, grouped navigation/actions, correct client orientation and mobile command-block overflow correction. Optional functionality is disclosed without deleting backend capabilities or changing authorization. Frozen root/native NetBox/FlowIntel locks are updated for known advisories and audited by CI; the shared OIDC adapter preserves existing digest identities/tombstones while using session-bound nonce checks. Target deployment, independent release signatures/renewal, full infrastructure/image review, registration/language refinements, complete accessibility and sustained capacity remain separate work. See [audit findings, corrections and evidence](audits/2026-11-21-ui-security.md).

Linux network follow-up: permit AF_NETLINK for local interface enumeration; report capture failures in the journal. Upgrade only the exact previous reviewed unit, preserving device state and custom drop-ins. Target systemd/NetBox acceptance remains separate.

## UI and security audit follow-up — 2026-11-21

The bundled NetBox now uses a digest-pinned base plus nine hash-locked Python
security overrides and installed dependency checks; CI audits the actual built
image. All 135 installed packages have zero remaining advisory records in the local
check. Registration groups required account/contact/commitments and optional details,
keeping entered values/errors visible. Default same-origin CSP blocks inline scripts
and preserves approved integration frames; local desktop/mobile and authenticated
map/asset/integration browser checks pass. See the [audit](audits/2026-11-21-ui-security.md).
Deployment acceptance, independent client release signing/credential renewal,
production egress, MFA, language continuity and full accessibility/sustained fleet
load acceptance remain open; source publication does not complete those controls.

Actual rebuilt Bearings/FlowIntel environments are also audited (32/76 packages, zero advisory records). Bundled gateways re-resolve fixed backend names after container replacement; verified HTTPS logins recover after a further FlowIntel recreation. Its unused administrative Gunicorn control socket is disabled.


## Group assigned IP records under their machine — 2026-11-21

Migration 0065 retains address identities and assessments while grouping same-source
explicit NetBox interface assignments under device/VM cards in company inventory.
No hostname/IP guessing or record merge occurs. Address previews and host details
are bounded; independent/missing records remain reviewable. Direct organization
email-domain-code navigation now matches the existing company-admin/platform-admin
permissions. See [NetBox operations](operations/managed-netbox.md).


## Remove stale overview assumptions — 2026-11-21

The infrastructure overview separates distribution-package monitoring from legacy
manufacturer/product watches, and stops requesting per-package mappings or showing
an invalid combined current-products ratio. Assigned IP records no longer inflate
machine/no-software counts. Truly empty workspaces remain available in a compact
setup section, with inventory-bearing organizations ordered first. No workspace is
merged, archived or deleted automatically and memberships stay unchanged.


## Consistent inventory directory and repeated consolidation — 2026-11-21

Inventory directory counts assigned IPs with their host and shows asset-less
workspaces compactly while preserving contacts and search. Platform-only review
links preselect the source without mutation. Reviewed consolidation can append
registrations to a canonical target with earlier archives, retaining target native
bindings and old archive destinations. Source archive chains remain blocked; every
incoming/resulting membership role is shown, and policy changes invalidate previews.
See [members and consolidation](user-guide/company-members.md).


## Linux downloads rollout controls — 2026-11-21

Implemented organization selection, one-time rollout key display after creation and
revocation on the download page using the existing fleet authorization and service.
Existing secrets remain hash-only; no implicit replacement or credential changes.
See [Linux client](integrations/linux-agent.md).

Rollout display follow-up: creation now jumps directly to the result below the
form; errors receive an explicit failure notice. Secrets remain one-time only.

Linux rollout instructions now include the installer download in each installation
block, plus LXC, service status and secret-file automation instructions.

Rollout virtualization now depends on host kind and the authoritative NetBox
instance configuration, with matching server validation and no changes to existing keys.


## Python 3.8 Linux installer — 2026-11-21

Implemented compatible subprocess credential drops with unchanged user/file
boundaries, real Python 3.8 checks and disposable HTTPS installation tests.
Republish the immutable client bundle and redownload the installer on the target.
See [Linux agent](integrations/linux-agent.md).

Noexec follow-up: installer candidate execution uses the destination filesystem,
leaving /run mount policies intact. Regression smoke now verifies real noexec
denial and tests both Python runtimes and enrollment modes.

Client discoverability: Inventory → Linux clients, a top-of-page installer action,
and localized public website links now lead directly to downloads.


## Consistent overview IP addresses — 2026-11-21

Attention cards now include explicit assigned IPs even without primary fields,
with same-source/company isolation, primary deduplication, last-known labels and
a link to full network records. A single bounded batch query preserves query budgets.
See [infrastructure overview](user-guide/infrastructure-overview.md).


## Explain CVE review attention — 2026-11-21

Implemented inclusion reasons, product/version and saved assessment/matching facts,
concrete next actions, explicit reconciliation and prioritized four-record previews.
Optional risk scenarios are collapsed hypotheses; existing assessments and scope
remain authoritative. See [overview guide](user-guide/infrastructure-overview.md).


## Reliable package-version CVE decisions — 2026-11-21

Implemented independent per-component version proof, source/binary comparison
evidence, explicit affected/fixed/unresolved package verdicts, freshness guards
and upgrade reevaluation. Presence-only Ubuntu triage entries are no longer
version matches. Native comparisons and immutable human decisions are retained.
See [case and implementation audit](audits/2026-11-21-package-cve-correctness.md).

### Separate actionable package verdicts from historical open review workflows

Implemented scoped SQL classification before queue aggregation/pagination: current affected versions/manual assessments, vendor uncertainty, pending current evaluations, fixed/not-matched/explicit human not-affected, and all retained workflows. Native Canonical CVE-2026-124757/needrestart 3.6-7ubuntu4.6 regression verifies the equal fixed boundary leaves the actionable list without closing human reviews. Proof operands/reasons/currentness are shown directly, analyst conflicts preserved, same-source NetBox assigned IP/DNS batched and searchable. Freshness and privacy/pagination/query-budget regressions; docs/audits/2026-11-21-package-cve-correctness.md. No schema/client/dependency changes.
