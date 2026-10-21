# Debian-maintained RT 5 with security patches; native amd64/arm64 packages.
FROM python:3.12-slim-trixie
ARG RT_VERSION=5.0.7+dfsg-4+deb13u3
RUN --mount=type=secret,id=cloud-ca,mode=0444 \
    set -eu; \
    printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod 755 /usr/sbin/policy-rc.d; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; \
    export https_proxy="${HTTPS_PROXY:-}" http_proxy="${HTTP_PROXY:-}"; \
    if [ -f /run/secrets/cloud-ca ]; then export APT_CONFIG=/tmp/cloud-apt.conf; printf 'Acquire::https::CaInfo "/run/secrets/cloud-ca";\n' > "$APT_CONFIG"; fi; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      dbconfig-no-thanks msmtp-mta apache2 libapache2-mod-fcgid libapache2-mod-auth-openidc \
      "rt5-apache2=$RT_VERSION" "rt5-fcgi=$RT_VERSION" "rt5-db-postgresql=$RT_VERSION" \
      "request-tracker5=$RT_VERSION" ca-certificates; \
    a2enmod ssl headers auth_openidc fcgid; a2dissite 000-default; \
    rm -rf /var/lib/apt/lists/* /tmp/cloud-apt.conf; \
    mkdir -p /usr/local/share/request-tracker5/lib/RT/Interface /run/rt-config; \
    printf 'account default\nhost 127.0.0.1\nport 1\n' > /etc/msmtprc
LABEL org.opencontainers.image.source="https://github.com/rommelfs/bearings" \
      org.opencontainers.image.licenses="GPL-2.0-or-later AND AGPL-3.0-or-later" \
      org.opencontainers.image.description="Synthetic Debian RT 5.0.7 security-patched lab; mail stays in local mbox files"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RT_SITE_CONFIG=/adapter/RT_SiteConfig.pm
EXPOSE 443 444
ENTRYPOINT ["python3", "/adapter/start.py"]
