#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# First installation only. No lab seed, external provisioning or public signup.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C.UTF-8
umask 022
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ ${EUID} == 0 ]] || fail 'Run this installer with sudo/root.'
[[ $(cat /proc/1/comm) == systemd ]] || fail 'This path requires a systemd container/host. Docker application containers require host-side orchestration instead; nothing changed.'
# Distribution-provided root-owned metadata.
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || fail 'This installer targets Ubuntu 24.04 only; nothing changed.'
[[ $(realpath "$(dirname "$0")/../..") == /opt/bearings ]] || fail 'Clone the reviewed repository into /opt/bearings first.'
[[ ! -e /etc/bearings/bearings.env ]] || fail 'Environment already initialized. Follow the upgrade/recovery instructions; never regenerate its key.'
[[ ! -e /var/lib/bearings && ! -L /var/lib/bearings && ! -e /var/www/bearings && ! -L /var/www/bearings ]] || fail 'Existing Bearings state/public directories found; review them rather than adopting or resetting data.'
[[ ! -L /opt/bearings && $(stat -c %u /opt/bearings) == 0 ]] || fail '/opt/bearings must be a root-owned checkout, not a symlink.'
[[ ! -e /etc/nginx/sites-available/bearings && ! -L /etc/nginx/sites-enabled/bearings ]] || fail 'Existing Bearings proxy configuration found; review it before first-install automation.'
if getent passwd bearings >/dev/null; then
    fail 'Account bearings already exists. Review the existing installation before first-install automation.'
fi
if getent group bearings >/dev/null; then
    fail 'Group bearings already exists. Review it first.'
fi
systemd-run --quiet --wait --collect --pipe \
  --property=PrivateTmp=yes --property=ProtectSystem=strict --property=ProtectHome=yes \
  --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes --property=ProtectControlGroups=yes \
  /usr/bin/true || fail 'Container does not permit the required systemd sandbox. Review LXC/Incus nesting/mount-namespace policy before installing; protections were not weakened.'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3.12 python3.12-venv ca-certificates curl git postgresql postgresql-client nginx certbot
python3.12 -m venv /opt/bearings-tools
/opt/bearings-tools/bin/python -m pip install --disable-pip-version-check 'uv==0.12.23'
cd /opt/bearings
UV_PYTHON_DOWNLOADS=never /opt/bearings-tools/bin/uv sync --frozen --no-dev --extra production --python /usr/bin/python3.12
useradd --system --user-group --home-dir /var/lib/bearings --shell /usr/sbin/nologin bearings
install -d -o bearings -g www-data -m 0700 /var/lib/bearings
install -d -o bearings -g www-data -m 0755 /var/www/bearings/static
install -d -o root -g root -m 0755 /var/www/bearings/clients /var/lib/letsencrypt
install -d -o root -g root -m 0700 /etc/bearings
systemctl enable --now postgresql
if [[ $(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='bearings'") != 1 ]]; then
    runuser -u postgres -- createuser --no-superuser --no-createdb --no-createrole bearings
else
    fail 'PostgreSQL role bearings already exists; review its privileges before adopting it.'
fi
if [[ $(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='bearings'") == 1 ]]; then
    fail 'Database bearings already exists; no data was modified. Review before adopting it.'
fi
runuser -u postgres -- createdb --owner=bearings bearings
/usr/bin/python3 - <<'PY'
import os,secrets
from pathlib import Path
text=Path('deploy/ubuntu24/bearings.env.example').read_text()
text=text.replace('REPLACE_WITH_A_GENERATED_PRIVATE_SECRET_OF_AT_LEAST_50_CHARACTERS',secrets.token_urlsafe(64))
fd=os.open('/etc/bearings/bearings.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as file:
    file.write(text)
PY
/opt/bearings/deploy/ubuntu24/manage.py migrate --noinput
/opt/bearings/deploy/ubuntu24/manage.py collectstatic --noinput
/opt/bearings/deploy/ubuntu24/manage.py check --deploy --fail-level WARNING
for service in web worker national; do
    install -m 0644 "deploy/ubuntu24/bearings-${service}.service" /etc/systemd/system/
done
# HTTP-01 bootstrap exposes no application; switch to TLS only after certificate issuance.
install -m 0644 deploy/ubuntu24/nginx-http.conf /etc/nginx/sites-available/bearings
ln -s /etc/nginx/sites-available/bearings /etc/nginx/sites-enabled/bearings
if [[ -L /etc/nginx/sites-enabled/default ]]; then rm /etc/nginx/sites-enabled/default; fi
nginx -t
systemctl daemon-reload
systemctl enable --now bearings-web bearings-worker bearings-national nginx
systemctl reload nginx
printf '%s\n' 'Private application installed; HTTP only serves certificate challenges. Next: create admin, provision HTTPS, then configure SMTP/SSO/inventory. See docs/operations/ubuntu24.md.'
