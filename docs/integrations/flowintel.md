# FlowIntel integration feasibility

Reviewed 2026-10-20. **Feasible and useful as an optional case/task workflow service. No connector or running integration is implemented by this assessment.**

## Evidence and scope

Reviewed the public upstream source at main commit [`0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f`](https://github.com/flowintel/flowintel/tree/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f) and compared relevant contracts with release [`4.0.0`](https://github.com/flowintel/flowintel/releases/tag/4.0.0), commit `6a6e56af53232fc6a119f7b8a8a24ab5d5d0b729`. The GitHub latest-release API reported 4.0.0, published 2026-08-31. These are source observations, not results against a running FlowIntel instance. No upstream services were installed, API writes made, credentials requested or operational information transmitted. Existing Bearings runtime and notification transport were unchanged.

Upstream is AGPL version 3, compatible in principle with the project's AGPLv3 basis. Prefer a separate API service. Preserve upstream notices and review exact file/dependency terms before copying code; the generic license text alone does not establish a project's “or later” grant. FlowIntel uses Flask/SQLAlchemy with PostgreSQL and Valkey/Redis and provides container deployment. Embedding its application into Django or sharing application tables would couple unrelated ownership and migrations unnecessarily.

## Division of responsibility

| Component | Authority |
| --- | --- |
| NetBox | Infrastructure identities, IP/DNS, site/rack and source facts |
| Vulnerability-Lookup | Published vulnerability evidence |
| MOSP/MONARC | Referenced risk scenarios and assessment context |
| Bearings | Organization scope, installed software, relevance/applicability, contact review, redistribution, bulk selection/template approval and organization inbox |
| FlowIntel | Analyst case, tasks, assignment, deadlines, notes and workflow history |

FlowIntel complements the action after detection. It does not replace product/version correlation or establish affectedness. Its case/task templates are playbooks; they are not a drop-in replacement for Bearings' audience-specific notification templates and verified contact eligibility.

## Source-confirmed interfaces

General REST API authentication uses `X-API-KEY` associated with a user. Alert ingestion has a separate connector-instance credential contract. These credentials and their visibility scopes must never be interchanged implicitly.

| Interface | Source-observed contract and integration use |
| --- | --- |
| `POST /api/case/create` | JSON including title, description, deadline, `is_private` and `ticket_id`; returns `case_id` with 201. Suitable first hand-off, explicitly private at creation. |
| `GET /api/case/<cid>` | Returns case UUID, status ID, completion and other context; current private-case visibility checked. Candidate for polling only locally linked cases. |
| `POST /api/case/<cid>/create_task` | Task title, description and deadline; checks case organization presence/admin rights; returns `task_id`. |
| `POST /api/task/<tid>/assign_users` | Task assignment; verify deployed role and user mapping during pilot. |
| `POST /api/templating/create_case_from_template/<cid>` | Accepts a title and creates a case from a playbook. The reviewed path does not accept/set `is_private`; see isolation constraint below. |
| `GET /api/alerts/schema`, `POST /api/alerts/ingest` | MISP event payload, wrapped in `Event` or bare. Connector key through `X-API-KEY`, `X-FLOWINTEL-ALERT-KEY` or Bearer. Returns alert ID/UUID, review status and occurrence count. |

The alert review and alert-to-case actions under `/alerting/api/...` are login/session-protected web routes in the reviewed source. Do not assume the ingest connector token also authorizes those actions. Human FlowIntel triage is a possible workflow; a headless client should use documented key-authenticated case/task endpoints unless a supported additional API is confirmed.

The API exposes status lists, but IDs are deployment data: discover/map them, do not hard-code numerical meanings. Some endpoints with GET verbs mutate state, for example task `/complete` toggles completion. Status polling must use an explicit allowlist of actual read routes, never broad endpoint crawling.

Sources: [API registration/auth contract](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/api.py), [case routes](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/case/case_api.py), [task routes](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/case/task_api.py), [template routes](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/templating/templating_api.py), [alert API](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/alerting/alerting_api.py).

## Material integration constraints

**Private cases and organization scope.** Case creation defaults to `is_private=False`. Private visibility checks presence of the user's organization in the case; platform admins are trusted. That differs from Bearings' membership/operator-visibility/redistribution model. Start with a CIRCL-only FlowIntel service identity and explicitly private cases, one customer organization per case. Revoking Bearings visibility must stop subsequent exports and restrict local integration details; previously exported copies need an explicit FlowIntel access/retention process, not an assumption of automatic remote erasure. Do not initially add customer users/organizations in FlowIntel; company interaction stays in Bearings. Before customer access is added, verify the entire case organization list, users, notes, tasks, exports and API visibility across two unrelated organizations.

The reviewed template creator constructs a `Case` without `is_private`, while the model defaults false. Creating a public case from a template and later making it private introduces a visibility window. The first pilot should create a private case directly and populate approved tasks. Using template-based creation with customer context requires a source/version path that can guarantee private creation atomically. “Privileged case”/four-eye review is a separate setting and does not imply private visibility.

Sources: [case visibility](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/case/common_core.py), [case creation](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/case/CaseCore.py), [template creation](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/templating/TemplateCase.py), [model defaults](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/db_class/db.py).

**MISP severity semantics.** Alert ingestion derives severity from MISP `threat_level_id`: 1 → high, 2 → medium, 3 → low, 4 → info; absent/unrecognized values default to medium in the reviewed code. This is not CVSS, cannot represent all Bearings source severities faithfully, and must not silently turn Unknown into Medium. For the first pilot keep CVSS score/version/source severity, applicability and business-risk uncertainty explicit in the private case description. A later alert adapter needs an agreed mapping/schema that preserves original meanings. Do not mark a vulnerable server as an observed attacking source or an IDS indicator merely to fit an example MISP payload.

**Retry and revision semantics.** Alert deduplication is by connector instance and source reference, typically event UUID. Release 4.0.0 has lookup-based deduplication; reviewed main adds a database unique constraint, conflict handling and an alert-to-case race check that are absent from that tag. Main also contains occurrence-count race tests. Source inspection alone does not prove all concurrent counters or exactly-once effects. Choose and test a pinned deployed version; do not assume moving `latest` or release 4.0.0 includes those later changes. Direct case creation exposes no dedicated HTTP idempotency-key contract; `ticket_id` is a correlation field, not a uniqueness guarantee. Lost POST acknowledgments require reconciliation, not blind retries.

**Notifications and status feedback.** The email module sends task notifications to FlowIntel users using SMTP. It does not implement Bearings' verified company contacts, product/severity bulk filters, redistribution or per-contact approval policy. Keep organization outreach in Bearings. The inspected webhook module emits `case_created` with an optional HMAC signature, not a documented general task-completion callback. Start return synchronization with GET polling of linked case/task status. A completed FlowIntel case means workflow completion, not verified remediation; expose the external state separately and require an explicit, reasoned Bearings assessment to resolve a finding.

Sources: [alert normalization/deduplication](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/alerting/alerting_core.py), [main's deduplication migration](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/migrations/versions/c4d8e2f1a9b7_add_unique_dedup_key_to_external_alert.py), [mail module](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/modules/notify_user/email.py), [webhook module](https://github.com/flowintel/flowintel/blob/0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f/app/modules/notify_user/webhook.py).

## Proposed Exchange pilot — not implemented

1. Operator configures an optional, approved HTTPS FlowIntel API/browser endpoint, credential reference and CIRCL organization identity. Keep credentials server-side and bound to the selected instance. Use a service user with the needed case/task role, not an unrestricted admin key by default.
2. Authorized analyst chooses **Create FlowIntel case** on a scoped finding. Show the exact export preview, destination and target organization. Recheck current operator visibility and evidence policy on approval and execution; the conservative first pilot exports only shareable evidence. Include approved asset hostname/IP/location/team, CVE/build and assessment with uncertainty, plus scoped Bearings/NetBox/evidence/MOSP references. No entire inventory/contact database export.
3. Create one explicitly private case for one organization and finding, for example `Exchange · CVE-2026-70571 · <correlation ID>`. Retain the case ID/UUID and stable local correlation in a source-bound mapping. Use an audited outbox with a database uniqueness constraint and serialized attempts. On an uncertain POST outcome, reconcile by correlation/authorized reads before creating anything again.
4. Populate tasks: validate installation/affectedness; review exposure; prepare/approve the Bearings contact notification; agree a patch window; verify remediation evidence; perform follow-up. Deadlines and assignments belong to FlowIntel; no tasks execute scans, patch systems or send messages merely because they exist.
5. Show the FlowIntel link, assignee/deadline/task state and last successful synchronization on the Bearings finding. Preserve last-known external state on outages and display freshness/errors. Status refresh cannot close findings, change NetBox or send mail.

Start with direct private case/task creation. Evaluate MISP-format alert ingestion as a second mode once normalization, owner scope and deployed deduplication behavior are tested. Those are alternative entry points; do not automatically create both an alert and a case for the same finding.

## Lab and acceptance gates

Use an optional development profile/service with a pinned version/digest, separate application database, distinct cookie/port settings and generated secrets. Upstream Compose contains fixed container names/default ports and default administrator credentials; do not merge it unchanged into the existing lab. Bearings and NetBox must keep working when FlowIntel is disabled or unreachable. No SMTP credentials, live webhook destination or external customer data in the pilot; use synthetic Exchange context and a local mail sink only.

A live pilot must demonstrate private creation with no transient public case, two-organization isolation, unauthorized/reader/export-policy denial, policy revocation after preview, no secret leaks, one case across repeated/concurrent/lost-ack requests, safe template behavior, supported semantic mappings, retained state on outages, GET-only return synchronization and no automatic remediation/notification. The first profile must also pass fresh startup and retained-volume restart. None of these live FlowIntel gates have been executed in this assessment.

The proposed pilot is tracked in [issue #22](https://github.com/rommelfs/bearings/issues/22). The feasibility assessment is complete; the connector and live acceptance gates remain planned.
