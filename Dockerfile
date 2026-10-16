FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
# Optional cloud CA mount is a public trust bundle, never a credential or permanent image layer.
RUN --mount=type=secret,id=cloud-ca \
    if [ -f /run/secrets/cloud-ca ]; then export SSL_CERT_FILE=/run/secrets/cloud-ca UV_SYSTEM_CERTS=true; fi; \
    uv sync --frozen --no-dev
COPY config ./config
COPY portal ./portal
COPY manage.py ./
RUN useradd --create-home bearings && mkdir -p /app/.local && chown -R bearings:bearings /app
USER bearings
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-dev --frozen python manage.py migrate && uv run --no-dev --frozen python manage.py runserver 0.0.0.0:8000"]
