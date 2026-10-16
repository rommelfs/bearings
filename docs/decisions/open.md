# Open decisions

- License and copyright governance: owner/CIRCL decision required. No LICENSE is selected. Review Django (BSD), psycopg (LGPL), httpx (BSD), NetBox (Apache-2.0), MISP (AGPL family), Vulnerability-Lookup and Plum Island licenses at exact chosen releases before public distribution. This is an initial review checklist, not a legal conclusion about combined works.
- Repository visibility and public release approval: initially private; GitHub API access must verify the existing repository. No public release is authorized.
- Verified security contact, disclosure policy and encryption key.
- SSO/MFA, account lifecycle, operator role governance and minimum production policies.
- Contact review interval: configurable, initial 183-day approximation; calendar-month scheduling and escalation policy still need agreement.
- Retention, audit export, evidence licensing/handling, backups and privacy requirements.
- Live service instances, approved network destinations, least-privilege keys, NetBox site/type/role/tenant mapping and custom-field provisioning.
- Production WSGI server/proxy, TLS, outbound enforcement, deployment topology, scheduler and delivery authorization.
- Actual deployed connector versions. Latest upstream documentation is a starting point, not a tested compatibility promise.
