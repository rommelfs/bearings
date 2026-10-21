# Agreed next phases

Planning baseline: 2026-10-20. Implementation status is now mixed: phases 1/2 have bounded implementations, phase 3 has lifecycle outreach/draft subscriptions/opt-in SMTP, phase 4 has a bounded read-only snapshot pilot, and phase 5a has historical import/comparison. Live RT/Plum compatibility, production operational acceptance, scalable deltas and phase 5b remain open. Existing NetBox, Vulnerability-Lookup, MOSP/MONARC and FlowIntel capabilities remain described in the user guides and validation record.

Bearings should provide one understandable view of organizational asset problems and their consequences: hardware, installed software/firmware, vulnerabilities, support/EOL, licenses, maintenance, warranty and observed network exposure. Each item must answer: what is affected, where it is, what evidence exists, why it matters, when action is due and who owns the next step.

## Order and deliverables

| Phase | Deliverable | Acceptance boundary |
| --- | --- | --- |
| 1 — Asset issues and lifecycle | Common organization-scoped issue/evidence model and clear asset/problem views. First cases: existing CVE reviews, EOL and expiring support; extend to licenses, maintenance and warranty. | Preserve existing finding/history/case identities; link issues to actual assets/installations or contracts, distinguish vendor/product facts from organization entitlements, record source, observed/valid/due dates, uncertainty and responsible owner. Existing CVSS remains source vulnerability severity. |
| 2 — Optional RT/RTIR | Reviewed issue-to-ticket hand-off and separate read-only workflow feedback, alongside FlowIntel. | Verify the selected RT/RTIR version, supported API, queue/custom-field/ticket-type permissions and TLS. Exact preview/approval, instance-bound correlation, uncertain-write reconciliation, current sharing checks and retained status. A maintenance issue does not automatically become an RTIR incident. |
| 3 — Operational notifications | Extend current reviewed local notification workflow to approved production delivery, subscriptions, reminders and escalation. | Company/CIRCL scopes, verified audiences, templates, bulk filters, per-recipient preview, idempotent approval, delivery/failure/acknowledgment history and policy checks also cover lifecycle/exposure issues. No automatic production transport is enabled by this plan. |
| 4 — CIRCL master and company instances | Both CIRCL-hosted organization workspaces and separately operated company Bearings instances with approved sharing. | Explicit instance/organization identities, least-privilege source credentials, versioned scoped delta API, provenance and current redistribution rules. Company NetBox remains authoritative; no shared databases or indiscriminate central raw-data replication. A bounded complete-snapshot pilot is implemented; scalable delta federation remains open. |
| 5a — Existing Plum Island observations | Reuse the existing national-scale observation corpus, correlate customer ranges/assets and show exposure over time. | Source capabilities/credentials/version verified before connection; bounded network/time queries or supported export, stable source identities, resumable ingestion and comparison coverage. Company views receive only their authorized, time-valid observations. |
| 5b — Controlled scan coordination | Optionally manage Plum Island target/profile scan requests from Bearings when operational parameters are configured. | Reuse CIRCL's stated Luxembourg scanning mandate as policy context; represent allowed scope, profiles, exclusions, budgets, cadence and actor in durable audited requests. Check duplicate targets, current authorization and uncertain outcomes. Target registration is a scheduling operation. |

Phase 5a can begin alongside phase 1 after the shared observation/issue boundaries are established: existing data does not require introducing a new scanning workflow. Phase 5b is a separate increment. SSO is implemented for Bearings, bundled NetBox and the CIRCL human in bundled FlowIntel, with independent roles and emergency access. A private RT/RTIR Apache deployment generator is included; target-instance acceptance and global session lifecycle remain separate. See [SSO operation](operations/sso.md).

## Plum Island: use the existing corpus first

CIRCL reports an existing mandate to scan Luxembourg and a large deployed observation corpus. Treat that as the operational context, not as a reason to rescan all customers or copy the entire corpus into every company workspace. The private service address supplied by the operator is not stored in this public repository or issues.

Bind verified, historically valid customer networks/IPs and requested-hostname context to source observations. Handle overlapping assignments, shared hosting, NAT, address reassignment and ambiguous attribution explicitly. A network observed under the national mandate is not automatically inventory belonging to a registered customer. Keep inventory discrepancy observations for review instead of silently creating authoritative NetBox assets.

For scale, select relevant networks and time intervals on the source, use bounded pages or export batches when the deployed interface supports them, retain source UID/content hash and checkpoints, and use incremental refresh with a bounded overlap for late data. Avoid per-address enumeration of large IPv4/IPv6 ranges and unbounded full-history loads. The reviewed search/export UI is not yet a certified headless service API; a supported export adapter or upstream API extension may be needed.

Use separate observation and ingestion/evaluation timestamps, requested window, source/report identity, protocol, port, requested hostname, service evidence, scan profile/coverage and scan outcome where available. Retain last-known data and freshness/errors on permission, transport, partial-export or indexing failure. Full scans, skipped scans, incomplete scans and unobserved services must remain distinguishable.

### Changes shown to an analyst

- **Newly observed:** a positive service observation absent from the comparable baseline, with the exact evidence and comparison period.
- **Still observed:** the service is present in comparable evidence; gaps do not imply continuous availability.
- **No longer observed:** an expected service is absent from a comparable observation; explain coverage and possible filtering/failure.
- **Confirmed closed:** only when a relevant scan result explicitly supports closure; absence in an InfoIP response is insufficient.
- **Unknown/stale:** insufficient coverage, unknown protocol, authentication/indexing error or missed scans.

An unexpected management port, changed service/banner or a missing expected service can prompt review for misconfiguration, a broken service or possible compromise. It is not by itself proof of malware. Match product/version evidence to Vulnerability-Lookup only when justified, and attach relevant MOSP/MONARC scenarios with a reason rather than inferring business risk from a port number.

### Presentation and response

Provide a compact company/CIRCL queue with linked asset/IP/DNS/location, protocol/port, change, first/last observations, baseline/coverage, priority reason, owner and action due date. Offer a timeline and a before/after evidence comparison, with actions to review applicability/context, contact stakeholders or prepare an RT/RTIR/FlowIntel hand-off. Use synthetic examples for screenshots and tests; do not publish national/customer observations.

## First acceptance examples

1. An Exchange installation has a CVE review and a separate end-of-support issue on the same asset. Each has its own evidence, consequences, owner and deadline; neither replaces the other.
2. A customer's existing Plum Island records show a newly observed management port. Bearings shows the source evidence and uncertainty, maps it only to an authorized customer scope, and prepares a notification/ticket after review.
3. A previously observed service disappears from a partial scan or a rolling window. Bearings shows unknown/not observed and retains prior evidence; it does not claim closure or remediation.
4. CIRCL filters applicable issues across participating companies and prepares separate, reviewed stakeholder messages; companies can prepare their own internal messages.

See [Plum Island contract research](integrations/plum-island.md), [RT/RTIR design](integrations/rt-rtir.md), [canonical backlog](backlog.json) and [current implementation evidence](validation.md).

## Tracking

- [#23: common asset/lifecycle issues](https://github.com/rommelfs/bearings/issues/23)
- [#25: optional RT/RTIR hand-off](https://github.com/rommelfs/bearings/issues/25)
- [#10: notification delivery and escalation](https://github.com/rommelfs/bearings/issues/10)
- [#26: independently operated company-instance federation](https://github.com/rommelfs/bearings/issues/26)
- [#8: existing Plum Island observations](https://github.com/rommelfs/bearings/issues/8), [#24: temporal comparisons](https://github.com/rommelfs/bearings/issues/24), [#27: later scan coordination](https://github.com/rommelfs/bearings/issues/27)

## Delivered first increments

See [asset issues and the repeatable example](user-guide/asset-issues.md), [RT 5.x contract and hand-off](integrations/rt-rtir.md), [notification subscriptions/SMTP](user-guide/notifications.md), [company snapshot federation](integrations/federation.md) and [Plum import/comparison](integrations/plum-island.md). These guides define the implemented boundaries. No active scan coordination, automatic CVE discovery, remote MONARC assessment synchronization or operational delivery acceptance is implied.
