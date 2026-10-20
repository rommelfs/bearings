#!/bin/bash
set -eu
export KC_BOOTSTRAP_ADMIN_USERNAME=sso-admin
export KC_BOOTSTRAP_ADMIN_PASSWORD="$(cat /run/credentials/bootstrap_password)"
exec /opt/keycloak/bin/kc.sh start-dev --import-realm --hostname "$BEARINGS_SSO_PUBLIC_URL" --proxy-headers xforwarded
