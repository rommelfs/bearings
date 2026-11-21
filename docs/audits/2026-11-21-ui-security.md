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

1. **Confirm target updates and NetBox activation.** The latest supplied production status confirms managed VM/tenant binding and export of 761 software components. Network export still has no current observation; the AF_NETLINK sandbox correction is locally reproduced and published, but target acceptance remains pending. Source publication is not activation; verify the target receipts and current client network observations after deployment.
2. **Independent Linux release signatures and automated device credential renewal.** HTTPS manifest hashes are integrity checks, not independent release signatures. Device renewal remains an operational lifecycle gap for large fleets.
3. **Review deployed boundaries and every packaged component.** Confirm operator egress/DNS-rebinding enforcement, restricted service/token permissions, backups/restore, proxy header trust, effective login limits, Keycloak/RT and actual bundled/container image advisories. No active production verification of those controls was performed here. The follow-up below patches and checks the actual bundled NetBox Python environment, and rebuilds the local Bearings/FlowIntel images. OS image advisories and production image deployment remain separate checks. The ordinary shared HTTP client still requires its documented operator egress boundary; a DNS precheck alone is not socket pinning.
4. **Browser hardening and identity lifecycle.** A default CSP is implemented and browser-tested in the follow-up below. MFA/operator requirements and broader identity lifecycle acceptance remain open. Do not weaken CSP/CSRF/TLS to make an integration work. The Linux agent currently observes system packages and configured binaries; Python virtualenv/container/SBOM coverage is a separate inventory extension, not implied by a clean dpkg/RPM result.
5. **Further UX cleanup.** Public registration grouping is implemented below. Preserving the chosen language through login/registration and real company-admin/operator task testing remain open. Usage-based feature removal needs evidence; no backend feature is removed in this pass.
6. **Complete accessibility and sustained load validation.** The rendering checks do not constitute a WCAG audit. The bounded UI/queue tests and small synthetic exports do not establish sustained 40,000-company or national fleet ingest/export capacity.

## Deployment

Back up databases and protected configuration, deploy the reviewed commit, and synchronize the correct frozen environment **before** Django management commands. Bearings needs `uv sync --frozen --no-dev --extra production`, `migrate`, `collectstatic`, checks and web/worker/national restart. There is no new portal schema migration, but the updated social-auth Django package has its own migrations. Restart in-progress OIDC logins after the upgrade; do not reset bindings or accounts.

Native NetBox/FlowIntel use their own venvs. Stop their application/workers, synchronize the respective reviewed hash-locked requirement files with `uv pip sync --python ... --require-hashes ...`, run NetBox migrations/static collection/checks through the existing protected ecosystem management wrapper, and restart. The native configuration is loaded from the reviewed repository and must include the identifier-key preservation setting **before** its social-auth migration. Do not rerun first installation, connector setup, identity linking, realm import or mail setup. Do not substitute an unreviewed upstream requirements file. Container deployments require reviewed rebuilt images; changing a host venv does not patch an existing image. See the [native operations guide](../operations/ubuntu24.md).

## Follow-up: actual bundled image, registration and browser policy

The actual bundled upstream NetBox image has 135 installed Python distributions,
with 55 advisory records across eight packages before updates (records include
aliases/duplicates). Nine pinned overrides, including the companion social-auth
Django package, produce zero remaining advisory records in that same complete
installed package set. The image retains its digest-pinned NetBox application,
entrypoint/user and existing volumes; it does not replace the environment with
the smaller native profile lock. `uv pip check` validates the full dependency graph.
The additional packages discovered here are graphql-core, opentelemetry-api and
pyasn1. See [installed image evidence](2026-11-21-bundled-netbox.json). CI now builds
and audits the actual bundled NetBox image rather than inferring its contents from
the native requirements. This does not cover OS packages or other architectures.

The registration form separates organization/account, responsible contact and
participation commitments. Optional address, team mailbox and public encryption
material use a keyboard-operable disclosure. Submitted optional values and errors
keep that section open; an error summary links to invalid controls. Required
consents and server-side submission/verification rules are unchanged.

Default HTML responses now use a same-origin CSP for scripts, fonts and connections,
block objects/framing and constrain base URLs. Inline JavaScript and external
scripts are blocked; inline styles remain allowed for existing Leaflet/admin layout.
Explicit integration frame policies are preserved. Camera, microphone and browser
geolocation permissions are disabled; the map uses recorded company coordinates.
No TLS/CSRF/SSO policy is relaxed. This CSP is defense in depth; it does not replace
escaping, authorization or the production egress boundary.

Local Chromium checks at 390/1440 pixels verify labels, required controls, optional
section keyboard access and no page overflow. An injected inline-script probe is
blocked. Authenticated synthetic national-map, asset and integration pages have no
CSP violations or JavaScript errors. These checks use an actual loopback development
server; they do not establish production browser/firewall acceptance or full WCAG
conformance. The temporary synthetic account is disabled again after checking.

The retained local Bearings and FlowIntel images were also rebuilt with their
updated locks: their actual installed environments contain 32 and 76 distributions,
respectively, with zero reported advisory records. FlowIntel's full dependency check
passes. These are installed-environment checks, not just input-file scans.

During retained-image recreation, the bundled FlowIntel gateway initially returned
502 because its static upstream name retained an obsolete backend IP. Bundled NetBox,
SSO and FlowIntel gateway configurations now re-resolve only their constant Docker
service names through Docker's internal resolver; externally supplied hosts never
select the proxy destination. NetBox gateways overwrite incoming forwarded client-IP
claims consistently with the other lab gateways. The native Ubuntu Unix-socket
reverse proxy is unchanged. A further FlowIntel backend recreation leaves its gateway
running and all three verified-TLS login endpoints return 200 afterward. Gunicorn's
unused FlowIntel control socket is explicitly disabled rather than trying to create
an administrative socket in an unwritable home directory.

After synchronizing the retained Bearings database through social-auth migrations
0018–0022 with the namespace-preservation setting already loaded, the real Keycloak
SSO flow passes across Bearings, NetBox, FlowIntel and RT/RTIR. Shared sessions,
company/foreign/unapproved identity boundaries and the HTTPS integration canvas are
verified. Replacing only an application image while skipping these upstream
migrations is insufficient; the deployment sequence above remains required.
