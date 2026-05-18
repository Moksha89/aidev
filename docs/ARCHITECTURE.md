# Architecture

This document describes the AI Developer platform at a high level. For specific
subsystems see the other files in `docs/`.

## Goals

1. **Private** — runs entirely on infrastructure the operator controls. No
   third-party LLM API keys are required; the platform talks to any
   OpenAI-compatible local server (Ollama, vLLM, llama.cpp).
2. **Reviewable** — every change an agent proposes must be visible to a human
   in the dashboard (diff, logs, screenshots, preview URL) before it can be
   pushed to a real branch as a PR.
3. **Safe by construction** — the agent runs in a Docker sandbox; the rules
   engine enforces a frontend-first policy in code, not just in prompts.

## Component map

```
┌──────────────────────────────────────────────────────────────┐
│                         User (browser)                       │
└──────────────────────────────────────────────────────────────┘
                              │  HTTPS
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ apps/web — Next.js 14 (App Router + Tailwind + shadcn/ui)    │
│   /dashboard /projects /tasks/:id /settings/*                │
└──────────────────────────────────────────────────────────────┘
                              │  REST + WebSocket
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ apps/api — FastAPI + SQLAlchemy + Alembic                    │
│   auth, projects, repos, tasks, logs, previews, approvals    │
│   GitHub REST integration (branches, PRs, commits)           │
└──────────────────────────────────────────────────────────────┘
       │                       │                         │
       ▼                       ▼                         ▼
┌────────────┐         ┌───────────────┐         ┌────────────────┐
│ PostgreSQL │         │ Redis (broker │         │ Object store / │
│ 15         │         │  + pub/sub)   │         │ local FS for   │
└────────────┘         └───────────────┘         │ screenshots    │
                              │                  └────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ workers/agent-runner — Celery worker                         │
│   Orchestrates multi-agent pipeline:                         │
│     Planner → Frontend → QA → [HUMAN] → Backend → Security   │
│   Calls into rules-engine before every file write.           │
└──────────────────────────────────────────────────────────────┘
                              │  spawns one sandbox per task
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ workers/sandbox-runner — SandboxExecutor                     │
│   MockSandboxExecutor   (in-process — used for dev + CI)     │
│   DockerSandboxExecutor (production — docker container per   │
│                          task, non-root UID 10001, read-only │
│                          rootfs, no-new-privileges, 2 CPU /  │
│                          4 GB / 512 pids / 30-min timeout,   │
│                          internal network + tinyproxy egress │
│                          allowlist, Traefik preview routes)  │
│   See docs/SANDBOX_EXECUTOR.md                               │
└──────────────────────────────────────────────────────────────┘
                              │  OpenAI-compatible HTTP
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ Model server — Ollama, vLLM, llama.cpp, LM Studio …          │
└──────────────────────────────────────────────────────────────┘
```

## Shared packages

- **`packages/shared`** — Python and TypeScript mirrors of the core enums
  (`TaskPhase`, `AgentRole`, `LogLevel`) so both sides agree on the wire format.
- **`packages/rules-engine`** — parses `.ai-rules/*.md`, exposes
  `Evaluator.is_write_allowed(path, phase, rules)`. Used by the agent-runner
  and (transitively) by the API to surface rule violations to the dashboard.
- **`packages/github-client`** — thin wrapper over the GitHub REST API.
  `branches.create`, `pulls.create`, `repos.get`, …
- **`packages/model-client`** — OpenAI-compatible client; configurable base
  URL/key/model per project.

## Task lifecycle (the heart of the system)

```
PENDING
  └─▶ PLANNING                 (Planner agent runs)
        └─▶ FRONTEND_CODING    (Frontend agent runs; rules-engine restricts
                               │   writes to frontend allowlist)
              └─▶ FRONTEND_QA  (Playwright builds + screenshots)
                    └─▶ AWAITING_APPROVAL   ◀── DASHBOARD SHOWS DIFF/PREVIEW
                          │
                          ├──▶ REJECTED            (user clicks Reject)
                          │
                          └──▶ BACKEND_UNLOCKED    (user clicks Approve)
                                └─▶ BACKEND_CODING
                                      └─▶ SECURITY_REVIEW
                                            └─▶ PR_OPENED
                                                  └─▶ DONE
```

The `TaskPhase` enum lives in `packages/shared` and is the single source of
truth. The API exposes it; the rules engine keys off it; the worker
transitions it; the dashboard renders it.

## Data model

See `apps/api/app/models/` for the full SQLAlchemy schema. Tables:

- `users` — auth principals
- `projects` — top-level container for a product the agent is building
- `repositories` — GitHub repos linked to a project
- `tasks` — one instruction → one task → one branch → (optionally) one PR
- `task_logs` — append-only structured log lines streamed from the worker
- `task_previews` — preview URL + Playwright screenshots per task
- `task_approvals` — audit trail of approve/reject decisions
- `task_messages` — chat between the user and the agent
- `task_files` — files changed in the task workspace (with status)
- `model_servers` — configured Ollama/vLLM endpoints
- `rule_sets` — per-project overrides of the global `.ai-rules`

## Why the rules engine is its own package

It is the *only* place where the frontend-first policy is implemented in
code. By keeping it as an importable package (Python today, TypeScript
mirror later), we can:

- unit-test the policy in isolation,
- reuse it from the API (to surface human-readable violation reasons),
- reuse it from a future static analyzer that scans agent-proposed diffs,
- and eventually run it as a sidecar that audits every workspace write at
  the filesystem layer.

## What is real vs. stubbed in the MVP

| Subsystem            | MVP state                                         |
| -------------------- | ------------------------------------------------- |
| Dashboard UI         | Real, with mock data fallback                     |
| FastAPI endpoints    | Real, all listed routes implemented               |
| PostgreSQL schema    | Real, with Alembic migration                      |
| Rules engine         | Real, unit-tested                                 |
| GitHub client        | Real, but wired to a feature flag                 |
| Model client         | Real, points at `MODEL_BASE_URL`                  |
| Agent orchestration  | Real Celery wiring; agent prompts are templates   |
| Sandbox executor     | Real Docker executor + mock for dev/CI            |
| Preview subdomains   | Traefik dynamic file provider, per-task routes    |
| Playwright QA        | Real script generator; screenshots from sandbox   |

See `docs/ROADMAP.md` for the path from MVP to v1.
