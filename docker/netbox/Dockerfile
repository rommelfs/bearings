# Retain the exact upstream application and entrypoint; patch reviewed Python packages only.
FROM netboxcommunity/netbox:v4.7.3-5.1.1@sha256:1d6e0b5fbd48da9868376900561ee55992e04446ce7861dab5e9a42ae01f3fcb
USER root
COPY docker/netbox/security-requirements.txt /tmp/bearings-netbox-security-requirements.txt
RUN --mount=type=secret,id=build_ca,target=/tmp/bearings-build-ca.pem \
    if [ -f /tmp/bearings-build-ca.pem ]; then export SSL_CERT_FILE=/tmp/bearings-build-ca.pem; fi; \
    /usr/local/bin/uv pip install --python /opt/netbox/venv/bin/python \
    --require-hashes --no-deps --no-cache -r /tmp/bearings-netbox-security-requirements.txt \
    && /usr/local/bin/uv pip check --python /opt/netbox/venv/bin/python \
    && rm /tmp/bearings-netbox-security-requirements.txt
USER netbox
