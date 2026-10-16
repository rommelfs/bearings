# CIRCL and platform operator workflow

Platform administrators are Django superusers. Use `/admin/` to create organizations, organization-local memberships, and exactly one source binding per organization. Source mode development is synthetic; central requires a tenant ID and operator environment configuration. Provision NetBox custom fields and validate the chosen release before connecting it. Do not grant superuser/staff to participant accounts.

Analysts belong to the exact `CIRCL analysts` group. The CIRCL dashboard includes only explicitly visible organizations unless the analyst also holds ordinary organization memberships. A platform superuser has full administrative access. The per-organization visibility switch is operator-owned, default deny, and audited when changed. Operator reads are audited. Explain this deployed policy to participants.

Review overdue contacts, source failure/success timestamps and open findings in the dashboard. An organization-admin membership is needed for an analyst to edit/review contacts; analyst status alone permits scope authority review and finding assessment in allowed organizations. Record a meaningful verification method for each infrastructure claim and use disputed/expired when appropriate. NetBox access alone is not authority proof.

Run `process_jobs` to process due inventory submissions, inspect failed assets/source status, resolve upstream configuration and then use `--retry-now`. Never report an inventory write as successful based only on local persistence. Review the synchronization runbook for ambiguous POST results.

Finding review records workflow state, analyst applicability and a reason while preserving the original automated assessment/evidence. An unassessed technology-review relationship is not compromise. Restricted evidence is operator-only; MISP sharing evaluation is not yet implemented and live ingestion remains disabled.

`remind_contacts` prepares reminders to each organization's administrators, deduplicated for the due review. All notifications remain in the local development sink. Production delivery, scans and deployment require explicit operational authorization. See incident and recovery runbooks before introducing production data.
