# Vulnerability notifications: CIRCL and company workflow

This increment implements filtered bulk previews, a constrained message template engine, explicit approval, a **local file outbox**, a company inbox and acknowledgment. It does not send production email. Open **Notifications** in the header or **Prepare notifications** on Security review.

## Run the synthetic exercise

```sh
git pull
python3 scripts/dev.py up
python3 scripts/dev.py manage seed_notification_example --bundled
```

Startup fills empty facts on the four original bundled devices/VMs: documentation IPv4/IPv6, `.example.invalid` DNS and Debian platform; physical servers additionally have synthetic room/rack/U10/serial/asset tag. Existing primary IPs, platform, placement and operator edits are retained. Both tenants have populated inventory; Bearings still uses a genuinely read-only token for the RO tenant. No API write capabilities are raised. Importing these facts uses the regular GET-only inventory importer.

The explicit notification exercise adds **synthetic minimal Log4j CVE-2021-44228 records (Critical)** for registered lab installations and separate synthetic notification contacts. Its source is `fixture://notification-example/SYNTHETIC`; it is not a live Vulnerability-Lookup response. Contacts explicitly simulate email reachability and a current role review; no real verification or emergency availability is asserted. Repeating the command preserves existing contact inclusion, evidence redistribution policy and analyst decisions. No notification is created until you request a preview. The command refuses external inventory when `--bundled` is supplied.

For the existing live-evidence Exchange exercise, keep its separately documented [setup](exchange-example.md). Its CVE-2026-70571 has **High** severity, so use the High filter and product Exchange. The bundled notification exercise provides an eligible synthetic contact for that same RW organization. The Exchange placement command remains `python3 scripts/dev.py example-exchange --inventory-only` for an already confirmed case.

Native fallback: `DJANGO_DEBUG=1 uv run python manage.py seed_notification_example` prepares only the separate Example Labs development workspace; it does not provision NetBox.

## CIRCL → organizations

1. Sign in as `circl-analyst`. Choose CIRCL audience, source severity **Critical** and product **Log4j**. Refresh matches. Both permitted lab organizations appear; each shows whether notification contacts are ready. Sort by severity/criticality, organization or product; optionally narrow by organization, CVE or analyst assessment.
2. Inspect the scoped asset and evidence links. “Unassessed” is a request to investigate, not a claim of affectedness. A technical severity is not a business risk score.
3. Edit the subject/body template if needed, then **Create bulk preview**. This stores an immutable rendered preview, with one message per eligible contact and all matching reviews for that contact's organization. There is no cross-company recipient list or shared message body.
4. Read the exact recipient and message. Uncheck recipients to exclude them. **Approve selected messages to local outbox** records the actor/time, rechecks evidence/assessment/contact/access, prevents unchanged repeat attempts, and writes files. Results are per recipient.
5. The company's Bearings inbox now shows its filed message. Local file creation is not remote email delivery or a read receipt.

CIRCL outreach requires explicit organization operator visibility, even for a platform-created CIRCL campaign. Evidence marked non-shareable is excluded from recipients, counts, previews, historical inbox messages and approval; permission to investigate restricted evidence does not grant redistribution permission. The batch preview belongs to its creator; the ten most recent currently visible batches are linked from Notifications. A reader cannot create internal campaigns or approve another user's batch.

## Company → internal contacts

1. Sign in as `company-admin`, choose Company audience and the company workspace. Select the same product/CVE/severity filters.
2. Review the findings, create a preview, select the internal contacts and approve to the local outbox. Only that company's installations and contacts can enter the message.
3. Open **Company inbox**, read the message and **Acknowledge receipt**. Editors/admins can acknowledge; readers can read permitted messages. The first actor/time is preserved on repeat requests. Acknowledgment does not change the finding's assessment or mark remediation complete. Follow the scoped review link to assess and remediate separately.

Eligibility requires a contact's explicit **notification inclusion**, verified email reachability, a substantive role review with a future next-review date, and no failed-delivery flag. Configure/review contacts in the organization workspace. Emergency availability is independent. If any matching organization lacks eligible contacts, the complete preview fails with a blocker; narrow the organization filter or fix its contacts. Organizations are never silently dropped. Service/team-specific subscriptions and escalation routing are future work; inclusion currently covers the organization's selected reviews.

## Template engine and state

Supported variables, each in double braces: `organization`, `contact_name`, `contact_role`, `language`, `finding_count`, `findings`, `audience`, `action`. Example: `{{ finding_count }} reviews for {{ organization }}`. `findings` includes CVE, source severity, installed edition/version/build, asset, IP/DNS, room/rack/U, team, assessment, workflow, explanation and scoped evidence/NetBox links. Bearings links are relative application paths until an operator-controlled public origin is added. Language is metadata, not automatic translation.

Only flat text variables are allowed: no template tags, filesystem loaders, includes, filters, attribute traversal, model objects or request context. Messages are plain text; web previews escape content. Subject header injection and overlong rendered subjects are rejected.

A preview is bounded to 500 reviews and 100 contacts; the match view shows the first 100 in the selected global order. A changed source payload, rendered asset/software/assessment or recipient invalidates approval. Closed reviews, retired assets and explicit “not affected” assessments are excluded. Missing/stale inventory is last-known information, not proof of present exposure. Contact readiness and current policy are checked again immediately before file I/O.

Each selected message claims a unique receipt before file I/O. Unchanged fingerprints are suppressed across batches for the same audience/contact/content. A crash between claim and confirmation leaves `filing`; a caught file/policy failure becomes `uncertain`. Neither is automatically retried, because a partial file may exist. An operator must investigate the retained receipt/file and audit trail. This is duplicate-attempt prevention, not a distributed exactly-once delivery guarantee. Changed legitimate content can generate a new message; grouping additional reviews can also change its fingerprint. Drafts and excluded recipients remain retained. Production retention/erasure governance is not implemented.

Files use Django's explicit file backend and configured `EMAIL_FILE_PATH` (`.local/mail`), including in Docker's retained local-data volume. Changing `EMAIL_BACKEND` cannot enable SMTP for this workflow. No transport retries, delivery success, bounce handling, reminders or timed escalation are claimed.

## Next phase

The current cue is derived from **already recorded CVE reviews on registered installations**, such as the Exchange live lookup or explicit fixture. Inventory import alone does not discover CVEs or generate applicability. Continuous Vulnerability-Lookup ingestion, canonical product/version correlation, saved notification subscriptions and event-driven CIRCL/internal alerts remain separate work. A product-only match must create a potential/unknown review with evidence, never automatically assert affectedness. Production transport additionally needs reviewed operational authorization, verified destinations, monitored retry/bounce/escalation policy and an approved public application origin. Issues #5/#6/#10/#11 retain these parts.

### Target event flow for the next increment (planned)

1. A scheduled Vulnerability-Lookup importer records a new/changed CVE revision. Match canonical product identifiers (vendor/product, CPE or package identity) against registered installations, then evaluate only supported structured version rules. Unknown builds, backports or configuration requirements retain potential/unknown applicability.
2. Create/update a deduplicated finding with source revision, match reason and uncertainty. CIRCL sees a new actionable cue such as “High · Exchange · 2 permitted organizations · 3 installations · notification review required.” The organization's own review queue receives the same scoped finding. Operator-only evidence stays out of redistribution.
3. Apply saved audience subscriptions (organization, product, severity and assessment), then offer the bulk template preview. Confirmed affectedness may select a different message from a potential-match investigation request. The existing approval/outbox/inbox/acknowledgment flow handles the reviewed result.
4. Track which finding revision/recipient/audience was handled so unchanged refreshes do not raise repeated alerts. Meaningful evidence changes can reopen review. Outages retain last-known evidence and expose freshness instead of silently clearing findings. Production delivery, bounce recovery and timed escalation require their own transport/recovery increment.

These are acceptance goals for #5/#6/#10/#11, not currently running background discovery or automatic mail delivery.

## Screenshots

Only synthetic data is shown.

![CIRCL filtered bulk notification preparation](../images/notifications.png)

![Company notification inbox](../images/notification-inbox.png)
