# Optional SSO: Bearings, NetBox, FlowIntel and RT

Implemented first increment: OIDC authorization-code sign-in for Bearings and the bundled NetBox, with a shared optional Keycloak lab. Login uses PKCE S256, signed RS256 ID tokens, issuer/audience/expiry/nonce checks and explicit issuer+subject account bindings. Application roles remain local. The combined lab also supports FlowIntel for the explicitly linked CIRCL human account. An [RT/RTIR deployment bundle](rt-sso.md) configures the same provider at an existing RT Apache execution boundary; the optional [RT 5 reference lab](rt-lab.md) also provides a running server, scoped queues and automatic client setup.

## Start the synthetic lab

```sh
git pull
python3 scripts/dev.py up --sso --flowintel --rt
python3 scripts/dev.py trust
python3 scripts/dev.py credentials
python3 scripts/dev.py sso-smoke
```

The starter remembers `--sso` for later `up`, `down`, `status`, `manage` and smoke calls. `--no-sso` stops the optional IdP and retains its data; local Bearings/NetBox authentication remains available. With both `--sso --flowintel`, the starter automatically adds and verifies FlowIntel's separate OIDC client and explicit CIRCL account binding, including in a retained realm created before this increment. Omitting `--flowintel` on a fresh lab starts Bearings/NetBox only. External NetBox mode never provisions or rewrites an external installation; configure its identity integration separately.

The browser issuer is **https://localhost:9444/realms/bearings-lab**, Bearings SSO uses **https://localhost:9441/**, NetBox **8443**. Port **8000** remains an HTTP development listener, not an HTTPS endpoint. Trust the public lab CA exported by `trust` in your OS/browser before signing in. The gateway reuses the NetBox lab certificate and verifies backchannel TLS; there is no disabled-verification option. Existing legacy lab CA certificates gain the key-usage extension required by Python 3.14, with the existing CA private/public key retained. Re-export the public certificate after updating. No private CA key is exported.

In Bearings choose **Sign in with SSO** and enter the generated demo password once as `company-admin` or `circl-analyst`. Then open NetBox, choose its **OpenID Connect** sign-in button: the same IdP session signs you in without another password prompt. Each application has its own session and client secret. As `circl-analyst`, also open FlowIntel at **https://localhost:9443/account/login** and choose the prominent **Sign in with SSO** button: the existing IdP session signs in to the existing CIRCL case-workflow account. Company and unassigned demo identities are intentionally denied there.

- Bearings maps to the **existing** local company/CIRCL accounts and preserves their memberships, operator policies, passwords and privilege flags.
- NetBox uses separate `sso-company-admin` / `sso-circl-analyst` human accounts. The company demo has read-only inventory access to the RW lab tenant; CIRCL's demo can read both synthetic tenants. These permissions are explicit NetBox object permissions; the humans do not inherit API service-account keys or write capability.
- `unassigned-demo` exists only in Keycloak to test default denial. Its valid IdP login cannot create an application account or grant access.
- `platform-admin` and `netbox-admin` remain separately managed local emergency accounts; no IdP identity is assigned to them by the fixture.

Keycloak **26.8.1** runs as a local-only development service with a separate persistent H2 data volume, private import/client/bootstrap inputs and a 768 MiB container limit. Realm imports skip existing realms. Password/role changes in a retained realm are preserved. This profile is not a production IdP deployment; use a managed IdP with its own database, backups, availability and MFA policy. Allow additional Docker memory/disk beyond the existing NetBox/FlowIntel lab; 8 GB of Docker memory is recommended without RT, or about 10 GB with all optional services.

## Use an operator-managed OIDC provider

Bearings supports one configured issuer per installation. Keycloak can broker additional company identity providers. Configure the following server-side values using your approved provider's metadata, with separate client credentials for each application:

```dotenv
BEARINGS_SSO_ENABLED=1
OIDC_ISSUER=https://idp.example.org/realms/example
OIDC_CLIENT_ID=bearings
# OIDC_CLIENT_SECRET belongs in private runtime secret storage, never Git.
OIDC_AUTHORIZATION_URL=https://idp.example.org/realms/example/protocol/openid-connect/auth
OIDC_TOKEN_URL=https://idp.example.org/realms/example/protocol/openid-connect/token
OIDC_USERINFO_URL=https://idp.example.org/realms/example/protocol/openid-connect/userinfo
OIDC_JWKS_URL=https://idp.example.org/realms/example/protocol/openid-connect/certs
OIDC_SESSION_SECONDS=1800
```

The explicit endpoints are Keycloak examples; other OIDC providers can supply different approved HTTPS paths. Runtime requests use only configured endpoints, reject redirects and bound responses to 1 MB with a ten-second timeout. Optional `OIDC_CA_BUNDLE` selects an approved CA file; TLS verification remains enabled. Production callbacks use HTTPS. Register the exact Bearings `/oauth/complete/oidc/` URL; no wildcard redirects, implicit flow or password grant is needed. The bundled lab uses exact HTTPS callbacks on the configured workspace port, including for logins initiated from its HTTP development entry. Enabling the bundled profile overrides its app endpoints with guarded lab settings; it does not change external IdP configuration.

A platform administrator explicitly links a verified immutable subject to an existing local account:

```sh
uv run python manage.py link_oidc_identity --actor existing-platform-admin --username existing-user --subject IMMUTABLE-IDP-SUBJECT
```

Email, preferred username and group claims do not link accounts or grant roles. The stored identity hashes both issuer and subject, so changing providers cannot reuse another issuer's subject. The command refuses reassignment to another local account and audits changes. It changes no password, company membership, staff/superuser flag or CIRCL group. Revocation is explicit:

```sh
uv run python manage.py link_oidc_identity --actor existing-platform-admin --username existing-user --subject IMMUTABLE-IDP-SUBJECT --revoke
```

Revocation leaves a disabled binding; the lab bootstrap preserves it. A later explicit relink rotates the binding generation, so old Bearings sessions cannot become valid again. Bearings checks the binding/account on each request and enforces an absolute configured SSO session lifetime, default 30 minutes. Local account deactivation and membership changes apply through the existing authorization rules. IdP-side revocation without backchannel notifications takes effect at reauthentication; automatic account synchronization is not implemented.

For an independently operated NetBox, configure its supported OIDC backend, a distinct client and explicit local permission/identity mapping through its operator. The bundled example uses the same approved backend module, an issuer+subject-derived `UserSocialAuth` UID and a pipeline without user creation, email association, role claims or token persistence. Its read permissions and existing account/permission changes are preserved on restart. Bindings can be disabled in their local metadata or the account disabled; NetBox uses its own session policy with a 30-minute verification limit. Production NetBox versions/extensions require separate compatibility and revocation acceptance.

## Sign-out, MFA and recovery boundaries

**Sign out here** closes the current Bearings session. It leaves the IdP and other application sessions active; choosing SSO again can sign in without another prompt. Global/frontchannel/backchannel logout, cross-application session termination, SCIM and automated group provisioning are separate work. Close/sign out of the IdP as well when changing users on a shared browser.

MFA is controlled by the IdP. Existing local passwords are preserved, so enabling SSO alone does not make MFA mandatory for those local logins. After testing SSO, operators can separately restrict participant password access while retaining audited emergency accounts. An IdP outage does not remove local accounts or data. API connectors continue using their own scoped server-side credentials.

The pinned FlowIntel build uses an adapter with signed JWT verification, fixed verified HTTPS backchannels, S256 PKCE, nonce/state, POST/CSRF initiation, session-ID regeneration and exact issuer/subject bindings. Its upstream native Keycloak switch remains off. The adapter creates no users and changes no roles, organization, password or API key on sign-in. Only the existing synthetic CIRCL human is linked; the API bridge and local platform administrator are not. Bindings live in a separate `bearings_oidc_binding` table in the FlowIntel database, without modifying upstream tables or migration history. Local account deletion and binding revocation invalidate SSO access; the upstream account model has no independent active flag.

The Docker operator can inspect or explicitly revoke/re-enable the synthetic binding:

```sh
python3 scripts/dev.py flowintel-sso status
python3 scripts/dev.py flowintel-sso revoke
python3 scripts/dev.py flowintel-sso enable
```

Each explicit change rotates the session generation. Startup preserves a revoked binding, and old sessions cannot revive after re-enabling it. FlowIntel SSO sessions have an absolute 30-minute lifetime. Turning off the profile invalidates SSO sessions while retaining local logins and data. Removing an IdP account alone takes effect at reauthentication; shared logout and backchannel revocation remain separate work. The SSO login adapter targets the pinned bundled FlowIntel build; independently installed FlowIntel needs its operator to install/review this adapter and credentials.

The one-off client provisioner alone can read the lab IdP bootstrap credential; running applications do not receive that administrator credential. Existing disabled clients, users and passwords are preserved. A differing retained callback, client policy or secret fails startup without rewriting either side. If the lab IdP administrator password has been deliberately rotated, update its private provisioner input through the operator rather than resetting the realm. Do not copy this lab provisioning credential into a production application.

RT/RTIR uses the [generated Apache/RT deployment bundle](rt-sso.md), with its own client and immutable subject map, without changing queue permissions or enabling user creation. The existing RT installation requires its operator's acceptance; external instances are not provisioned by `up`. For a self-contained local reference, add `--rt` and follow the [RT lab guide](rt-lab.md).

The guarded `sso-smoke` uses Python's standard library, private generated credentials in memory and normal CA/hostname verification. It exercises the real IdP/code exchange, a single company password prompt across both apps, permitted/foreign NetBox inventory and unapproved identity denial, plus CIRCL FlowIntel sign-in and company denial when enabled; it prints no secrets or callback URLs. See [validation](../validation.md).

## Synthetic login view

![Bearings optional SSO and local sign-in](../images/sso-login.png)

The optional [native RTIR lab](rtir-lab.md) uses `up --sso --flowintel --rtir` and the existing RT OIDC boundary. CIRCL can coordinate Incidents and Investigations; company RT identities keep their ordinary private queues without RTIR access.

## FlowIntel still shows a password login

Update and explicitly enable both profiles (including a previously installed lab):

```sh
git pull
python3 scripts/dev.py up --sso --flowintel --rtir
python3 scripts/dev.py flowintel-sso status
python3 scripts/dev.py sso-smoke
```

Open **https://localhost:9443/account/login**. The primary blue SSO card appears above the expandable **Local account / administrator recovery** form. Use **circl-analyst** at Keycloak; an existing session for that account avoids a second password prompt. A local Bearings `platform-admin` login does not establish a Keycloak session. If Keycloak already has a company identity signed in, sign out there before switching to CIRCL; company accounts have no access to the shared CIRCL FlowIntel workspace.

Earlier adapters rendered a light SSO button on the light page background, making it difficult to see. Also, Compose does not reload bind-mounted Python changes in existing Gunicorn processes. The starter now restarts FlowIntel on each explicit `up` and waits for health before returning. It reports whether shared sign-in is enabled. It preserves existing users, passwords, client policies and revoked bindings. A reported revoked binding needs an explicit operator decision; startup does not re-enable it.

The upstream `KEYCLOAK_ENABLED=False` setting is intentional: the Bearings adapter handles OIDC. Turning on FlowIntel's separate native switch is not required. For independently installed FlowIntel, this bundled adapter is not installed by the starter.

## Connected application canvas

The SSO lab now starts a verified HTTPS Bearings entry at **https://localhost:9441/applications/** automatically. Use **Applications** to choose visible NetBox, FlowIntel or RT/RTIR connections; authenticate in a top-level tab, then show the native interface inside the Bearings frame. Existing application permissions and separate recovery/session boundaries remain intact. The starter supports `BEARINGS_CANVAS_PORT` with an exact HTTPS callback for the Bearings client. See [setup, external acceptance and screenshots](../user-guide/applications.md).


## Safari cannot open the callback on HTTPS port 8000

`https://localhost:8000/oauth/complete/oidc/` uses TLS against a plaintext HTTP listener. A running service there still cannot answer that request. The former lab callback returned to HTTP localhost:8000; browsers with localhost HSTS or HTTPS upgrade policies can upgrade it to HTTPS, because HSTS is scoped to the hostname across ports.

Update and start the existing lab:

```sh
git pull
python3 scripts/dev.py up --sso
```

Then start a **new** login at **https://localhost:9441/accounts/login/**. The old authorization response is tied to the previous redirect URI; do not edit or replay it. The callback now remains on **https://localhost:9441/oauth/complete/oidc/** (or the configured `BEARINGS_CANVAS_PORT`). No browser TLS/HSTS setting needs to be disabled.

Startup creates/verifies the separate Bearings client-provisioning job before app initialization. It narrowly migrates the exact generated legacy HTTP callback list to the exact HTTPS localhost/127.0.0.1 workspace callbacks, after checking retained client policy, PKCE and secret. Disabled state, users, roles, credentials and custom client fields are preserved. Modified callback lists, authentication policy or mismatched secrets fail closed for operator review rather than being reset. The generated private provisioning file lives in the Bearings secrets volume, outside Keycloak's realm-import directory. App/worker processes restart on explicit SSO startup so retained images load the updated callback too. Independently operated IdPs and NetBox callbacks are unchanged.
