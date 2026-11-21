# First UI and security audit — 21 November 2026

The target is https://bearings.circl.lu. Production inspection used only public GETs; no registration, email, signed-in production action, exploit payload, scan, patch or deployment was performed. Authenticated flows, negative authorization cases and runtime changes use local synthetic fixtures. This is an initial audit and correction pass, not a complete penetration test or a claim that production has installed the corrected dependencies.

## Public observations and UI corrections

Verified HTTPS responses were rendered in Chromium at 1440 and 390 pixels: four marketing languages, four FAQ translations, login, registration, invitation acceptance and Linux downloads — 24 layouts. Public responses have no detected JavaScript errors, failed resources, unlabelled form controls or broken local anchors. The Linux download page overflows horizontally on mobile. Browser transport uses HTTPX through the environment proxy with certificate verification; the browser profile does not trust the interception CA directly. This is a rendering/HTTP check, not independent production TLS or firewall certification. Response caching is used between widths, so recorded rendering times are not production latency benchmarks.

The source review confirms that an inactive NetBox export disappears entirely from the asset page. The Linux reporting route also defaults to vulnerability-review navigation. Both obscure the current workflow. These are corrected:

- Always display separate **Client reports**, **NetBox host** and **NetBox inventory export** states. Disabled, read-only, unconfigured, pending, failed, inactive and confirmed stages remain distinct. A registered host never implies exported software/IPs. Historical receipts remain labelled as previous confirmations; stale/newer observations do not become fresh export proof.
- Keep software, CVE reviews, client reports and the direct NetBox record visible. Secondary asset operations are grouped under **More asset actions**, retaining existing edit-role checks.
- Group navigation into Overview, Inventory, Security and Response. Integrations, Administration and Help use native keyboard-accessible disclosure controls; the active group opens automatically. Analyst and superuser administration remain role-specific. Unconfigured synthetic examples leave primary navigation; configured examples and explicit routes remain available. Federation is labelled **Federated company reports**, rather than suggesting a NetBox connection.
- Correct the client reporting route's inventory orientation, constrain download command blocks to their own horizontal scroll area, and group manual single-host enrollment under an advanced disclosure. Update stale rollout copy to distinguish observed-only and explicit managed registration.

Authenticated local Chromium checks cover asset, client, integration and download pages at desktop/mobile widths. The export-off state is visible, current navigation remains visible, secondary actions and enrollment expand by keyboard, and the document has no horizontal overflow. A synthetic reader cannot see editor-only actions or access a foreign asset. Status presentation makes no upstream calls or write-policy changes. Screenshots contain only synthetic local inventory:

- [Desktop asset](2026-11-21-asset-1440.png)
- [Mobile asset](2026-11-21-asset-390.png)
- [Mobile downloads](2026-11-21-downloads-390.png)

## Dependency findings and corrections

`pip-audit 2.10.1` checks the exported frozen production lock plus the separate native NetBox and FlowIntel locks. The baseline reports include duplicate advisory records; deduplicated IDs and exact package changes are in the [machine-readable record](2026-11-21-ui-security.json).

| Profile | Flagged packages corrected | Post-update checked records | Remaining known advisory records |
| --- | --- | ---: | ---: |
| Bearings | certifi, oauthlib, social-auth-core | 33 | 0 |
| Native NetBox | djangorestframework, Pillow; shared OIDC dependency updated too | 98 | 0 |
| FlowIntel | cryptography, dnspython, Werkzeug | 76 | 0 |

Compatibility dependencies social-auth-app-django and MSAL are updated with their corresponding core/cryptography dependency. The native NetBox source stays at its reviewed revision; DRF/Pillow/auth packages are explicit reviewed profile overrides. The original root OIDC configuration already enables PKCE, which mitigates the shared-nonce authorization-code injection advisory's default flow. SAML, LoginRadius, VK and Vend backends are not enabled, and Bearings is not an oauthlib device-code authorization server. Installed vulnerable packages are nevertheless updated rather than declaring every advisory an exploitable Bearings vulnerability.

The OIDC adapter uses the patched core's session-bound nonce checks and error taxonomy while preserving existing issuer+subject digest UIDs. It does not enable claim/email-based identity migration. `SOCIAL_AUTH_OLD_ID_KEYS={"oidc": None}` prevents an upstream data migration from relabelling pre-approved digest identities as raw subjects. The historical empty identifier-key namespace, explicit approval, tombstones, local roles and passwords are retained. New stage metadata is consumed locally rather than sent as an HTTP request option. Negative tests reject a valid nonce issued to another browser without consuming the original browser's legitimate login. Legacy exception imports remain only for retained native services during a staged upgrade; the root frozen floor requires the patched core.

CI now audits all three locks on pushes/pull requests. A clean advisory result is time-dependent and is not proof that all code, images or deployed services are safe.

## Authorization and runtime evidence

The existing 121-case PostgreSQL security baseline passes before changes. The updated release subset passes 173 PostgreSQL cases across signed SSO/PKCE/state/nonce, explicit identity linking and revocation, role boundaries, company membership/domain invitations, signed agent admission/replay, read-only/foreign-source NetBox denial, application framing/origins, scoped inventory, registration and public/private entry points. A final focused UI/authentication subset passes 56 cases. Native helper tests pass 23 cases. The production-profile smoke confirms non-superuser PostgreSQL, verified loopback TLS/Gunicorn, signed agent enrollment, closed registration, static delivery and worker execution without synthetic seeding or host-service installation.

The isolated native NetBox/FlowIntel fixture uses complete hash-locked requirements, disposable PostgreSQL/Redis, actual management commands/static collection and real ORM checks. It verifies login availability, tenant isolation, identity retention and private Redis sockets. The final isolated smoke passes with both complete updated runtime locks. The complete retained NetBox/FlowIntel/RT/RTIR smoke and five real NetBox ORM link/namespace checks also pass. Those retained-image checks are compatibility regression evidence; their image contents are not established by scanning the separate native locks. Deployment/remaining runtime evidence is recorded in validation.md.

## Remaining work, in priority order

1. **Confirm target updates and NetBox activation.** Last supplied production status has export disabled and enrollment-age network observations. Source publication is not activation; verify the target receipts and current client network observations after deployment.
2. **Independent Linux release signatures and automated device credential renewal.** HTTPS manifest hashes are integrity checks, not independent release signatures. Device renewal remains an operational lifecycle gap for large fleets.
3. **Review deployed boundaries and every packaged component.** Confirm operator egress/DNS-rebinding enforcement, restricted service/token permissions, backups/restore, proxy header trust, effective login limits, Keycloak/RT and actual bundled/container image advisories. No active production verification of those controls was performed here. The retained bundled NetBox image still reports social-auth-core 5.2.0, DRF 3.18.0 and Pillow 12.3.0; its official image needs a separately reviewed patched build/upgrade before being treated as patched. The native lock corrections do not alter that image. The ordinary shared HTTP client still requires its documented operator egress boundary; a DNS precheck alone is not socket pinning.
4. **Browser hardening and identity lifecycle.** Review a broader CSP without breaking approved native frames, MFA/operator requirements and native dependency lifecycle. Do not weaken CSP/CSRF/TLS to make an integration work. The Linux agent currently observes system packages and configured binaries; Python virtualenv/container/SBOM coverage is a separate inventory extension, not implied by a clean dpkg/RPM result.
5. **Further UX cleanup.** Group the public registration's optional address/team/crypto material, preserve the chosen language through login/registration, and test real company-admin/operator tasks with users. Usage-based feature removal needs evidence; no backend feature is removed in this pass.
6. **Complete accessibility and sustained load validation.** The rendering checks do not constitute a WCAG audit. The bounded UI/queue tests and small synthetic exports do not establish sustained 40,000-company or national fleet ingest/export capacity.

## Deployment

Back up databases and protected configuration, deploy the reviewed commit, and synchronize the correct frozen environment **before** Django management commands. Bearings needs `uv sync --frozen --no-dev --extra production`, `migrate`, `collectstatic`, checks and web/worker/national restart. There is no new portal schema migration, but the updated social-auth Django package has its own migrations. Restart in-progress OIDC logins after the upgrade; do not reset bindings or accounts.

Native NetBox/FlowIntel use their own venvs. Stop their application/workers, synchronize the respective reviewed hash-locked requirement files with `uv pip sync --python ... --require-hashes ...`, run NetBox migrations/static collection/checks through the existing protected ecosystem management wrapper, and restart. The native configuration is loaded from the reviewed repository and must include the identifier-key preservation setting **before** its social-auth migration. Do not rerun first installation, connector setup, identity linking, realm import or mail setup. Do not substitute an unreviewed upstream requirements file. Container deployments require reviewed rebuilt images; changing a host venv does not patch an existing image. See the [native operations guide](../operations/ubuntu24.md).
