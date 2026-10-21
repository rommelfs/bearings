# Authorization and operator visibility

Django users and organizations are separate. Login is required for all organization pages and APIs. Unknown and unauthorized organization/object IDs both return 404. Every object route first resolves a visible organization; child objects are queried within it. Templates and APIs use the same evidence filtering. No exports, attachments, caches, or search endpoints exist yet.

| Capability | Reader | Editor | Organization admin | CIRCL analyst | Platform superuser |
| --- | --- | --- | --- | --- | --- |
| Read own org inventory/contacts/shareable findings | yes | yes | yes | only policy-permitted orgs, or explicit membership | all |
| Create inventory/software/claims | no | yes | yes | only with explicit editing membership | yes |
| Create/update/review contacts | no | no | yes | only with explicit org-admin membership | yes |
| Verify/dispute infrastructure authority | no | no | no | policy-permitted organizations | yes |
| Review findings | no | yes | yes | policy-permitted organizations | yes |
| See restricted evidence and derived findings | no | no | no | policy-permitted organizations | yes |
| Change memberships, source bindings, visibility policy | no | no | no | no | yes |

Group name: `CIRCL analysts`. Being staff alone grants no organization access. Platform superusers are trusted administrators with full access; hiding data from them is not a promise this software can enforce. Their reads are audited. `operator_visibility=False` is the per-organization default and denies analyst access; explicit memberships still grant their ordinary organization role. Revocation is evaluated on every request, not cached in a session. There are no self-service membership changes yet.

Only platform administration edits visibility. Policy changes record previous/new values in `AuditEvent`; sensitive cross-organization reads record actor and organization. Django administration separately logs administrative actions. Audit rows are read-only through application admin and have no deletion UI; database administrators remain trusted. Tamper-evident external audit export is planned.

SourceRecord `shareable=False` is the conservative default. Participants see neither these records nor their derived findings/counts/history/evidence endpoints. Only the public Vulnerability-Lookup adapter and explicitly synthetic demo records mark records shareable. A boolean is not a replacement for MISP distribution/sharing-group/marking evaluation: no live MISP ingestion is enabled. Future ingestion must compute redistribution eligibility for both evidence and every derived statement before exposure.

Background jobs carry an organization through the asset/source binding; reminders select only that organization's administrators. Jobs have no user-supplied organization IDs or destinations. Future jobs, notifications, search, exports and cache keys must retain this same scope.

Optional OIDC SSO for Bearings, bundled NetBox and the CIRCL human in bundled FlowIntel is now available with explicit issuer/subject bindings and independent local roles; see [SSO operation](operations/sso.md). The RT/RTIR deployment generator supplies exact subject-to-existing-user mapping at an Apache authentication boundary, with no automatic account creation or queue permission changes; the target RT installation requires acceptance. Local passwords remain available. Production MFA/local fallback policy, global session revocation, account recovery, session/rate-limit review and delegated providers are backlog items. Public token redemption changes reachability only, checks hashed 256-bit random tokens, expiry and one-use state, and uses CSRF on POST. GET never consumes a token.

All current contact messages use the development file sink. The UI labels this explicitly; a redeemed local token exercises the confirmation state machine but is not evidence of real-world email delivery. Enabling production contact reachability needs an authorized transport and delivery validation.

## NetBox connection capabilities

Only platform superusers configure instances, credential references, dedicated ownership, scope and read-only/read-write/disabled state. Organization users and analysts cannot elevate connection capabilities. Shared-instance queries require a tenant and validate every returned tenant. Dedicated whole-instance queries require a matching organization assignment. Read-only blocks portal infrastructure submission and all queued external writes even if the user is an editor/admin; local software entry retains its membership rules. Capability downgrades are checked again in the connector against current database configuration. Permission changes are audited. The operator CLI can query many bindings, but no participant endpoint accepts arbitrary instance URLs, credentials or unscoped query IDs.

## FlowIntel case export

Only current authorized CIRCL reviewers/platform administrators can prepare a hand-off for explicitly operator-visible organizations and shareable evidence. Company membership alone does not grant this export. The creator approves the exact snapshot; the worker checks active access, related organization identities, evidence and instance policy before every POST. Linked status reads repeat current visibility checks and verify the exact private service-organization case. FlowIntel private access is organization-based: the bundled cases belong only to the CIRCL service organization, not customer organizations. Platform administrators in both applications remain trusted. Revocation stops future exports; previously exported copies require a separate remote retention/access process.

## Optional RT reference identity boundary

The bundled RT lab has explicit company/CIRCL human and service accounts, private per-queue permissions and separate scoped tokens. Its OIDC overlay resolves exact immutable subjects to an existing active local account and returns the verified numeric RT ID; numeric username strings cannot become another account ID. Unknown/disabled accounts are denied and no claim creates users or grants queue rights. The loopback recovery entrance uses a separate FastCGI pool/cookie and local passwords; it does not authenticate the SSO entrance. RT and its database have no Internet route and mail stays in local mbox files. Bootstrap preserves ACL/account/credential/disabled state and refuses identity conflicts rather than recreating accounts or restoring removed rights. See [RT lab](operations/rt-lab.md).

## RTIR coordination

Native RTIR Incidents and Investigations use a separate CIRCL-only connection and API bridge. Each asset issue is independently approved. An Incident aggregate is denied if any linked issue/company is no longer visible to the actor; company membership alone never exposes coordination tickets or lists. Remote RTIR retention and user ACLs remain independent from Bearings visibility. Native ticket closure does not assert remediation. See [RTIR operations](operations/rtir-lab.md).
