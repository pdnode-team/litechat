# LiteChat frontend

React + TypeScript + Tailwind CSS SPA for the LiteChat support desk. Talks to
the Litestar API over JSON; in production it is served as a static site and
calls same-origin `/api` and `/ws`.

## Run locally

```bash
cd frontend
pnpm install
pnpm dev          # http://127.0.0.1:3000, proxies /api and /ws to :8000
```

The Vite proxy target defaults to `http://127.0.0.1:8000`. Override with
`DEV_API_TARGET`. `VITE_API_BASE_URL` is only needed when the API is on a
different origin (then also set `ALLOWED_ORIGINS` on the backend). Same-origin
deploys leave it unset.

```bash
pnpm build        # tsc -b && vite build → dist/
pnpm lint         # oxlint
pnpm test         # vitest (formLogic mirror of the server rules)
```

## Layout

```
src/
  api/            # HTTP + WebSocket clients
  components/     # admin / agent / customer / auth / chat
  context/        # AuthContext, RealtimeContext
  types/          # shared TypeScript types
  utils/          # datetime, errors, formLogic (mirrors backend form_logic.py)
```

Node 24 is required (see `nixpacks.toml`): Vite 8's bundler needs `>=22.12`.
