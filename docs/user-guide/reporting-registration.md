# Register your organization and keep infrastructure data current

From **Sign in → Register your organization** (`/register/`), provide your organization, responsible person's name, emergency telephone number, unique username/email and at least one IP range, static IP or domain. Include the international telephone prefix (`+`); formatting spaces/brackets are normalized. No telephone call or automatic availability verification takes place.

CIDR prefixes, explicit start-end ranges, IPv4/IPv6 and DNS names are supported, up to 100 declarations. Internal addresses can have a network-context label. Software inventory is optional: add assets and exact installed versions once signed in to improve vulnerability matching.

## Required participation statements

Every new applicant must explicitly confirm all four statements. None is selected in advance:

- CIRCL may review the application and access the organization's infrastructure information after approval.
- The person is authorized to share the organization's contact and infrastructure information; IP/domain authority remains subject to verification.
- They accept periodic data reviews and email reactivity checks and will respond.
- They will keep the information current and report changes to contacts, responsibilities and infrastructure immediately.

The authorization declaration, periodic-check consent and update commitment are recorded with individual timestamps and text version **2026-11-18**. CIRCL sees the emergency telephone and these records in Registrations. The timestamps describe applicant statements at submission, not independent verification. Earlier applications retain blank fields and are identified as legacy; the migration invents no phone numbers or retrospective agreement. The public form cannot choose a review period or turn off service emails, including through extra manipulated POST fields.

## Email confirmation opens private access

1. Submit the registration. No password or company access exists yet.
2. Open the email link, choose your password and deliberately confirm the request. Opening a link alone has no effect. The one-use code expires after 24 hours; resends replace it and have a 15-minute cooldown.
3. Sign in with the local portal username/password. Your new private organization area is immediately available for contacts/declarations and optional assets/software. This does not provision SSO or join an existing company with the same name.
4. CIRCL opens **Registrations**, reviews the application and approves/rejects CIRCL sharing after mailbox verification. Approval makes the organization visible to CIRCL. Rejection preserves private owner access. CIRCL cannot inspect live pending inventory; trusted platform administrators retain administrative access. Application snapshots themselves are separately auditable.

Mailbox confirmation does not prove infrastructure authority. Approval does not verify claims, contact roles, emergency availability or patch status. [Practical technical-verification options](infrastructure-verification.md) are recommendations for a later increment; no automated DNS/RDAP/HTTP challenge is introduced here.

Self-service inventory uses **Company-reported inventory**: local assets without NetBox provisioning/write jobs. Existing authoritative NetBox organizations retain their source. Correcting a declaration expires its old record and creates a new unverified claim; withdrawing preserves history.

## Administrator-managed data reviews

**Periodic data review and email reminders** is linked from company pages and the infrastructure overview. A new organization starts with a 90-day review interval, repeat requests every seven overdue days, and the initial data review due now. These are defaults; administrators configure each organization's schedule on that page:

- Only **platform administrators** and **CIRCL analysts for currently shared organizations** can change periods or initialize a schedule for an existing company. Ordinary membership, company-admin status or a previously granted CIRCL visibility is insufficient. Company administrators can review/correct/confirm data, not configure the schedule.
- Review interval: 1–365 days; overdue repeat interval: 1–90 days.
- For registrations accepting the new periodic-check commitment, email checks are mandatory. No opt-out field appears for either applicant or administrator; the service layer enforces enabled mail even if a submitted value attempts to disable it. Legacy optional-mail settings are preserved without pretending that older applicants agreed to new terms.

Check contacts, emergency telephone, IP/domain declarations, assets and versions, then confirm the current data. Confirmation records actor/time, summary counts and a digest, and advances the next due date. A changed emergency number or other data/schedule invalidates an open confirmation form. Changing periods alone does not postpone unreviewed data. Manual-source freshness follows owner review rather than an imaginary connector import.

Due email asks for an active portal response. Sent-message time and owner-confirmation time are visible; opening mail alone does not confirm anything. This is a data-review/reactivity request, not proof of mail delivery, phone availability, network control or remediation. The workflow does not track email opens or automatically escalate unanswered checks.

Mail goes to the mailbox-confirmed registered administrator and opted-in reachable response contacts, deduplicated by address; DPO-only contacts are excluded automatically. Expired contact role review does not silently stop generic data-review requests. Messages contain a portal link, not inventory/vulnerability details. Current policy and recipients are rechecked at delivery; completed reviews suppress pending requests. Failed sends have at most three attempts with backoff. Ambiguous SMTP failure can duplicate mail; bounce processing is not implemented.

## Operator settings

The bundled worker runs checks automatically. Other deployments must regularly schedule `python manage.py remind_inventory --limit 10`. GET requests do not send mail. Delivery state is durable and database-locked, with recipient/due-date/day deduplication.

The default backend writes service mail to `.local/mail` in the web/worker runtime. Set the operator-owned `BEARINGS_PUBLIC_URL` HTTPS origin, or use the canvas origin, for email links; DEBUG permits HTTP localhost only. Links never use client-supplied Host headers.

Real service mail requires `BEARINGS_SERVICE_MAIL_TRANSPORT=smtp` plus `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS=1` or `SMTP_TLS=1`, and `DJANGO_DEFAULT_FROM_EMAIL`. The starter reads private `.env` through Compose; bare Django needs process environment variables. Keep credentials out of Git. This switch is separate from `BEARINGS_NOTIFICATION_TRANSPORT` and never approves vulnerability campaigns. SMTP is transport-tested with a mocked relay; no operational mail was sent.

`BEARINGS_PUBLIC_REGISTRATION=0` closes signup. `BEARINGS_REGISTRATION_HOURLY_LIMIT` defaults to 30 attempts/peer/hour. Only salted rate keys are retained. Verification codes use digests in the database and URL fragments cleared from the browser; GET never consumes them. Trusted proxies must overwrite forwarded peer headers and redact verification/query values in their logs.

After updating, `python3 scripts/dev.py up --no-build` applies migrations before restarting web/worker. Migration 0030 adds phone/commitment fields without backfilling agreement or changing legacy scopes, contacts, intervals or optional-mail policy.
