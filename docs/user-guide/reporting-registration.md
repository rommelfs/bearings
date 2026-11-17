# Infrastructure registration and periodic data review

From **Sign in → Register as an infrastructure responsible person** (`/register/`), provide a company name, responsible contact, unique username/email and at least one IP range, static IP or domain. CIDR prefixes, explicit start-end ranges, IPv4/IPv6 and DNS names are supported, up to 100 declarations. Internal address spaces can have a network-context label. Software inventory is optional; the workspace encourages adding assets and exact installed versions for useful vulnerability matching.

## Email confirmation opens private access

1. Submit the registration. No password or company access exists yet.
2. Open the email link, choose your password and deliberately confirm the request. Opening a link alone has no effect. The one-use code expires after 24 hours; resends replace it and have a 15-minute cooldown.
3. Sign in with the local portal username/password. Your new private workspace is immediately available: review contacts/declarations and add assets/software versions. This does not provision an SSO identity or join an existing company with the same name.
4. CIRCL opens **Registrations** (`/operator/registrations/`), reviews the submitted application and approves or rejects CIRCL sharing. Approval makes this new workspace visible to CIRCL. Rejection leaves private owner access available. CIRCL analysts cannot inspect its live inventory before approval; trusted platform administrators retain administrative access. Application review itself exposes only the submitted application and is audited.

Email confirmation proves mailbox access. It does not verify infrastructure authority. Approval does not convert declarations to verified claims. Existing authority review, contact-role review, emergency availability and vulnerability applicability remain separate.

Self-service inventory uses a **Company-reported inventory** source. Assets are recorded locally without NetBox provisioning or connector write jobs. Existing authoritative NetBox organizations retain their source and existing write/acknowledgment rules. Correcting a declaration expires its old record and creates a fresh unverified declaration; withdrawing expires it without deleting history.

## Keep data current

Each company has **Data review & reminders**, linked from its company page and infrastructure overview. Registered companies start with a configurable interval (default 90 days) and an initial review due now. Existing company administrators can enable the same schedule. Configure:

- Data review interval: 1–365 days.
- Repeat reminder interval while overdue: 1–90 days, default 7.
- Service email reminders: enabled by default for registrations, can be disabled.

Check contacts, IP/domain declarations, assets and installed versions, then confirm the current data. A confirmation records the actor, time, summary counts and a digest of that inventory snapshot, and sets the next due date. It does not assert patches, complete inventory or verified authority. Changed data/schedules invalidate an open confirmation form. Merely changing the schedule does not postpone unreviewed data. Manual-source freshness follows owner confirmation rather than a fictitious connector import.

Due service messages go to the mailbox-confirmed registered administrator and opted-in reachable response contacts, deduplicated by address. DPO-only contacts are excluded automatically; DPO vulnerability outreach retains its separate policy. These generic data-review requests do not silently stop because a contact's role review expired. Messages contain a sign-in link, not the inventory or vulnerability evidence. Current schedule and recipient eligibility are checked again at delivery. Confirmation/opt-out suppress pending messages. Delivery state is visible on the review page.

The bundled worker runs reminders automatically. Other installations must schedule `python manage.py remind_inventory --limit 10` regularly; no GET request sends mail. Queue/delivery attempts are durable, database-locked and deduplicated per due-date/recipient/day. Failed sends retry at most three times with backoff; relay acceptance is not proof of delivery, and an ambiguous SMTP failure can duplicate an email. There is no bounce processing yet.

## Operator settings and local lab

The default backend writes service emails to the local mail sink (`.local/mail` inside the web/worker runtime). It sends no operational email. Set an operator-owned `BEARINGS_PUBLIC_URL` (HTTPS origin without path/query/credentials), or use the configured canvas origin, for email links. DEBUG allows HTTP localhost only. Never construct verification links from a client-supplied Host header.

Actual service delivery requires an explicit `BEARINGS_SERVICE_MAIL_TRANSPORT=smtp` setting plus `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS=1` or `SMTP_TLS=1`, and `DJANGO_DEFAULT_FROM_EMAIL`. For the bundled starter, place these settings in the private `.env` read by Compose; for bare Django, supply process environment variables. Keep credentials outside Git. This switch is separate from reviewed vulnerability outreach (`BEARINGS_NOTIFICATION_TRANSPORT`) and does not approve campaigns. The SMTP timeout is ten seconds. Real service SMTP is transport-tested with a mocked relay, not an operational delivery acceptance.

`BEARINGS_PUBLIC_REGISTRATION=0` closes new signup. `BEARINGS_REGISTRATION_HOURLY_LIMIT` defaults to 30 public attempts per peer/hour (1–1000). Only salted rate keys are retained, not raw peer addresses. Verification codes are retained only as digests, supplied in email URL fragments, cleared from the browser URL and never consumed by GET. Reverse proxies must overwrite forwarded peer headers and redact verification/query information in their own logs. No automatic DNS/IP ownership challenge is performed.

After updating the checkout, `python3 scripts/dev.py up --no-build` applies migrations before restarting web/worker, including the new tables and national-activity indexes. External mode still never provisions external inventory during startup.
