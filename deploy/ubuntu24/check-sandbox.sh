#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Non-mutating preflight: the application account does not exist yet. Ubuntu's
# www-data identity exercises unprivileged namespace setup before installing.
set -euo pipefail
systemd-run --quiet --wait --collect --pipe \
  --property=User=www-data --property=Group=www-data \
  --property=NoNewPrivileges=yes --property=CapabilityBoundingSet= \
  --property=ReadWritePaths=/var/tmp \
  --property=PrivateTmp=yes --property=ProtectSystem=strict --property=ProtectHome=yes \
  --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes --property=ProtectControlGroups=yes \
  /usr/bin/true
