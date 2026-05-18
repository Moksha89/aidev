# Frontend-First Workflow

This is the rule that defines the platform: **agents cannot touch backend
code until a human has approved the frontend.** This document describes
how that rule is implemented, enforced, and surfaced in the dashboard.

## Why

Most LLM agents fail in two places: they write too much code at once, and
they write code that touches things the user did not actually ask for
(usually: backend, auth, payments, deployment). By forcing the agent to
deliver a reviewable frontend first, we get:

- a tight visual feedback loop (preview URL + screenshots),
- a small reviewable diff,
- a hard line against the agent silently editing auth or money code,
- a clear point in time where the human commits to a direction.

## The phases

```
PENDING → PLANNING → FRONTEND_CODING → FRONTEND_QA → AWAITING_APPROVAL
                                                         │
                                            (Approve)   │   (Reject)
                                                         ▼
                                                BACKEND_UNLOCKED
                                                         │
                                                         ▼
                                                BACKEND_CODING
                                                         │
                                                         ▼
                                                SECURITY_REVIEW
                                                         │
                                                         ▼
                                                    PR_OPENED
                                                         │
                                                         ▼
                                                       DONE
```

A task starts in `PENDING`. The user kicks it off with `POST /tasks/:id/start`,
which transitions to `PLANNING`. The Planner agent produces a plan. The
Frontend agent then runs in `FRONTEND_CODING`, restricted by the rules
engine. When it self-reports complete, the worker transitions to
`FRONTEND_QA`, runs the build + Playwright screenshots, and transitions to
`AWAITING_APPROVAL`.

The dashboard shows the user:

- the diff (`/tasks/:id/diff`),
- the preview URL (`/tasks/:id/preview`),
- the screenshots at mobile / tablet / desktop sizes (`/tasks/:id/screenshots`),
- the agent's chat log (`/tasks/:id/chat`),
- the structured logs (`/tasks/:id/logs`).

The user clicks **Approve frontend** (calls
`POST /tasks/:id/approve-frontend`) or **Reject**
(`POST /tasks/:id/reject`).

## What's allowed in `FRONTEND_CODING`

From `.ai-rules/frontend-first.md`:

```yaml
allowed_paths:
  - "src/**"
  - "app/**"
  - "pages/**"
  - "components/**"
  - "styles/**"
  - "public/**"
  - "tests/e2e/**"
  - "tests/playwright/**"
  - "tailwind.config.*"
  - "next.config.*"
  - "vite.config.*"
  - "tsconfig.json"
  - "package.json"      # add/remove deps; lockfile change must be lockfile-only
  - "package-lock.json"
  - "pnpm-lock.yaml"
  - "yarn.lock"
forbidden_paths:
  - "apps/api/**"
  - "backend/**"
  - "server/**"
  - "migrations/**"
  - "alembic/**"
  - "infra/**"
  - "docker/**"
  - ".github/workflows/**"
  - "**/.env*"
  - "**/secrets/**"
  - "**/wallet/**"
  - "**/payments/**"
  - "**/auth/**"        # if an "auth" path exists under src/ for UI-only auth,
                       # it must be added to the project-level override
  - "**/settlement/**"
  - "**/rng/**"
  - "**/game/result/**"
```

Mock data is allowed and encouraged — the Frontend agent should produce
TypeScript files under `src/mocks/` and route the UI to them, so the
preview works without a backend.

## What's allowed in `BACKEND_CODING`

After approval the rules engine flips. Backend paths are now writable,
but a hard-denylist remains:

```yaml
forbidden_paths:
  - "**/.env"
  - "**/.env.production"
  - "**/secrets/**"
  - ".github/workflows/deploy*.yml"   # deployment workflows are off-limits
```

## What happens on rejection

When the user clicks **Reject**, they provide a reason. The worker:

1. Aborts the current sandbox,
2. Wipes the workspace,
3. Records the rejection in `task_approvals`,
4. Returns the task to `PENDING` so the user can edit the instruction and
   re-run.

The branch on GitHub is **not** pushed on rejection. Nothing leaves the
platform.

## Per-project overrides

Projects can override the default rules at `/settings/rules`. Overrides
are *additive* for `allowed_paths` and *restrictive* for `forbidden_paths`
— you can never use a project override to grant the agent more privilege
than the global defaults allow. This is enforced server-side.

## Defence-in-depth recap

| Layer            | What it does                                                      |
| ---------------- | ----------------------------------------------------------------- |
| Prompt           | Tells the agent the current phase + allowed paths.                |
| Rules engine     | Validates every write before it touches the workspace.            |
| Filesystem       | Backend paths are mounted read-only via overlayfs in frontend phase. |
| Container        | Non-root, read-only root FS, no host mounts, restricted egress.   |
| Audit            | Every write attempt (allowed or denied) is logged.                |

See `SECURITY.md` for the full security model.
