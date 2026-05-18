# AI Developer

A self-hosted, private, Devin-like AI developer platform. It manages a sequence
of AI agents (Planner, Frontend, Backend, QA, Security) that plan, code, test,
and deploy software inside isolated Docker sandboxes — with a **strict
frontend-first approval gate** enforced in code, not just in prompts.

> **Status:** MVP scaffold. The code in this repository wires up the dashboard,
> backend, rules engine, and worker interfaces. The Docker sandbox runtime is
> stubbed behind a `SandboxExecutor` interface and replaced with a mock
> executor for local development. See `docs/ROADMAP.md` for what is real and
> what is stubbed.

---

## Highlights

- **Dashboard** (Next.js + Tailwind + shadcn/ui) — chat with the agent, browse
  projects, watch live activity, review diffs/logs/screenshots, approve or
  reject the frontend before any backend work begins.
- **Backend** (FastAPI + PostgreSQL) — projects, repositories, tasks, logs,
  previews, approvals; GitHub REST integration for branch & PR creation.
- **Workers** (Celery + Redis) — `agent-runner` orchestrates the agent
  sequence; `sandbox-runner` is the abstraction that will (eventually) launch
  a Docker container per task.
- **Rules engine** (`packages/rules-engine`) — a phase-aware allowlist/denylist
  evaluator driven by the project's `.ai-rules/*.md` files. Every file write
  the agent attempts is validated **before** it touches the workspace.
- **Frontend-first approval gate** — until a human approves the frontend via
  the dashboard, the rules engine rejects any write outside the allowed
  frontend paths.
- **Model server agnostic** — talks to any OpenAI-compatible endpoint
  (Ollama, vLLM, llama.cpp server, LM Studio). No external API keys required.

## Repository layout

```
aidev/
├── apps/
│   ├── web/            # Next.js 14 dashboard (App Router + shadcn/ui)
│   └── api/            # FastAPI backend + SQLAlchemy models
├── workers/
│   ├── agent-runner/   # Celery worker — multi-agent orchestrator
│   └── sandbox-runner/ # Celery worker — Docker sandbox executor (mock today)
├── packages/
│   ├── shared/         # Shared types/enums (TaskPhase, AgentRole, …)
│   ├── rules-engine/   # .ai-rules parser + path/phase enforcement
│   ├── github-client/  # Thin GitHub REST wrapper (branches, PRs, commits)
│   └── model-client/   # OpenAI-compatible client (Ollama / vLLM)
├── docker/             # Per-service Dockerfiles (web, api, worker, sandbox)
├── infra/              # docker-compose, nginx, traefik configs
├── docs/               # Architecture, install, deployment, security, roadmap
└── .ai-rules/          # Default rule set shipped with the platform
```

## Quick start (local dev, without Docker)

Requires Node.js 20+, Python 3.11+, PostgreSQL 15+, and Redis 7+.

```bash
# 1. backend
cd apps/api
cp .env.example .env
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000

# 2. agent worker
cd workers/agent-runner
poetry install
poetry run celery -A app.celery_app worker -l info

# 3. dashboard
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

Open `http://localhost:3000`.

## Quick start (Docker)

```bash
cd infra
cp .env.example .env       # set DOMAIN, POSTGRES_PASSWORD, MODEL_BASE_URL, …
docker compose up -d
```

Dashboard at `http://localhost`, API at `http://api.localhost`.

See `docs/INSTALLATION.md` for the long form, including model-server setup
(Ollama / vLLM) and GitHub App configuration.

## The frontend-first rule

The single most important behaviour of this platform: **agents cannot touch
backend code until you explicitly approve the frontend.**

This is enforced in three places:

1. The **rules engine** parses `.ai-rules/frontend-first.md` and refuses any
   write outside the allowed glob patterns while `task.phase != BACKEND_UNLOCKED`.
2. The **agent-runner** loads only the Frontend agent prompt (and a tiny QA
   agent for Playwright) until the phase transitions.
3. The **sandbox-runner** (when wired up) mounts backend paths as read-only
   overlayfs layers, so even a bug in the rules engine cannot let an agent
   write to `apps/api/**`, `migrations/**`, or `.env*`.

See `docs/FRONTEND_FIRST_WORKFLOW.md`.

## Multi-agent pipeline

```
Planner ──▶ Frontend Developer ──▶ QA (Playwright) ──▶ [HUMAN APPROVAL]
                                                          │
                                                          ▼
                                            Backend Developer ──▶ Security Reviewer ──▶ PR
```

Each agent is a separate prompt + tool set; transitions are gated by the
rules engine and (for the human gate) the dashboard's "Approve frontend"
button.

## Contributing

This is an early-stage scaffold. See `docs/ROADMAP.md` for the things that
are stubbed and need real implementations — most notably the sandbox runtime.

## License

MIT — see `LICENSE`.
