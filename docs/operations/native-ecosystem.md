# Native NetBox, FlowIntel and Keycloak on Ubuntu 24.04

This extends the [existing native Bearings server](ubuntu24.md). It does not run the developer Compose stack, seed companies/assets, replace the Bearings database/key, change existing inventory source identities, enable public registration or send notifications. The operator executes the commands on the server as root. Local component tests do not establish a production SLA or replace target acceptance.

## Layout and boundaries

| Application | Public origin | Internal listener | Database role/database |
| --- | --- | --- | --- |
| Bearings | `https://bearings.circl.lu` | Existing private socket | Existing `bearings` |
| NetBox 4.7.3 | `https://netbox.bearings.circl.lu` | `/run/bearings-netbox/web.sock` | `bearings_netbox` |
| FlowIntel pinned case-workflow build | `https://flowintel.bearings.circl.lu` | `/run/bearings-flowintel/web.sock` | `bearings_flowintel` |
| Keycloak 26.8.1 | `https://sso.bearings.circl.lu` | Loopback 18083; health 19000 | `bearings_keycloak` |

Separate non-login users, PostgreSQL databases/roles, root-owned source/virtual environments and protected runtime directories isolate the services. NetBox/FlowIntel use local PostgreSQL peer authentication; Keycloak uses a separately generated local TCP database password. No application role is a PostgreSQL superuser. The two Redis instances have separate private Unix sockets, with no TCP listeners. An existing global Redis installation is preserved; the unused default service is stopped only if newly installed by this installer.

Native source lives under `/opt/bearings-services`, private configuration/receipts under `/etc/bearings/ecosystem`, runtime data under `/var/lib/bearings-*`, public NetBox static assets under `/var/www/bearings-netbox/static`. PostgreSQL storage remains owned by Ubuntu's PostgreSQL service. Back up all these state/configuration locations and all four databases together. Never delete the receipt to retry installation; it contains retained keys/passwords and source identity.

NetBox and FlowIntel source commits are fixed. Python packages are hash-locked, and Keycloak's official archive is verified against a recorded SHA-256. NetBox uses the upstream pins with psycopg binary/pool and Gunicorn 25.3.0 for this native profile. These checksums are not independent publisher signatures. Source/license notices remain in the upstream trees. FlowIntel is the same bounded case-workflow runtime tested by the lab; PDF/AI/analyzer infrastructure and outbound SMTP/Matrix/webhooks are not deployed.

## 1. Prepare DNS and backups

Point the three additional names at the existing server, with A/AAAA records or CNAMEs to `bearings.circl.lu.`. Publish AAAA only with working end-to-end IPv6. Allow TCP 80/443; do not expose databases, Redis, health or native application ports. Make and verify a backup of the existing Bearings database, private environment and state before changing services.

Use the reviewed source revision supplied with the implementation. The original guide used a detached checkout, so use `git fetch` and an explicit reviewed revision rather than assuming `git pull` updates it:

```sh
cd /opt/bearings
git fetch origin
git checkout --detach REVIEWED_COMMIT
python3 deploy/ubuntu24/ecosystem.py plan
```

Recommended starting allocation: at least 8 GiB RAM, four CPUs and sufficient disk for all databases/uploads/backups. `free` and `/proc/cpuinfo` can show the host capacity in LXC: inspect the actual cgroup/container limits too. Keycloak's heap is explicitly capped at 1 GiB; application workers use conservative counts, not the host CPU count. This is a starting allocation, not capacity evidence.

## 2. Install internal services

Replace the email below with the intended first FlowIntel administrator address. This creates a local recovery account but sends no mail. On the constrained plain LXC installation diagnosed in this conversation:

```sh
python3 deploy/ubuntu24/ecosystem.py install --lxc-compatible --admin-email YOUR_EMAIL
```

For a host supporting the complete systemd mount sandbox, omit `--lxc-compatible`; the unprivileged sandbox preflight must pass. Compatibility is explicit: it omits the inner filesystem mount protection, retaining dedicated identities, no-new-privileges, empty capabilities, SUID restrictions and ordinary filesystem permissions. Outer LXC confinement is not changed. Do not globally disable AppArmor or use a privileged container as a shortcut.

The command installs Ubuntu packages, separate pinned runtimes, schema migrations and services. Fresh NetBox migrations can take several minutes. Successful service start alone is insufficient: the helper waits for actual native login/health responses before reporting readiness. This stage installs ACME-only HTTP virtual hosts; it does not expose the application over plaintext HTTP.

If interrupted, inspect the error and repeat **the same command and flags**. Keys/passwords and application records are retained. Unknown pre-existing accounts/directories/databases/sites are refused instead of adopted. After successful activation, the first-install command refuses reuse; upgrades require review/backups. No unattended upgrade is implemented. In a failure, the existing Bearings installation remains separate; do not reset its database/environment or run `scripts/dev.py` on this server.

## 3. Certificate and activation

After DNS reaches this server, obtain an operator-approved certificate. If Let's Encrypt HTTP-01 is the chosen policy, substitute the operational certificate contact address:

```sh
certbot certonly --webroot -w /var/lib/letsencrypt --cert-name bearings-ecosystem -d netbox.bearings.circl.lu -d flowintel.bearings.circl.lu -d sso.bearings.circl.lu --email YOUR_EMAIL --agree-tos
python3 deploy/ubuntu24/ecosystem.py activate
```

Alternatively install the approved certificate/key at the two paths expected by the generated sites, or review the templates for your organization's certificate management. Do not overwrite the existing Bearings certificate. Certbot renewal is already enabled by the base deployment; test renewal policy as appropriate.

Activation tests Nginx configuration and rolls back generated site files on configuration failure. It verifies the exact public HTTPS issuer using the server's trusted CA store, then appends the retained Bearings client configuration to its private environment and restarts Bearings. The original environment is backed up as `/etc/bearings/ecosystem/bearings-before-sso.env`. Existing different SSO issuer/client settings cause refusal, never silent identity repointing. On failed Django configuration checks the environment is restored. A later runtime failure needs operator recovery; activation is not a distributed transaction.

Verify after application boot:

```sh
systemctl --no-pager status bearings-web bearings-worker bearings-national bearings-netbox bearings-netbox-worker bearings-flowintel bearings-keycloak bearings-netbox-redis bearings-flowintel-redis
curl --fail --head --max-time 15 https://bearings.circl.lu/accounts/login/
curl --fail --head --max-time 15 https://netbox.bearings.circl.lu/login/
curl --fail --head --max-time 15 https://flowintel.bearings.circl.lu/account/login
curl --fail --max-time 15 https://sso.bearings.circl.lu/realms/bearings/.well-known/openid-configuration
```

The native sites omit access logs and suppress proxied request error logging to avoid retaining authentication-code queries. Diagnose startup through the protected service journals and internal readiness/socket checks. Do not paste credentials, cookies, full environment files or authentication URLs into public issues.

## 4. Local recovery accounts and explicit SSO

Create NetBox's own recovery administrator interactively, then display the generated initial Keycloak/FlowIntel recovery credentials **on the server terminal only**:

```sh
python3 deploy/ubuntu24/ecosystem.py manage netbox createsuperuser --username platform-admin
python3 deploy/ubuntu24/ecosystem.py credentials
```

Changed passwords cannot be recovered by `credentials`; it shows the initial values only, never rotates them or exposes API/OIDC/database keys. Existing Bearings local recovery remains available at `/accounts/login/`. Keycloak's initial administrator is a bootstrap account: replace it with an individually managed administrator/MFA policy before onboarding customers. Keycloak SMTP, password recovery and MFA require explicit operator configuration and acceptance; they are not silently enabled.

Open Keycloak's `/admin/` console, select the **bearings** realm, create the intended human user and set a temporary initial password. Copy that user's **immutable User ID**. The realm initially has no company, analyst or demo users. The three clients have exact callbacks, confidential independent credentials, code flow and mandatory PKCE; password/implicit/service-account grants are disabled for these clients.

Link the verified same User ID to existing local accounts. Replace actor/account names as appropriate. These commands grant no new local roles or company membership:

```sh
/opt/bearings/deploy/ubuntu24/manage.py link_oidc_identity --actor platform-admin --username platform-admin --subject KEYCLOAK_USER_ID
python3 deploy/ubuntu24/ecosystem.py link-netbox-sso --actor platform-admin --username platform-admin --subject KEYCLOAK_USER_ID
python3 deploy/ubuntu24/ecosystem.py manage flowintel link-sso --actor YOUR_EMAIL --user YOUR_EMAIL --subject KEYCLOAK_USER_ID
```

NetBox/FlowIntel linking refuses existing/revoked bindings rather than resetting them. Bearings uses its existing audited link/revoke command. Different applications retain their own permissions. A matching email alone never links accounts. Test an explicitly linked user and an unassigned user; the latter must not get access. A provider login should avoid a second password prompt across applications, while local recovery remains usable. Absolute SSO sessions are bounded; global logout, SCIM and coordinated cross-application deprovisioning are not implemented.

Native pages retain their own framing policies and are initially opened separately; the lab's embedding exception is not automatically deployed. NetBox `/media/` is deliberately not publicly served in this profile because uploads can contain private files. Public static assets work; private attachment/media delivery needs a separately reviewed authorization-aware design before use.

## 5. Bind actual company inventory and CIRCL case work

Installation/SSO does **not** prove authorized inventory access. Do not connect customers using a NetBox administrator's token. In NetBox, create each company's tenant and separately constrained human/API identity. Start with read-only API permissions and test foreign-tenant denial. Register the approved instance/credential reference and exact company/tenant binding in Bearings administration, then perform the first GET-only import. Review device/VM/IP/prefix and reference-data permissions before enabling writes. Empty manual inventory may be converted through the approved onboarding workflow; a populated manual inventory or existing authoritative source must not be repointed automatically. The developer `enroll-company-sso` script is lab-only and must not be used here.

For FlowIntel, create a CIRCL service organization and a dedicated non-admin Editor bridge account within it. Store its API key server-side in the protected Bearings environment under a dedicated variable, then configure a `FlowIntelInstance` with that variable name, the HTTPS URL and the expected service organization ID. Do not reuse the recovery administrator key. Verify scope/current permissions and a controlled case before enabling operational exports. Existing visibility checks, analyst approval and notification policies continue to apply; installing FlowIntel does not authorize customer data export or delivery.

Automatic native company/tenant/API provisioning and a one-command production connector rollout remain separate work. This deployment establishes the services and explicit identity linkage; it does not pretend the lab enrollment fixture is production onboarding.

## Recovery and updates

Inspect `journalctl -u bearings-netbox -u bearings-netbox-worker -u bearings-flowintel -u bearings-keycloak --since '-10 minutes' --no-pager`. Keep secrets/config/receipts and database state together. A boot-time 502 may disappear after workers finish loading; a persistent one needs the current journal/socket evidence. Do not weaken sandbox flags beyond the explicitly selected compatibility policy.

For SSO configuration rollback, retain local recovery access, stop/review affected workers, restore the protected `bearings-before-sso.env` backup and restart the three Bearings services. Do not delete the Keycloak realm or native application databases. Restoring that environment also restores its old service configuration; reconcile any changes made after the backup rather than blindly copying it over.

Upgrades are reviewed maintenance: back up/restore-test all databases/state/config, preserve identity/client credentials and bindings, update pinned upstream versions/hash locks, run migration/component/permission tests, reconcile unit/proxy changes, then restart and verify. The first-install helper deliberately refuses to upgrade an activated installation. Sustained workload, monitoring, host hardening, backup restores, real certificate renewal and customer lifecycle acceptance remain operator requirements.
