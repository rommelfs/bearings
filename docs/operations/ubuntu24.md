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

Record/review that source revision; the development branch moves. The helper installs Python 3.12, pinned uv, frozen production dependencies, PostgreSQL, Nginx and Certbot. It creates the dedicated non-login `bearings` account/database role/database, root-owned mode-0600 `/etc/bearings/bearings.env` with a newly generated random secret, `/var/lib/bearings` private state and public static/client directories. It runs committed migrations, static collection and deploy checks, prepares both client downloads, then enables web/worker/national services. Dependencies/source remain root-owned; the application can write only its state/runtime directories.

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

The native installer prepares both download pages, `/downloads/linux/` and
`/downloads/windows/`. On the existing Ubuntu server, use the same publisher
to refresh both clients from the clean, reviewed checkout:

```sh
cd /opt/bearings
python3 deploy/ubuntu24/ecosystem.py prepare-clients
```

The command uses a checksum-pinned Go compiler, builds Linux amd64/arm64
and Windows x64/ARM64/x86 packages, and prepares the checksums and corresponding
source. The Windows EXEs embed the approved HTTPS origin from `BEARINGS_PUBLIC_URL`.
Apply the current portal migrations before registering Windows clients. Both clients accept the same limited rollout keys. Build egress includes `go.dev` and its Go archive host, plus
`proxy.golang.org` and `sum.golang.org` for locked Windows module dependencies.
The command switches both paths together in the protected Bearings environment
after both builds finish and restarts the web service. Prior release directories
are retained. The earlier `prepare-linux-client` command is an alias for the
same publisher. For a maintenance window with an explicit service start,
use `prepare-clients --no-restart`.

The managed release contains all the ZIPs, checksums and source. It is writable
only by the operator. The portal serves allowlisted files and checks the
corresponding SHA-256 value before serving each package. Windows packages are
unsigned reference builds. Package publishing is separate from approving,
enrolling and updating individual devices. See the
[Linux rollout guide](../integrations/linux-rollout.md) and
[Windows setup guide](../../clients/windows/README.md).

## Updates and recovery

Use a reviewed/pinned source revision and retain the private environment/database/state. Before upgrading take/verify backups, then stop `bearings-web`, `bearings-worker` and `bearings-national`; fetch/check out the reviewed revision as root. Sync the frozen production extra using `/opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12`, run the management helper's migrate/collectstatic/check commands, run `python3 deploy/ubuntu24/ecosystem.py prepare-clients --no-restart`, reconcile changed unit/proxy templates and restart/check the three services. Do not use the first-install helper for upgrades and do not run developer seed/bootstrap/volume-reset commands on this server. Review pending external writes before worker reactivation after restore or failed/uncertain remote requests; preserve original source IDs and native recovery rules.

### Windows inventory upgrade from `6acb4c8`

Use the reviewed Windows inventory revision that includes `6acb4c8`. The
upgrade adds migration `0073_windows_inventory` and retains the host overview.
The frozen dependencies and native service configuration match `6acb4c8`.

After verifying the backup, run the following as root from the existing
`/opt/bearings` checkout. Replace `REVIEWED_WINDOWS_COMMIT` with the reviewed
commit ID. The preflight checks the current revision and rejects local changes
before stopping the services.

```sh
set -eu
cd /opt/bearings
reviewed=REVIEWED_WINDOWS_COMMIT
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = 6acb4c85ed52ca3fba2588da7d2dda329308b973
git fetch origin refs/heads/codex/windows-inventory-client
git merge-base --is-ancestor HEAD "$reviewed"
systemctl stop bearings-web bearings-worker bearings-national
git switch --detach "$reviewed"
/opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12
./deploy/ubuntu24/manage.py migrate --noinput </dev/null
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
./deploy/ubuntu24/manage.py check </dev/null
python3 deploy/ubuntu24/ecosystem.py prepare-clients --no-restart
systemctl start bearings-web bearings-worker bearings-national
systemctl is-active bearings-web bearings-worker bearings-national
```

Confirm the public HTTPS portal opens and the company's **Linux / Windows
inventory reports** page is available. Enrollment uses the approved HTTPS
origin in `BEARINGS_PUBLIC_URL`. Follow the [Windows client guide](../../clients/windows/README.md)
for setup, existing-asset enrollment and periodic reports.


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


### Enable managed CIRCL NetBox registration (migration 0063)

The previous pilot is intentionally read-only. To register the existing LXC host as a NetBox VM with an `lxc` tag and enable managed registration for new rollout codes, follow [the staged plan, apply and bidirectional verification](managed-netbox.md). Migration 0063 adds explicit managed policy and virtualization metadata without changing client protocol, source identity or existing rollout authorization. Existing rollout codes stay observed-only. Do not rerun first-install or repoint the source. Host IP declarations and software/CVE records remain in Bearings; a physical host/cluster is not inferred.


The extended NetBox inventory exporter requires **migration 0064** and web/worker restart. It is opt-in per source; native extension is `manage-circl-inventory --export-inventory --apply`. Recurring network observations require the updated Linux binary, published through the existing verified central release workflow after server upgrade. Do not rebuild artifacts from a dirty source checkout. See [export activation and customer-owned RW](managed-netbox.md#reported-inventory-export-migration-0064).


## Security dependency upgrade — 21 November 2026

The reviewed security/UI update changes frozen Python dependencies and the social-auth Django schema. Back up databases and protected configuration. Stop Bearings web/worker/national, run `uv sync --frozen --no-dev --extra production` from `/opt/bearings`, then use the protected management wrapper for `migrate --noinput`, `collectstatic --noinput` and `check` before starting services. Do not run old Python environments against newly checked-out authentication code. In-flight OIDC logins may need to restart. Existing explicit digest bindings, roles and local passwords are preserved.

Native NetBox/FlowIntel have separate environments. With their applications/workers stopped, sync `/opt/bearings-services/netbox/.venv/bin/python` from `deploy/ubuntu24/ecosystem/netbox-requirements.txt` and `/opt/bearings-services/flowintel/.venv/bin/python` from `docker/flowintel/requirements.txt` using `uv pip sync --python PATH --require-hashes FILE`. The source-controlled native configuration must load `SOCIAL_AUTH_OLD_ID_KEYS = {"oidc": None}` before NetBox's social-auth data migration. Use `python3 deploy/ubuntu24/ecosystem.py manage netbox migrate --noinput`, then the corresponding `collectstatic --noinput` and `check` commands; restart `bearings-netbox`, `bearings-netbox-worker` and `bearings-flowintel`. Do not rerun first install, connector provisioning, SSO identity linking, realm import or mail setup. This upgrade adds no NetBox API rights and changes no retained credentials.

Rebuild reviewed container images when using Docker; updating host files/venvs does not patch existing image packages. See [audit scope, evidence and remaining work](../audits/2026-11-21-ui-security.md).


### Group NetBox addresses with their machine

Migration 0065 adds a nullable imported address-to-host relation. Use the normal
backup/stop/frozen-sync/migrate/collectstatic/check/restart procedure above. Then
run `./deploy/ubuntu24/manage.py sync_netbox --source SOURCE_UUID` for the reviewed
source (GET-only), or request the existing company inventory refresh. This backfills
relations from NetBox's actual interface assignments. **01 / Inventory & software**
shows one host card with its assigned IPv4/IPv6 records; previous address identities,
software and assessments remain accessible. No client reinstall or new enrollment is
needed. See [grouping and uncertainty](managed-netbox.md#one-machine-card-with-assigned-addresses-migration-0065).

Organization administrators and platform superusers can open **Company members &
invitations → Company email domain codes** directly from the company page. The
reusable domain code itself is shown once when created; retained records show its
domain, role, expiry/quota and revocation controls, not the original secret.


### Overview package-monitoring and empty-workspace cleanup

This read-only UI/aggregation update introduces no additional migration after 0065.
Use the normal frozen upgrade, run migrations/static collection/checks, then restart
`bearings-web`, `bearings-worker` and `bearings-national`. If 0065's address relations
have not been populated yet, run a complete scoped `sync_netbox --source SOURCE_UUID`
so assigned IP records can be counted under their host. No Linux client rebuild or
new enrollment is required for this overview update.

Distribution package identities are shown independently of manufacturer/product
watches. Device evaluation timestamps are explicitly recorded attempts, not proof
of current package/feed coverage; follow the matching/coverage link for current
receipts. Paused/failed/manual watches retain their separate status. Organizations
with no inventory, reviews, actions or risk assessments appear under **Workspaces
awaiting inventory**. Search/direct selection opens them normally, and a participant
with only an empty workspace sees that setup section expanded. This is presentation,
not a company merge or deletion; review memberships and the existing merge preview
before consolidating actual duplicate registrations.


### Inventory directory and repeated reviewed consolidation

This follow-up has no new dependency or database migration after 0065. Deploy the
reviewed revision with the normal backup/frozen-sync/migrate/collectstatic/check
procedure, then restart `bearings-web`, `bearings-worker` and `bearings-national`.
Run a scoped full `sync_netbox --source SOURCE_UUID` if address relationships still
need backfilling. No Linux client rebuild or native NetBox/SSO service restart is
required for these directory/merge changes.

The inventory directory now uses the same explicit host/address counts as company
inventory and shows pending workspaces compactly, preserving contacts and search
access. Platform-only consolidation links preselect only the source. The merge
preview lists every incoming resulting membership role. A target's earlier archives
no longer prevent receiving another independently reviewed registration; source
archive chains remain blocked. Existing previews must be recreated after this
merge-policy update. No production organizations are merged by deployment.


### Upgrade package/CVE evaluation semantics

Update the reviewed checkout, run `./deploy/ubuntu24/manage.py check` and restart
`bearings-web bearings-worker bearings-national`. No migration, dependency sync,
client rebuild or client restart is required by this change. The new worker
automatically requeues fresh inventories and recompiles supported cached vendor
feeds once (compiler version 3, receipt/evaluator version 2). This can take several
minutes for a large Ubuntu feed; it runs in the background. Old proofs are marked
awaiting evaluation meanwhile. Failed refreshes retain prior evidence and retry
under existing bounded policy; they do not imply fixed or unaffected packages.

Expected regression result for Ubuntu 24.04 / python3-pip-whl
24.0+dfsg-1ubuntu1.3 / CVE-2026-97688, using the vendor state reviewed on
21 November 2026: **unresolved**, because Ubuntu supplies only package presence
and records python-pip as needs-triage. When Ubuntu supplies a version predicate,
the normal feed refresh will reevaluate it. No special-case CVE override exists.
See [the primary-source audit](../audits/2026-11-21-package-cve-correctness.md).

Review queue classification follow-up: update to the reviewed commit and restart
`bearings-web bearings-worker bearings-national`. No migration, client rebuild,
new dependencies, or static collection is needed for this template/query change.
The queue separates current affected package versions, vendor uncertainty,
pending reevaluations and retained fixed/assessed reviews. After deployment,
check `/reviews/` and the status tabs; historical review counts must not be
interpreted as the current affected-version count. Existing worker reevaluation
refreshes proof when inventory, vendor rules or evaluator inputs change.

Pip/ESM update explanation and separate CVSS/priority badges: after updating,
run `./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null` and restart
`bearings-web`. No migration, dependency synchronization or client update is
needed. The interface performs no APT/probe calls; vendor-listed ESM fixes are
not evidence of local subscription status or installable candidates. Use
read-only `apt-cache policy python3-pip-whl` and `pro status` on the affected
host to investigate those separately. This change does not enable subscriptions
or install the reported package update.

Software-entry public catalog picker / MISP mapping: update the reviewed
checkout, run `./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null`
and restart `bearings-web bearings-worker bearings-national` so web templates,
picker JavaScript and background exact-name enrollment use the same code.
No migration, dependency or client binary update is required. Searches reuse
the existing operator-approved Vulnerability-Lookup source and bounded HTTP
contract; no full CPE dictionary is downloaded into the application database.

### Configurable application client profiles and context navigation

Apply migration `0066_application_manifest_observations` before restarting the
web/worker processes or distributing the new client. Existing clients continue
reporting without the optional application section. From the reviewed checkout:

```sh
./deploy/ubuntu24/manage.py migrate --noinput </dev/null
./deploy/ubuntu24/manage.py check </dev/null
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
systemctl restart bearings-web bearings-worker bearings-national
python3 deploy/ubuntu24/ecosystem.py prepare-linux-client
```

Publication requires a clean tracked checkout; keep downloaded installers outside
`/opt/bearings`. On each already enrolled client, download to `/root` and update
without a bootstrap code:

```sh
cd /root &&
curl --fail --show-error --proto '=https' \
  https://bearings.circl.lu/downloads/linux/install.py -o bearings-install.py &&
python3 bearings-install.py --server https://bearings.circl.lu
```

The installer retains existing identity/state and reviewed drop-ins and restarts
the service. Check `bearings-linux version` and `systemctl status bearings-linux`.
The normal watcher includes local application profiles at its next jittered
capture. Local profile changes are read each capture; restarting bearings-linux
brings the next attempt forward. The built-in MISP profile reads only its release file; generic profiles must
not target secret-bearing configuration. No filesystem privileges are granted
automatically. Configuration and minimal metadata permissions must
be managed locally, independently of tenant UI permissions. See the
[application profile reference](../integrations/linux-application-probes.md).


The company-admin profile editor at `/organizations/<slug>/agents/profiles/`
requires the newly published native client's `validate-applications` command;
`prepare-linux-client` above is required even when only authoring profiles in the
browser. Run static collection for `application-profile-editor.js` and restart
web/worker/national as shown. The editor validates syntax only, exports local JSON
or a PR proposal ZIP and never distributes profiles or contacts GitHub. It adds
no migration beyond 0066. Existing monitored hosts need the client update above
to collect generic profiles. Keep keys/state and local sandbox drop-ins intact.


### Opt-in automatic Linux client updates

Publish the new reviewed installer with
`python3 deploy/ubuntu24/ecosystem.py prepare-linux-client` from a clean checkout. Restart `bearings-web` for the updated
installation instructions; no migration/dependency change is added. On each
already enrolled host, download the installer outside `/opt/bearings` and run
`python3 bearings-install.py auto-update-enable --server https://bearings.circl.lu`.
The timer checks daily with jitter; unchanged releases avoid binary download and
restart. Recovery, quarantine, status/disable commands, trust boundaries and
refreshing the local updater are documented in [Linux client updates](linux-client-updates.md).
Existing clients are not silently enrolled in automatic updates.

### Vitrine map and presentation components

The national map and manual company-position editor use pinned, locally served
Vitrine components. CIRCL XYZ background tiles default to
`https://geo.circl.lu/hot/{z}/{x}/{y}.png`. Set `BEARINGS_MAP_TILE_URL=` for a
local-geometry-only map. Only the viewed map area reaches the tile service;
company data and local GeoNames address lookup remain within Bearings.
See [map behavior and attribution](../user-guide/circl-map.md).

After checking out the reviewed release on `/opt/bearings`:

```sh
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
systemctl restart bearings-web
```

No migration, worker restart, client rebuild or client restart is needed for this
presentation change. Existing Linux inventory collection is unaffected. Refresh
the browser for the new module. npm is a maintainer-only vendoring dependency;
production uses committed artifacts and their retained third-party notices.

### Retained daily indicator history

Migration `0067_national_daily_snapshots` adds forward-only daily per-company
review/inventory/coverage observations and PostgreSQL policy-generation guards.
The existing national worker samples clean summaries normally hourly, preserving
the latest observation per day. This is separate from rebuildable national cache
rows: do not include the history/policy tables in cache-reset procedures. No
upstream reads, writes, notifications or client-side deployment are introduced.

After checking out the reviewed release, run migration, static collection and a
bounded first capture before restarting both web and national worker:

```sh
./deploy/ubuntu24/manage.py migrate --noinput </dev/null
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
./deploy/ubuntu24/manage.py refresh_national --limit 500 </dev/null
systemctl restart bearings-web bearings-national
```

The ordinary worker and Linux clients need no restart for this feature. Captures
begin after update; no historical totals are invented. See [history semantics and
permission changes](../user-guide/national-indicator-history.md). Existing
observations survive failures/rebuilds; retain them in backups. Production capture
requires PostgreSQL; SQLite deliberately does not record unguarded history.

### Machine-based indicators and attention overview (23 November 2026)

This increment changes server-side presentation/queries and forward daily history capture. It needs no new migration, dependency sync, client rebuild or static asset collection; existing migration 0072 is required. Deploy the reviewed pinned commit using the existing protected environment and management helper, check migration consistency, then restart **bearings-web, bearings-worker and bearings-national**. Do not rerun first installation or alter client enrollment. Hourly national history capture automatically adds the new machine-metric contract, replacing today's older observation when needed. Older dates are not backfilled from raw reviews. Current machine indicators read scoped live evidence; no wait for historical data is needed for the current dashboard.
