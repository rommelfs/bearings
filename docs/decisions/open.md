# Open decisions

- License decision: the owner selected AGPL-3.0-or-later on 2026-10-16; LICENSE and package metadata record it. Continue reviewing third-party notices at exact chosen dependency/integration releases; this does not relicense upstream software or data. Copyright attribution and contributor governance should reflect actual rights holders, not invented assignments.
- Visibility decision: the owner confirmed a public open-source project from the start. Publish source and the development backlog to `rommelfs/bearings`. Production deployment, operational data publication, scanning and real notifications remain separately authorized actions.
- Verified security contact, disclosure policy and encryption key.
- SSO global session lifecycle, MFA/fallback policy, account lifecycle, operator role governance and minimum production policies.
- Contact review interval: configurable, initial 183-day approximation; calendar-month scheduling and escalation policy still need agreement.
- Retention, audit export, evidence licensing/handling, backups and privacy requirements.
- Live service instances, approved network destinations, least-privilege keys, NetBox site/type/role/tenant mapping and custom-field provisioning.
- Production WSGI server/proxy, TLS, outbound enforcement, deployment topology, scheduler and delivery authorization.
- Actual deployed connector versions. Latest upstream documentation is a starting point, not a tested compatibility promise.
