# `apps/web` — AI Developer dashboard

Next.js 14 (App Router) + Tailwind CSS + shadcn-style components. The
dashboard talks to the FastAPI backend over HTTPS and never holds any
credentials in client-side code.

## Run locally

```bash
cd apps/web
cp .env.example .env.local
pnpm install         # or `npm install`
pnpm dev             # http://localhost:3000
```

You also need the backend running on the URL referenced by
`NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). See
`apps/api/README.md`.

## Layout

```
src/
  app/                  # App-router pages
    dashboard/
    projects/
    repositories/
    tasks/[id]/
    settings/
  components/           # Shared UI
    ui/                 # shadcn-style primitives
  lib/
    api.ts              # fetch wrapper for the FastAPI backend
    mocks.ts            # mock data used pre-backend
    types.ts            # TS mirror of the API schemas
    utils.ts
```

## Frontend-first workflow

The dashboard is the only place a human can flip a task from
`awaiting_approval` to `backend_unlocked`. The button calls
`POST /tasks/:id/approve-frontend`; the backend writes a row to
`task_approvals` (with IP + user agent) and only then does the worker
extend the rules-engine allowlist to backend paths.
