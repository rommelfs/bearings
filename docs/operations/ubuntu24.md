# First deployment on Ubuntu 24.04 with systemd

This is a native installation for a fresh systemd host/LXC/Incus container, using Ubuntu PostgreSQL 16, Gunicorn 25.3, Nginx and independent workers. It does not run Docker inside the container, the developer bootstrap or synthetic seeds. The supplied first-install helper targets **bearings.circl.lu**. Review the checked-out revision/scripts before executing them as root. This prepares an initial controlled deployment; it is not a production security audit, recovery/throughput SLA or approval to enable all integrations.

## 1. Source and installation

Run on the new container as root (or prefix administrative commands with sudo). The installer first tests the required systemd mount-namespace sandbox in a transient unit. If LXC/Incus denies it, review the container's nesting/sandbox policy with its host operator; the script stops before package/account/database changes and does not silently remove protections. It also refuses another OS, PID1 without systemd, unexpected existing account/database/environment/proxy state and a checkout outside `/opt/bearings`. It never drops/reset databases or regenerates an existing environment secret.

```sh
umask 022
apt-get update
apt-get install -y git ca-certificates
git clone --branch codex/continuous-review-workflow https://github.com/rommelfs/bearings.git /opt/bearings
cd /opt/bearings
git rev-parse HEAD
bash deploy/ubuntu24/install.sh
```

Record/review that source revision; the development branch moves. The helper installs Python 3.12, pinned uv, frozen production dependencies, PostgreSQL, Nginx and Certbot. It creates the dedicated non-login `bearings` account/database role/database, root-owned mode-0600 `/etc/bearings/bearings.env` with a newly generated random secret, `/var/lib/bearings` private state and public static/client directories. It runs committed migrations, static collection and deploy checks, then enables web/worker/national services. Dependencies/source remain root-owned; the application can write only its state/runtime directories.

PostgreSQL uses the local Unix socket and peer authentication as the dedicated OS/database user. There is no shared/default database password and no public database listener is configured. Do not silently change peer authentication to `trust`. If using a remote database instead, configure a separate scoped role/verified TLS and review the connection/secret setup explicitly.

At this point HTTP serves certificate challenges only; the application is on a private Unix socket. **No public registrations, SMTP delivery, lab accounts, example companies or external provisioning are enabled.** A partial failure may retain account/database/private environment for recovery. Inspect the error and resume migration/check/services using the retained secret; do not delete/reseed/regenerate it or rerun first-install automation blindly.

## 2. Initial platform administrator

```sh
/opt/bearings/deploy/ubuntu24/manage.py createsuperuser --username platform-admin
```

Enter your own email/password at the prompts. This is a local bootstrap/recovery account. No lab `credentials` password is generated. The helper uses a transient systemd service with the same root-protected EnvironmentFile and application identity (PTY for interactive prompts, direct pipes for automation); do not print/source secrets into a shell command line or issue report.

## 3. HTTPS for bearings.circl.lu

First make DNS A/AAAA records point at the correct service and route ports 80/443 to this container. A stale/unrouted AAAA record can break validation for IPv6 clients. SSH access is managed by your existing host policy; only the web edge should be publicly exposed. Verify the domain/certificate policy with the operator.

If direct HTTP-01/Let's Encrypt is appropriate, obtain the certificate using your chosen operational contact address:

```sh
certbot certonly --webroot -w /var/lib/letsencrypt \
  -d bearings.circl.lu --email YOUR-OPERATIONAL-CONTACT --agree-tos
install -m 0644 /opt/bearings/deploy/ubuntu24/nginx.conf /etc/nginx/sites-available/bearings
nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer
certbot renew --dry-run
```

If CIRCL supplies/manages certificates instead, install the operator-approved chain/key and adjust only the two certificate paths in the supplied HTTPS configuration; do not issue another certificate automatically. If TLS terminates at an existing external edge, adapt the Unix/private-hop/header policy explicitly instead of exposing Gunicorn to the network. The supplied configuration assumes local Nginx terminates TLS, validates/preserves Host (including an explicit port for signed requests), overwrites X-Forwarded-Proto/X-Real-IP and is the only process allowed to reach the application socket.

Django requires secure cookies/CSRF, HTTPS, exact allowed hosts and a strong private key. HSTS initially covers this hostname for one hour without subdomain/preload enrollment; checks W005/W021 are deliberately acknowledged in this profile, while all other deploy warnings still fail installation. Login, registration and agent ingress have distinct edge rate budgets. Successful edge access logs omit query strings; error logs can still contain request details and need restricted access/retention. Proxy real client IP is validated before registration throttling; arbitrary client forwarding headers are not trusted.

Open **https://bearings.circl.lu/** and **https://bearings.circl.lu/admin/** after HTTPS is working.

## 4. Verify and configure before inviting customers

```sh
systemctl --no-pager status bearings-web bearings-worker bearings-national nginx postgresql
journalctl -u bearings-web -u bearings-worker -u bearings-national --since '-10 minutes' --no-pager
/opt/bearings/deploy/ubuntu24/manage.py check --deploy --fail-level WARNING
curl --fail --head https://bearings.circl.lu/accounts/login/
```

A ready service is not proof of functional source access, delivered email or completed risk assessment. National refresh is independent of imports/notifications. Bounded work retains failure states and retries; inspect journal/source health. Server resources, actual provider versions, backup/restore, egress, traffic/registration/ingest quotas and monitoring need acceptance for the intended operational workload. Ubuntu service/package lifecycle must be exercised on the target; local smoke uses equivalent runtime components, not a real LXC PID1 installation.

Configure SMTP, IdP/SSO and operator-owned inventory/intelligence connections deliberately. For a new central NetBox integration, approve the authoritative source/tenant/capability before importing customer data; do not repoint populated source identities. NetBox/Keycloak/FlowIntel/RT/MISP are not provisioned by this installer. This deploys Bearings and its database, not the complete native tool estate. Native permissions/provisioning and SaaS customer lifecycle keep their existing integration boundaries.

Service mail in `/etc/bearings/bearings.env` can be enabled after testing the approved relay:

```text
BEARINGS_SERVICE_MAIL_TRANSPORT=smtp
SMTP_HOST=APPROVED-RELAY
SMTP_PORT=587
SMTP_STARTTLS=1
SMTP_TLS=0
SMTP_USER=APPROVED-ACCOUNT
SMTP_PASSWORD='PRIVATE-RELAY-SECRET'
DJANGO_DEFAULT_FROM_EMAIL=bearings@circl.lu
```

Reload services after protected environment changes. Exercise registration/confirmation/reaction mail on controlled pilot addresses before setting `BEARINGS_PUBLIC_REGISTRATION=1`. Keep it 0 until delivery, company approval/roles, support/privacy and recovery are accepted. Reviewed vulnerability outreach remains a separate `BEARINGS_NOTIFICATION_TRANSPORT` decision; configuring service SMTP does not authorize that transport.

Before customers, configure/accept SSO/MFA and local recovery policies using [SSO operation](sso.md). Bootstrap local login is intentionally retained for recovery. Take encrypted database/config/state backups and perform an isolated restore rehearsal as described in [backup/restore](backup-restore.md). Protect the environment key together with the database; it encrypts personal MISP credentials and changing it blindly loses access.

## Client downloads

The public Linux client page is `/downloads/linux/`. Build reviewed artifacts on a trusted build machine with Go 1.24+ and `scripts/build_linux_client.py`; publish the complete output into `/var/www/bearings/clients` with root-owned directories 0755 and public artifact modes 0644 (executables may be 0755). Production has no implicit source build or unsigned external auto-download. The application can read but not replace that directory; fixed artifact names/checksums/source/license remain required. The generated checksums are not independent code signatures. No compiler is required on monitored clients. See [client/roll-out guide](../integrations/linux-rollout.md).

## Updates and recovery

Use a reviewed/pinned source revision and retain the private environment/database/state. Before upgrading take/verify backups, then stop `bearings-web`, `bearings-worker` and `bearings-national`; fetch/check out the reviewed revision as root. Sync the frozen production extra using `/opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12`, run the management helper's migrate/collectstatic/check commands, reconcile changed unit/proxy templates and restart/check the three services. Do not use the first-install helper for upgrades and do not run developer seed/bootstrap/volume-reset commands on this server. Review pending external writes before worker reactivation after restore or failed/uncertain remote requests; preserve original source IDs and native recovery rules.


### LXC: 502 with systemd `226/NAMESPACE`

If the journal says `Failed to set up mount namespacing: /tmp: Permission denied`, Gunicorn has not started and Nginx cannot find its socket. A root-only sandbox probe can succeed even though the service fails: namespace setup must be checked with an unprivileged user, `NoNewPrivileges=yes` and an empty capability bounding set. The first-install preflight now uses Ubuntu's existing `www-data` account before creating `bearings`; it fails closed without automatically reducing protection.

A successful probe without writable paths is insufficient: `ReadWritePaths` and the writable state-directory exceptions under `ProtectSystem=strict` require additional mount operations. The preflight includes a writable `/var/tmp` exception to exercise this operation without creating application state. A reported plain Ubuntu LXC installation rejected both private temporary mounts and writable state mounts, despite accepting the other flags in a probe without writable paths.

For an existing installation with these confirmed namespace failures, the operator can use the following explicit compatibility override as root. This removes the systemd filesystem mount sandbox for these three services. The application can then write any location its ordinary Unix identity can write; notably application-owned static files lose their read-only mount protection. Root-owned code, environment and client artifacts remain protected by ordinary permissions. The dedicated non-login user, empty capability bounding set, `NoNewPrivileges`, SUID restrictions, private state permissions and outer LXC confinement remain in place. Do not globally disable host AppArmor or make the container privileged.

```sh
mkdir -p /etc/systemd/system/bearings-web.service.d /etc/systemd/system/bearings-worker.service.d /etc/systemd/system/bearings-national.service.d
printf '[Service]\nPrivateTmp=no\nProtectSystem=no\nProtectHome=no\nProtectKernelTunables=no\nProtectKernelModules=no\nProtectControlGroups=no\nReadWritePaths=\n' | tee /etc/systemd/system/bearings-web.service.d/lxc.conf /etc/systemd/system/bearings-worker.service.d/lxc.conf /etc/systemd/system/bearings-national.service.d/lxc.conf
systemctl daemon-reload
systemctl restart bearings-web bearings-worker bearings-national
```

Clearing `ReadWritePaths` is necessary: it can itself request a mount namespace. Fresh installation still requires the default full sandbox; compatibility is not selected silently by the installer. For full inner filesystem isolation, the container host administrator must arrange a suitable reviewed mount-namespace policy, then retest the actual services.

Allow Gunicorn to finish loading before testing HTTP; `systemctl restart` returning and `active` immediately afterwards do not prove the socket is ready. Check again after startup:

```sh
systemctl --no-pager --full status bearings-web bearings-worker bearings-national
journalctl -u bearings-web -u bearings-worker -u bearings-national -n 60 --no-pager
ls -ld /run/bearings /run/bearings/web.sock
curl --fail --head --max-time 15 https://bearings.circl.lu/accounts/login/
```

A persistent 502 needs the current journal and Nginx error, not a reinstall. Preserve the environment, database and state. These drop-ins survive service-template updates. After the container host supports the original sandbox, remove only these `lxc.conf` files, daemon-reload and restart/check the services to restore the full default sandbox.


## Add NetBox, FlowIntel and shared SSO

Use the separate [native ecosystem extension](native-ecosystem.md) for the existing server. It retains Bearings state and installs additional pinned services in stages; do not run the developer stack or repeat the base first installer.

### Request errors in the journal

The production profile writes Django request errors to stderr/systemd even with DEBUG disabled. `journalctl -u bearings-web --since '-10 minutes' --no-pager -n 120` shows status, resolved route, exception types and file/line/function positions. It deliberately omits raw exception messages, request paths/queries/bodies, code text and local variables. Startup-only output from an older profile does not establish that a merge succeeded or failed. Inspect the active/archived organization rows and the `organization.merged` audit before replaying an uncertain merge; never enable DEBUG or log credentials to diagnose it.


### Publish automatic Linux enrollment

After backing up and deploying the reviewed source, run `/opt/bearings/deploy/ubuntu24/manage.py migrate --noinput` for migration 0058, then `python3 deploy/ubuntu24/ecosystem.py prepare-linux-client` and restart the existing Bearings web/worker/national services. Preparation builds both architectures once on the server and activates immutable public download artifacts; monitored hosts never build the client. Preserve the existing private environment, source bindings and LXC service drop-ins. Do not rerun first installation, CIRCL connector setup or mail configuration.

A company administrator then opens `/organizations/COMPANY/agents/fleet/` to issue an expiring/quota-limited rollout key. For a constrained LXC host, the downloaded installer command is `python3 bearings-install.py --server https://YOUR-BEARINGS-HOST --bootstrap-prompt --lxc-compatible`. Deployment jobs use `--bootstrap-stdin` and a secret runner. Self-reported hosts appear in Bearings even with the existing read-only NetBox bridge; there is no per-host native write grant. See [rollout/recovery](../integrations/linux-rollout.md).


### Automatic standard Linux software inventory

Deploy migration 0059 with the normal stop/migrate/restart procedure. No client rebuild or reenrollment is required: the existing protocol already supplies manager, package slot/name, native version, package architecture and host OS/release. After the worker starts, fresh already-applied reports are backfilled automatically in bounded batches; future reports directly create/update separate package software records. Open the asset's Installed software list, or its Linux report page's Open installed software link. Existing manual/CSV records and reviewed version bindings remain separate. See [normalization and distro advisory limits](../integrations/linux-agent.md).

## Public entry point and automatic package CVEs (migration 0060)

The existing HTTPS application serves the multilingual marketing website at `/` for anonymous and authenticated visitors, with same-origin Login and free Registration links. The authenticated infrastructure overview moves to `/infrastructure/`; navigation and post-login destinations use that route. No extra domain, Nginx root replacement or separate static preview server is required. The application source/package must include `website/` and its local assets. Public content contains no inventory. The CIRCL operator text links its statutory role under the Luxembourg law of 5 May 2026 implementing NIS2 and describes scanning/voluntary information sharing; this does not itself activate scanning.

For this upgrade follow the backup/stop/update procedure above and **sync the frozen production dependencies before invoking manage.py**, then migrate (0060), collectstatic, check and restart web/worker/national. The new distro comparator/XML dependencies are required when importing the application. Existing LXC overrides, SMTP settings, sources, SSO identities, manual assessments and private keys are retained. Do not rerun first-install, configure-mail or company connector provisioning.

The existing worker performs automatic supported Ubuntu/Debian/RHEL package CVE evaluation in the background; first vendor cache population can take minutes. Explicit proxy/egress allowlists must permit `security-metadata.canonical.com`, `www.debian.org`, and `security.access.redhat.com`. See [the source/evaluation contract](../integrations/distro-cves.md) for supported releases, coverage limits, error retention and workload bounds. Rebuild/publish the Linux client once with `python3 deploy/ubuntu24/ecosystem.py prepare-linux-client`; updated Debian clients supply exact source-package metadata. Existing Ubuntu reports can already be evaluated. No package-by-package configuration is required.

## Completed management command with a stuck terminal

Native batch management commands now use `systemd-run --wait --collect --pipe`, including when invoked from an SSH terminal. A pseudo-terminal is reserved for interactive `createsuperuser`, `changepassword`, `shell` and `dbshell`; `--noinput` or shell command arguments select pipes. The native ecosystem wrapper applies the same separation to NetBox and uses pipes for non-interactive FlowIntel work. Root-only environment-file validation, systemd parsing, service identity, no-new-privileges and command exit-status propagation remain unchanged.

On an older helper, a `systemd-run --pty` process can remain waiting after its transient service has finished. Inspect `systemctl list-units --all 'run-*.service'` and the identified unit's `Result`, `ExecMainCode`, `ExecMainStatus` and exit timestamp. An inactive unit alone does not prove success; `Result=success` and `ExecMainStatus=0` confirm completion. After confirming the unit is finished, interrupt only the waiting terminal forwarder in its original terminal. Do not start another migration while the original service is active or its result is unknown. On the old helper, append `</dev/null` to batch commands to select pipes; for example `manage.py collectstatic --noinput </dev/null` and `manage.py check </dev/null`. Resume the remaining upgrade steps and check the restarted services. The observed target migration 0060 completed successfully; the hang was its PTY forwarder, not active database work.

## CIRCL corporate theme

Public pages, login/workspace and Django administration share the CIRCL-inspired Raleway/blue/red identity. Font files and the application mark are local static assets with retained font license/provenance. Update source, run `manage.py collectstatic --noinput`, then restart the web process; no theme-specific migration or dependency installation is needed. The marketing stylesheet and updated preview links have a new version suffix so browsers request the new theme. No CSP relaxation, external font host, government crest, authorization change or semantic risk-colour remapping is involved.

## Domain membership codes (migration 0061)

Deploy the reviewed source with the normal backup/stop/migrate/collectstatic/check/restart procedure. Migration 0061 adds reusable company-domain code policy and an optional reference on personal invitations; existing invitations remain valid under their original policy. No new dependency, SMTP policy or SSO/native role provisioning is introduced. The already corrected native helper uses pipes for migration/check/collectstatic; an inactive transient unit with successful exit status is not an active migration.

Company administrators manage codes under `/organizations/COMPANY/members/`; recipients use `/join/domain/` and still verify their individual mailbox. Review the [code/rate/role/revocation contract](../user-guide/company-members.md#shared-code-for-an-exact-email-domain). The invitation UI reports configured SMTP submission instead of a hardcoded local-mail warning. Existing environment banners distinguish reviewed outreach from service mail; enabling registration/invitation SMTP does not enable vulnerability outreach.

## Package association display and registration review diagnostics

This source update has no schema/dependency change beyond existing migrations. Collect static files and restart web **and worker** after updating. The worker recognizes compiler-version changes and recompiles existing public vendor caches even when vendor bytes are unchanged, then queues fresh evaluations. First refresh/parsing/publication runs in the background; package cards show cache/evaluation state and available associations without waiting on vendor requests.

A registration's current applicant membership is checked against its **original registered company**. Missing OrgAdmin membership is an actionable validation error, not a reason to weaken the guard or run a blanket role-restoration SQL update. The review page identifies the exact company, applicant role and permitted membership destinations, with platform-only backend links for explicit correction. No production registration or role is changed by deployment itself. See the registration guide for duplicate-company handling.


### Package-check receipt and map display update (migration 0062)

This update **requires migration 0062**, unlike the earlier label-only inventory patch. Follow the backup/stop/update process above, then run `deploy/ubuntu24/manage.py migrate --noinput`, `collectstatic --noinput` and `check` before restarting web, worker and national services. No dependency change, client rebuild/reinstallation, connector reconfiguration or role update is required. Existing enabled devices are queued by the migration; the worker produces package-check receipts from current reports in bounded batches. Until reevaluation completes the UI shows an unavailable/pending current result, not an inferred clean state. Feed failures and stale inputs retain previous evidence without current-success claims. The map script and general stylesheet URLs are versioned to avoid retaining the older rendering code.
