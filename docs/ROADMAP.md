# Roadmap

This is the MVP scaffold. Several subsystems are intentionally stubbed.
This document is the honest list of "what's real vs. what's a TODO".

## v0.1 — MVP scaffold (this PR)

- [x] Monorepo layout (`apps/`, `workers/`, `packages/`, `docker/`, `infra/`, `docs/`, `.ai-rules/`)
- [x] FastAPI backend with full route surface (auth, projects, repos, tasks, logs, files, diff, preview, screenshots, approvals, settings)
- [x] SQLAlchemy models + initial Alembic migration
- [x] Next.js 14 dashboard with all listed pages (App Router + shadcn/ui)
- [x] `packages/rules-engine` with unit tests
- [x] `packages/shared` enums (Python + TypeScript mirrors)
- [x] `packages/github-client` (real GitHub REST calls behind a feature flag)
- [x] `packages/model-client` (OpenAI-compatible client)
- [x] `workers/agent-runner` (Celery) with mock multi-agent flow
- [x] `workers/sandbox-runner` with `SandboxExecutor` interface + `MockSandboxExecutor`
- [x] Docker Compose for local single-host install
- [x] `.ai-rules/*.md` default rule set
- [x] Documentation set (this folder)

## v0.2 — Real sandbox runtime

- [ ] `DockerSandboxExecutor` — `docker run` per task with the security
      flags listed in `SECURITY.md`
- [ ] Sandbox image (`docker/Dockerfile.sandbox`) with Node 20, Python
      3.11, Playwright, gh, git, ripgrep
- [ ] Overlayfs read-only layer for backend paths in `FRONTEND_CODING` phase
- [ ] Egress whitelist proxy (Squid) on the sandbox bridge network
- [ ] Resource caps + 30-minute task timeout

## v0.3 — Real preview subdomains

- [ ] Traefik dynamic file provider populated by the worker
- [ ] `task-<id>.preview.<domain>` → sandbox container port 3000
- [ ] Per-task Let's Encrypt certs (or wildcard cert)
- [ ] Preview reaper — tear down preview when task moves to `DONE`/`REJECTED`

## v0.4 — Real multi-agent loop

- [ ] Planner agent prompt + tool use (read-only repo exploration)
- [ ] Frontend agent prompt + write-tool wrapped by rules engine
- [ ] QA agent that actually runs Playwright in the sandbox
- [ ] Backend agent prompt + tool set
- [ ] Security Reviewer agent that runs `semgrep` + `bandit` + custom rules
- [ ] Streaming token output from worker → API → dashboard via SSE

## v0.5 — Production hardening

- [ ] Auth: OIDC + GitHub App-based login
- [ ] RBAC: roles (owner / approver / viewer) per project
- [ ] Per-project rule overrides via `/settings/rules`
- [ ] Per-project model server selection via `/settings/models`
- [ ] Per-project GitHub installation via `/settings/github`
- [ ] Audit log export (JSON Lines)
- [ ] Backup / restore scripts

## v1.0 — Real-world readiness

- [ ] HA Postgres
- [ ] Multi-host worker fleet
- [ ] Per-task cost tracking (tokens, GPU-minutes)
- [ ] Web Storybook for the dashboard components
- [ ] End-to-end test suite (Playwright against the deployed stack)

## Stretch / research

- [ ] Firecracker microVMs as the sandbox runtime (instead of Docker)
- [ ] Persistent agent memory per project (vector store)
- [ ] Multi-repo tasks (cross-cutting changes)
- [ ] Plan-only mode: agent produces a PR description and no code
- [ ] "Devin Review"-style automatic code review on third-party PRs
