# Case-workflow lab build of upstream FlowIntel, not the full PDF/AI/analyzer distribution.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
WORKDIR /home/flowintel/app
COPY docker/flowintel/requirements.txt /tmp/flowintel-requirements.txt
RUN --mount=type=secret,id=cloud-ca \
    if [ -f /run/secrets/cloud-ca ]; then export SSL_CERT_FILE=/run/secrets/cloud-ca UV_SYSTEM_CERTS=true; fi; \
    uv venv /home/flowintel/venv && \
    uv pip install --python /home/flowintel/venv/bin/python --require-hashes -r /tmp/flowintel-requirements.txt
COPY --from=flowintel / /home/flowintel/app/
# Upstream intentionally excludes conf/** from its root Docker context.
COPY --from=flowintel-conf /config.py.default /config_module.py.default /home/flowintel/app/conf/
RUN rm -rf .git && \
    groupadd --gid 10000 flowintel && useradd --uid 10000 --gid 10000 --create-home flowintel && \
    mkdir -p logs history uploads && chown -R 10000:0 /home/flowintel/app
LABEL org.opencontainers.image.source="https://github.com/flowintel/flowintel" \
      org.opencontainers.image.revision="0fd54db3d3c7d17c4b26d8759cb6ac857d8d041f" \
      org.opencontainers.image.licenses="AGPL-3.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10000:0
EXPOSE 7006
