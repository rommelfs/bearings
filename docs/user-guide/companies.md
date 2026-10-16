# Company workflow

A platform administrator creates your organization, maps its inventory source, and grants membership. Your account can belong to several organizations with different roles; the home page shows only your permitted organizations.

1. Review the visible CIRCL analyst access policy at the top of the workspace. Only the platform operator can change it.
2. An organization administrator records emergency contacts, scope/language/availability, and escalation order. Review role/details, confirm declared emergency arrangements, and verify channel reachability separately. Prepared email messages are local development files, not real delivery. Changing an email invalidates previous reachability; changing details makes substantive review due.
3. Declare domains, public/private prefixes, IPs or ranges. Use network context for private addresses. CIRCL operators review authority and record their method. A declaration is not verified authority, and overlapping claims can be valid or disputed.
4. Editors can submit a manual asset only when the configured inventory instance permits writes. Read-only infrastructure must be maintained in NetBox; software installations remain platform-owned. Pending means the inventory authority has not confirmed it; failed means a retry/reconciliation is needed. Development source IDs are synthetic. Ask the operator to process jobs or resolve connector configuration.
5. Select an existing organization-local software product or enter a new name and optional CPE/PURL. Record exact version/build/edition when known; leave version blank when unknown. OS installations use the same relationship. Identifiers are manual normalization assertions, not automatic affectedness.
6. Select a CVE to retrieve for review. A successful record lookup does not determine applicability, exploitation or compromise. Read evidence/explanation and record an assessment and reason; workflow and applicability are separate. Repeating a lookup preserves review history.

Readers cannot mutate data. Editors cannot change contacts or memberships. Organization administrators manage contacts but cannot self-verify infrastructure authority or modify operator policy. Missing/stale inventory and absent findings are coverage gaps, not a safe result.
