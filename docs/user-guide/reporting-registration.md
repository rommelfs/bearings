# Register your organization and keep infrastructure data current

From **Sign in → Register your organization** (`/register/`), provide your organization, responsible person's first name, last name and role/job title, emergency telephone number, unique username/email. Public PGP/S/MIME material is optional; IP ranges, static IPs and domains are collected later in company configuration. Include the international telephone prefix (`+`); formatting spaces/brackets are normalized. No telephone call or automatic availability verification takes place.

The optional **Company address** field accepts street, postal code, city and country in one text box; it can be skipped and added later. The address is copied to the private organization after mailbox confirmation. Company admins can edit/clear it through **Update company address**; the original submitted application remains unchanged. CIRCL reads the current address under existing organization sharing rules and sees the submitted address in its application review. The address is part of the reviewed data digest. It is a company location, not an assertion of physical server location. The [CIRCL map](circl-map.md) uses separately documented local/manual company positioning.

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
4. CIRCL opens **Registrations**, reviews the application and approves/rejects CIRCL sharing after mailbox verification or an explicitly recorded platform-admin activation override. Approval makes the organization visible to CIRCL. Rejection preserves private owner access. CIRCL cannot inspect live pending inventory; trusted platform administrators retain administrative access. Application snapshots themselves are separately auditable.

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

Migration 0031 adds optional submitted/current company-address fields. Existing addresses remain blank; no location is guessed. Automated resource verification remains a proposal while the low-friction onboarding design is reconsidered.

## Optional team notification mailbox

Signup now offers **Team notification email (optional)** for a shared `security@`, `abuse@`, `noc@` or another valid mailbox; no prefix is mandatory. This is additional to the personal account-confirmation address and creates a separate security contact, not a shared user/login. Equal personal/team addresses are deduplicated.

After personal mailbox confirmation opens the private organization, a separate one-use team confirmation is prepared through the configured service-mail transport. Opening that link only prefills the verification form and clears the URL fragment; a deliberate POST confirms the mailbox. The code is hashed, expires in 24 hours and cannot be replayed. Resend via **Emergency contacts → Prepare verification** respects the service transport and a 15-minute cooldown. A failed team send does not roll back personal access; retry after correcting mail configuration. An unconfirmed team mailbox is excluded from reminders.

Confirmed team mailboxes receive generic periodic data-review requests alongside the registered administrator, with address deduplication and current eligibility checks. Vulnerability outreach still requires the existing contact-role review and campaign approval; mailbox confirmation does not assign those rights, verify availability or grant infrastructure access. Changing a contact's email invalidates old mailbox tokens/status through the existing contact editor.

The periodic test is implemented: the worker queues due requests, sends a link to the authenticated company review page, records the administrator's explicit current-data confirmation, advances the next due date and suppresses queued obsolete requests. Link opening alone and mail scanners never confirm data. The command now includes newly queued jobs in its same-pass delivery cutoff; the worker no longer needs a second iteration for those jobs. Local file delivery remains the default, and real service SMTP must be explicitly configured.

## Configuration wizard and public communication material

Registration no longer requires IP/network/domain declarations. Optional public PGP and PEM S/MIME certificate fields are copied to the private company after mailbox confirmation; they do not prove identity or enable encrypted delivery. CIRCL approval opens the [resumable company setup](company-configuration.md); individual private sections remain available before approval. Existing registrations/scopes and mandatory reminder policy are retained. AIL preferences support a manual YARA handoff and human review, without direct integration or automatic alerts.

## Pending registration: local mail and administrative override

The default lab delivery mode writes messages to local files; it does not send them to external inboxes. The registration receipt now says **Registration saved — local mail mode**. As **platform-admin**, open **Registrations → Service mail & local outbox** (`/operator/service-mail/`) to see the current mode and up to 200 newest local messages, including their recipients and subjects. Read a message to retrieve its verification link for the intended recipient. Views are platform-only, audited, bounded and private/no-store; message HTML is escaped and SMTP-mode access to file previews is disabled. Tokens must not be pasted into issues or shared with unintended users.

The Django backend now lists **Infrastructure registrations** at `/admin/portal/infrastructureregistration/`. Its **Review / administrative activation / resend email** link opens the controlled application view. Choose **Awaiting email** in the registration list to find unconfirmed applicants. The selected filter is retained in the form.

To activate access before mailbox confirmation:

1. Open the application as a platform superuser.
2. In **Administrative activation override**, record the reason and confirm that you will pass the link to the intended responsible person through a trusted channel.
3. Select **Activate private access / issue password setup link**. A private manual-inventory company and its owner membership are created; no staff, analyst, SSO or other-company privilege is granted. The original registration and administrative actor/time/reason are retained.
4. Pass the one-use 24-hour password setup link through that trusted channel. It is displayed only in this response; the administrator never sets or sees the owner's password. Opening the link alone does nothing. The owner explicitly chooses a password and can then sign in.
5. Review CIRCL sharing separately using the normal application decision. Administrative activation alone does not expose the inventory to CIRCL or verify infrastructure authority.

The **email address remains unconfirmed** throughout this override flow. No mailbox reachability, contact-role review or email receipt is invented. Unverified contacts remain ineligible for normal verified-recipient notifications/reminders until separate mailbox proof. The active account initially has an unusable password; login becomes possible only after the owner completes password setup. Before that completion, an administrator can issue another activation link; it invalidates the previous one. The override cannot reset an already usable password and refuses accounts with unexpected roles, memberships, prior activation or privileges. CIRCL analysts without platform-superuser rights cannot perform the override or inspect the local mail store.

For a normally pending application, **Resend verification email** makes an explicit new send attempt, displays local-file/SMTP acceptance or failure, and invalidates the previous token. The platform-admin retry can bypass the public 15-minute cooldown; public resends retain that limit. No SMTP credentials, provider responses or raw tokens are stored in audits. SMTP relay acceptance is not evidence of delivery; configure the existing private SMTP settings described above for actual outbound mail. No production relay was enabled by this change.

## Responsible person's name and company role

New registrations require separate **First name**, **Last name** and **Role / job title within the organization** fields. Names are stored on the local account and retained in the submitted registration; the combined name and declared title are copied to the initial company contact during either mailbox confirmation or administrative activation. Names support Unicode and multiple words; the combined contact name is limited to 180 characters. Titles are free text, up to 120 characters, and grant no portal/SSO/operator permissions or verified contact role.

Migration 0036 adds blank-compatible submission fields without splitting existing full names or inventing titles. Legacy pending registrations still activate using their original contact name and the existing generic responsibility label. Already created accounts/contacts are preserved. The registration review/list displays the submitted company title; subsequent contact edits remain separate from the original submission. Registration still creates local Bearings accounts; central SSO identity and NetBox authorization are separate controlled onboarding steps.
