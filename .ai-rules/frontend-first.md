---
id: frontend-first
title: Frontend-first approval gate
applies_to: phases.FRONTEND_CODING
priority: 90
enforced_by: [rules_engine, overlayfs]
---

# Frontend-first approval gate

Until a human approves the frontend via the dashboard, you may only
write frontend files. This rule is enforced in code, not just here.

## Allowed paths

```glob
src/**
app/**
pages/**
components/**
styles/**
public/**
mocks/**
tests/e2e/**
tests/playwright/**
tailwind.config.*
postcss.config.*
next.config.*
vite.config.*
tsconfig.json
package.json
package-lock.json
pnpm-lock.yaml
yarn.lock
.eslintrc*
.prettierrc*
README.md
```

## Forbidden paths (this phase only)

```glob
apps/api/**
backend/**
server/**
api/**
routes/api/**
controllers/**
models/**
db/**
database/**
migrations/**
alembic/**
prisma/**
infra/**
docker/**
.github/workflows/**
**/.env*
**/secrets/**
**/credentials.*
**/wallet/**
**/payments/**
**/billing/**
**/settlement/**
**/auth/server/**
**/rng/**
**/game/result/**
```

## Allowed network egress

Inside this phase the sandbox may reach:

- the model server (`MODEL_BASE_URL`)
- the configured npm / pnpm / yarn registry
- `api.github.com` (read-only operations only)
- `playwright.dev` and `download.playwright.dev` (browser binaries)

All other egress is rejected by the sandbox network policy.

## Mock data policy

You may (and should) produce mock data files under `src/mocks/` or
`mocks/` so the UI renders without a live backend. Mocks must be:

- TypeScript modules, not JSON the UI fetches from disk,
- deterministic (no `Math.random()` in the module body),
- typed against the expected response shape so the backend agent can
  later align the API to them.

## "Done" criteria for this phase

You must self-report complete only when:

1. `pnpm build` (or the project's equivalent) succeeds.
2. `pnpm lint` produces no errors.
3. The Playwright screenshot suite runs and saves images at the
   `mobile-375`, `mobile-430`, `tablet-768`, `desktop-1280`, and
   `desktop-1920` viewports.
4. The preview URL is reachable from inside the sandbox.

The platform will then transition the task to `AWAITING_APPROVAL`.
