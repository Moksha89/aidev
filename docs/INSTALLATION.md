# Installation

There are two supported paths:

1. **Local development** — run each component on your machine.
2. **Docker Compose** — single-host install for an internal team.

Production (multi-host, with Traefik + per-task preview subdomains) is
covered in `DEPLOYMENT.md`.

---

## 1. Local development

### Prerequisites

- Node.js 20+ and pnpm 9+
- Python 3.11+ and Poetry 1.8+
- PostgreSQL 15+
- Redis 7+
- A running OpenAI-compatible model server (see `MODEL_SERVER_SETUP.md`)

### 1.1 Backend (FastAPI)

```bash
cd apps/api
cp .env.example .env
# edit .env — set DATABASE_URL, REDIS_URL, MODEL_BASE_URL
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000
```

The API will be at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

### 1.2 Agent worker

```bash
cd workers/agent-runner
cp .env.example .env
poetry install
poetry run celery -A app.celery_app worker -l info
```

The worker uses the **mock sandbox executor** by default. To switch to the
(stubbed) Docker executor, set `SANDBOX_EXECUTOR=docker` in `.env` — but
note that the Docker executor is not yet implemented (see `ROADMAP.md`).

### 1.3 Dashboard (Next.js)

```bash
cd apps/web
cp .env.example .env.local
# set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
pnpm install
pnpm dev
```

Dashboard at `http://localhost:3000`. Sign in with the seed account created
by `apps/api/scripts/seed.py` (run automatically by `alembic upgrade head`
in dev mode).

---

## 2. Docker Compose (single host)

```bash
cd infra
cp .env.example .env
# edit .env — set:
#   DOMAIN=aidev.local
#   POSTGRES_PASSWORD=...
#   MODEL_BASE_URL=http://host.docker.internal:11434/v1
#   GITHUB_APP_ID=... (optional, for PR creation)
docker compose up -d --build
```

Services:

| Service       | URL (default `DOMAIN=aidev.local`) |
| ------------- | ----------------------------------- |
| Dashboard     | `http://aidev.local`                |
| API           | `http://api.aidev.local`            |
| Traefik admin | `http://traefik.aidev.local:8080`   |

Add to `/etc/hosts` for local dev:

```
127.0.0.1 aidev.local api.aidev.local traefik.aidev.local
```

### Logs

```bash
docker compose logs -f api
docker compose logs -f agent-runner
```

### Reset

```bash
docker compose down -v   # WARNING: drops the database
```

---

## 3. Model server

The platform speaks the **OpenAI Chat Completions** wire protocol. Any
server that implements it will work:

- **Ollama** — easiest. `ollama serve` then `ollama pull qwen2.5-coder:14b`.
  Set `MODEL_BASE_URL=http://localhost:11434/v1`.
- **vLLM** — best throughput on multi-GPU hosts.
  `vllm serve Qwen/Qwen2.5-Coder-14B-Instruct --port 8001`. Set
  `MODEL_BASE_URL=http://localhost:8001/v1`.
- **LM Studio** — turn on the local server in the GUI; default port 1234.

See `MODEL_SERVER_SETUP.md` for sizing recommendations per GPU class.

---

## 4. GitHub integration

The platform creates branches and pull requests via the GitHub REST API.
It supports two auth modes:

1. **Personal Access Token (PAT)** — quickest for a single user.
2. **GitHub App** — recommended for multi-user installations.

Configure via `/settings/github` in the dashboard, or set:

```
GITHUB_TOKEN=ghp_…
# or
GITHUB_APP_ID=…
GITHUB_APP_PRIVATE_KEY_PATH=/etc/aidev/github-app.pem
GITHUB_APP_INSTALLATION_ID=…
```

See `GITHUB_INTEGRATION.md` for the full setup.

---

## 5. Troubleshooting

- **`alembic upgrade head` fails with "relation does not exist"** — the
  database is fresh but the search path is wrong. Run
  `psql -c 'CREATE SCHEMA IF NOT EXISTS aidev;'` first.
- **Worker says "model server unreachable"** — check `MODEL_BASE_URL` is
  reachable from inside the container (`docker exec aidev-agent-runner
  curl $MODEL_BASE_URL/models`).
- **Approval gate doesn't engage** — open `/settings/rules` and confirm
  the `frontend-first.md` rule is enabled for the project.
