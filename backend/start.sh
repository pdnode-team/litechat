#!/bin/sh
# Container start command for the backend (see nixpacks.toml).
#
# Migrations run first so a broken schema stops the deploy instead of starting
# an API that cannot use its own database.
set -e

echo "[start] applying database migrations..."
uv run alembic upgrade head

echo "[start] launching API on port ${PORT:-8000}"
exec uv run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips '*'
