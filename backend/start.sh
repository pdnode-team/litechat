#!/bin/sh
# Container start command for the backend (see nixpacks.toml).
#
# Migrations run first so a broken schema stops the deploy instead of starting
# an API that cannot use its own database.
set -e

# Work from the directory this script lives in. The build context may be the
# repository root or the backend folder, depending on how the platform sets up
# the app, and `alembic.ini` / `app/` are resolved relative to the project root.
cd "$(dirname "$0")"

# --no-sync: dependencies were installed at build time, so do not re-resolve
# them at startup (faster boot, and no network needed).
echo "[start] applying database migrations..."
uv run --no-sync alembic upgrade head

echo "[start] launching API on port ${PORT:-8000}"
exec uv run --no-sync uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips '*'
