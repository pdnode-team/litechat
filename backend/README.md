# LiteChat Backend

Support-desk API built with [Litestar](https://litestar.dev/) + SQLAlchemy (async) + SQLite/PostgreSQL.

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

The API is served at `http://127.0.0.1:8000`, interactive docs at `http://127.0.0.1:8000/schema`.
Tables are created automatically on startup (no migration step yet — see *Known gaps*).

## Configuration

All configuration is read from environment variables. Nothing is required for local
development, but **the following must be set in production**:

| Variable | Required | Purpose |
|----------|----------|---------|
| `JWT_SECRET_KEY` | **yes in production** | Token signing key. Startup fails in production if unset. |
| `ENVIRONMENT` | recommended | Set to `production` to enable the strict checks below. |
| `DATABASE_URL` | no | Defaults to `sqlite+aiosqlite:///<backend>/litechat.db`. |
| `ALLOWED_ORIGINS` | recommended | Comma-separated CORS allowlist. Defaults to localhost:3000 / :5173. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | no | If both set, an administrator is seeded on startup. |
| `ADMIN_USERNAME`, `ADMIN_NAME` | no | Optional overrides for the seeded administrator. |

In development, if `JWT_SECRET_KEY` is unset, a random key is generated and persisted
to `backend/.jwt_secret` (git-ignored). **Deleting that file invalidates all issued tokens.**

## Creating the first administrator

Public registration always creates a `customer`. An administrator account can only be
created through one of these paths:

1. **From the UI** — on a fresh install the sign-in screen detects an empty database
   (`GET /api/auth/bootstrap-status`) and offers a one-time "Create administrator" form.
   It calls `POST /api/auth/setup-admin`, which is locked as soon as any user exists.
2. **From the CLI**:
   ```bash
   cd backend
   uv run python -m app.cli.create_admin \
     --email admin@example.com --username admin --full-name "System Administrator" \
     --password "changeme123"
   ```
3. **From environment variables** — set `ADMIN_EMAIL` + `ADMIN_PASSWORD` and restart.

The `setup-admin` endpoint is intentionally one-shot: it returns `403` once the user
table is non-empty.

## Tests

```bash
cd backend
uv run pytest
```

`tests/conftest.py` forces an isolated database (`tests/test_isolated.db`) so the suite
never touches your development `litechat.db`.

## Project layout

```
app/
  main.py              # Litestar app, CORS, static uploads, startup hooks
  config.py            # Env parsing, JWT secret resolution, SLA tables
  cli/create_admin.py  # Administrator bootstrap script
  controllers/         # REST + WebSocket route handlers (one module per resource)
  services/            # auth (bcrypt/JWT), SLA calculation, WebSocket hub
  models/              # SQLAlchemy ORM models
  schemas/             # Pydantic request/response models
  db/                  # Engine/session, declarative base, env seeding
tests/                 # pytest suite (DB-isolated)
uploads/               # Uploaded attachments (git-ignored)
```

## Authentication & roles

- `POST /api/auth/register` → `customer`
- `POST /api/auth/setup-admin` → `admin`, only while the user table is empty
- `POST /api/auth/login` → bearer token (7 day expiry)
- `GET  /api/auth/me`

Roles are `customer` / `agent` / `admin`. Clients send `Authorization: Bearer <token>`.
WebSocket connections (`/ws/tickets/{id}?token=...`) use the same token.

## Known gaps

- **No migrations.** Schema changes are applied with `create_all` only; introducing
  Alembic is the next infrastructure step.
- Timestamps are stored as UTC but serialized without an explicit timezone offset.
  Clients must interpret them as UTC.
- No pagination on list endpoints, no rate limiting, no password reset flow.
