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
