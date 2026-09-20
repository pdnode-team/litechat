# LiteChat Backend

Support-desk API built with [Litestar](https://litestar.dev/) + SQLAlchemy (async) + SQLite/PostgreSQL.

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
cd backend
uv sync
cp .env.example .env          # optional; review the values
uv run alembic upgrade head   # create/update the schema
uv run uvicorn app.main:app --reload --port 8000
```

The API is served at `http://127.0.0.1:8000`. Interactive docs live at
`http://127.0.0.1:8000/schema` (disabled in production unless `ENABLE_API_DOCS=true`).

On startup the app also runs `create_all`, which keeps a fresh local database working
without migrations. **Schema changes must go through Alembic** — see *Database migrations*.

## Configuration

All configuration is read from environment variables. See `.env.example` for the full
annotated list. The essentials:

| Variable | Required | Purpose |
|----------|----------|---------|
| `JWT_SECRET_KEY` | **yes in production** | Token signing key. Startup fails in production if unset. |
| `ENVIRONMENT` | recommended | `production` enables the strict checks. |
| `DATABASE_URL` | no | Defaults to `sqlite+aiosqlite:///<backend>/litechat.db`. |
| `ALLOWED_ORIGINS` | recommended | Comma-separated CORS allowlist. Defaults to localhost:3000 / :5173. |
| `PUBLIC_APP_URL` | recommended | Frontend base URL used in emailed links. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | no | If both set, an administrator is seeded on startup. |
| `SMTP_*` | no | Without `SMTP_HOST`, outbound email is logged instead of sent. |
| `RATE_LIMIT_*` | no | Per-IP limits on the credential endpoints. |
| `LOG_LEVEL` | no | Root log level, default `INFO`. |
| `LOG_FILE` | no | Mirror the log into a rotating file (stdout is the default sink). |

In development, if `JWT_SECRET_KEY` is unset, a random key is generated and persisted
to `backend/.jwt_secret` (git-ignored). **Deleting that file invalidates all issued tokens.**

## Database migrations

Alembic is configured for the async engine and reads `DATABASE_URL` from the app config,
so migrations always target the same database the app uses.

```bash
uv run alembic upgrade head                       # apply everything
uv run alembic revision --autogenerate -m "..."   # after changing a model
uv run alembic check                              # fail if models drift from migrations
uv run alembic downgrade -1                       # roll back one revision
```

SQLite cannot `ALTER` most columns in place, so `env.py` enables batch mode and those
migrations are rewritten as create/copy/drop. Migrations that add a `NOT NULL` column to
a populated table must supply a `server_default` and backfill — see
`migrations/versions/*_add_auth_tokens_and_email_verification.py` for the pattern.

## Realtime

Two WebSocket channels, both authenticated with the same bearer token
(`?token=...`) and resolved against the database rather than the token claims,
so a role change takes effect immediately:

| Channel | Purpose |
|---------|---------|
| `/ws/tickets/{id}` | One conversation: `new_message`, `typing`, `ticket_updated` |
| `/ws/notifications` | Account-wide: everything else the user may see |

The notification channel puts a connection into rooms by role — the user's own
room, plus `staff` (agent/admin) and `admin` (admin) — and sends a `ready` frame
listing the subscribed rooms.

Event types published by `app/services/events.py`:

| Type | Sent to | Triggered by |
|------|---------|--------------|
| `ticket_created` | staff + the owning customer | ticket opened |
| `ticket_updated` | customer, assignee, staff | status / priority / assignment / detail edit |
| `message_created` | participants + staff | public reply (whispers exclude customers) |
| `csat_submitted` | customer, assignee, staff | satisfaction rating |
| `user_updated` | the affected user + admins | role or activation change |
| `catalog_changed` | staff + admins | apps / ticket types / FAQ / macros CRUD |
| `rate_limited` | the throttled user | credential endpoint limit hit |

Routing lives in one place: controllers call `events.publish(...)` and the
service decides which rooms and which emails an event maps to. A connection is
never sent the same event twice, even when it belongs to several matching rooms.

The conversation channel only appends messages it is told about, so a
`ticket_updated` frame for a status/priority/assignment change **also carries the
action card that change wrote** (`ticket_updated.message`). Without it the
"Ticket status changed from … to …" bubble appeared only after a manual reload.

## Email notifications

Sent for: a new ticket (all active staff), a public staff reply (the customer),
a customer reply (the assignee, or all staff when unassigned), assignment (the
new assignee) and resolve/close (the customer). **Internal notes never generate
email.**

Both email and notification behaviour are configurable at runtime from the admin
UI (Admin console → *Email & Alerts*), and the values are stored in the
`app_settings` table. Environment variables remain the fallback for anything an
administrator has not saved, so an existing deployment keeps working unchanged.

`GET/PUT /api/settings`, `PUT /api/settings/email`,
`PUT /api/settings/notifications` and `POST /api/settings/email/test` are
administrator-only. The SMTP password is stored encrypted (key derived from
`JWT_SECRET_KEY`) and is never returned by the API — only `smtp_password_set`.

If `smtp_host` is unset, outbound mail is written to the application log
instead, so password-reset links stay usable in development.

## Pagination

Every list endpoint returns a page envelope instead of a bare array:

```json
{ "items": [], "total": 0, "limit": 50, "offset": 0 }
```

`limit` defaults to 50 (max 200) and `offset` to 0; out-of-range values are rejected with
400. `GET /api/tickets/{id}/messages` is special: **page 0 holds the newest messages**,
and each page is still returned in chronological order so older pages can be prepended
directly.

## Dynamic ticket forms

A ticket type owns a JSON array of field definitions (`ticket_types.fields_schema_json`).
The same definition drives three things that must stay in agreement:

1. the admin builder (`frontend/src/components/admin/CustomFieldBuilder.tsx`),
2. the customer form (`frontend/src/components/customer/CreateTicketModal.tsx`),
3. `app/services/form_logic.py` — the **authoritative** validation.

The browser copy in `frontend/src/utils/formLogic.ts` exists only to give immediate
feedback; the client can be bypassed, so every rule is enforced again on the server. When
a rule changes in one implementation, change it in the other.

A field can declare:

| Attribute | Meaning |
|-----------|---------|
| `type` | `text`, `textarea`, `select`, `multi_select`, `number`, `switch`, `url`, `date` |
| `required`, `required_when` | Always mandatory, or mandatory only while a condition holds |
| `visible_when` | The question is hidden (and its answer discarded) unless the condition holds |
| `options`, `allow_other`, `other_label` | Choices for `select`/`multi_select`, plus a free-text "Other" |
| `min_length`, `max_length`, `pattern` | Text constraints; `pattern` must match the **whole** value |
| `min_value`, `max_value` | Numeric range |
| `error_message` | Replaces the generated wording of a length/format/range failure |
| `help_text`, `placeholder` | Presentation |

Conditions are `{ logic: "all" | "any", conditions: [{ field, operator, value }] }`, where
`operator` is one of `equals`, `not_equals`, `contains`, `not_contains`, `in`, `not_in`,
`is_answered`, `is_empty`, `gt`, `gte`, `lt`, `lte`. A group may hold any number of
conditions; the admin builder edits them one row at a time and switches the group between
"match all" and "match any". A condition may only reference a field defined **above** the
field that declares it; that is what makes a single forward pass sufficient and stops
circular rules. `validate_field_schema()` rejects duplicates, unknown references, self
references and forward references before a schema is stored.

Consequences worth knowing:

- Answers to hidden questions are **dropped**, not stored, so a tampered client cannot
  smuggle an answer for a question it was never shown.
- `multiselect` answers are JSON arrays; everything else is a scalar.
- Empty answers are omitted rather than stored as empty strings.
- The whole submission is capped at 32 KB and 50 custom fields.

## Errors and logging

Every rejected input is answered with the same body, so a form can attach each message to
the input that caused it:

```json
{
  "status_code": 422,
  "detail": "3 problems need your attention.",
  "errors": [
    { "field": "title", "label": "Ticket Subject", "message": "...", "code": "too_short" },
    { "field": "custom_fields.severity", "label": "Severity", "message": "...", "code": "required" }
  ]
}
```

`field` is the dotted path of the offending input (`title`, `custom_fields.<key>`),
`code` is a machine readable reason. Litestar's own request-schema failures (status 400)
are normalised into the same shape.

Every response carries an `X-Request-ID` header; a client-supplied id is reused when it
looks like an id. A `500` is logged with a full traceback, the method, the route, the
caller and that request id, and the body repeats the id as a reference. **The request body
is deliberately never logged** — it may contain a password or a reset token.

Values are also checked against the length of the column that stores them (`String(n)`) on
every admin catalogue, and a duplicate on a unique `code`/`shortcut` column is answered as a
field error. Both used to surface as an opaque 500 on PostgreSQL — a
`StringDataRightTruncation` for an over-long value, a `UniqueViolation` for a duplicate —
while SQLite accepted them happily, so neither ever showed up in development.

One failure is deliberately *not* translated: a primary-key collision
(`... unique constraint "managed_apps_pkey"`). That means the id sequence drifted out of
sync with its table, usually after importing a dump, and answering "this code already
exists" would send the operator chasing the wrong thing. It stays a logged 500, and the fix
is to resynchronise the sequence:

```sql
SELECT setval(pg_get_serial_sequence('managed_apps','id'),
              COALESCE((SELECT MAX(id) FROM managed_apps), 1));
```

## Rate limiting

Credential endpoints are limited per client IP (in-process sliding window): login,
register, setup-admin, forgot-password and reset-password. Exceeding a limit returns
`429` with a `Retry-After` header. The store is per process — running multiple workers or
replicas requires a shared store (e.g. Redis) to enforce the limits globally.

## Password reset and email verification

- `POST /api/auth/forgot-password` — always `202`, so it cannot be used to discover which
  addresses have accounts. Issues a single-use, hashed, expiring token and emails a link.
- `POST /api/auth/reset-password` — consumes the token and sets the new password.
- `POST /api/auth/verify-email` — consumes a verification token.
- `POST /api/auth/resend-verification` — authenticated; re-sends if still unverified.
- `POST /api/auth/change-password` — authenticated; requires the current password.

Email verification is **advisory**: an unverified account can still sign in and simply
sees a banner prompting confirmation. This avoids locking anyone out of an existing
deployment. Password reset does not revoke already-issued JWTs (there is no revocation
store yet), so a stolen token stays valid until it expires.

Emails are delivered over SMTP when `SMTP_HOST` is set, otherwise they are written to the
application log — reset links remain usable in development without a mail server.

## Testing

```bash
uv run pytest
```

`tests/conftest.py` forces an isolated database (`tests/test_isolated.db`) and disables the
rate limiter, so the suite never touches your development `litechat.db`.

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

## Project layout

```
app/
  main.py              # Litestar app, CORS, static uploads, startup hooks
  config.py            # Env parsing, JWT secret resolution, SLA tables, limits
  logging_config.py    # Logging setup, request-id context, record factory
  exception_handlers.py# Uniform validation 4xx payloads + logged, referenced 500s
  exceptions.py        # FormValidationError (a 422 carrying per-field messages)
  cli/create_admin.py  # Administrator bootstrap script
  controllers/         # REST + WebSocket route handlers (one module per resource)
  middleware/          # ASGI middleware (request id/access log, rate limiting)
  services/            # auth, SLA, WebSocket hub, tokens, email, form_logic
  models/              # SQLAlchemy ORM models
  schemas/             # Pydantic request/response models (+ pagination primitives)
  db/                  # Engine/session, declarative base, env seeding
migrations/            # Alembic environment and revisions
tests/                 # pytest suite (DB-isolated)
uploads/               # Uploaded attachments (git-ignored)
```

## Authentication & roles

- `POST /api/auth/register` → `customer`
- `POST /api/auth/setup-admin` → `admin`, only while the user table is empty
- `POST /api/auth/login` → bearer token (7 day expiry)
- `GET  /api/auth/me`
- `POST /api/auth/forgot-password`, `/reset-password`, `/verify-email`,
  `/resend-verification`, `/change-password`

Roles are `customer` / `agent` / `admin`. Clients send `Authorization: Bearer <token>`.
WebSocket connections (`/ws/tickets/{id}?token=...`) use the same token.
`GET /api/users` is administrator-only; `GET /api/users/assignable` lists active staff for
the reassignment picker and is available to agents.

## Known gaps

- **Timestamps are stored as UTC but serialized without a timezone offset.** Clients must
  interpret them as UTC (the frontend does this in `src/utils/datetime.ts`).
- **No token revocation.** Password reset and logout do not invalidate already-issued
  JWTs; they stay valid until they expire.
- **The rate limiter is per process.** Multiple workers need a shared store.
- **Realtime is per process.** The WebSocket hub keeps connections in memory, so
  running more than one worker means a client only receives events published by the
  worker it is connected to; a shared pub/sub (e.g. Redis) is required to fan out
  across workers.
- **Notification email is synchronous** with the request that triggers it. Delivery
  failures are logged and never fail the API call, but a slow SMTP server adds latency
  to ticket creation.
- No refresh tokens, no email change flow, no audit log.
- **Custom fields are not searchable.** `custom_fields_json` is plain JSON text, so only
  title, description and ticket code are matched by `search=`.
