# Deployment

This document covers deploying AI Developer to a Linux VPS with optional
GPU. For a local dev setup see `INSTALLATION.md`.

> **No production deployment is performed automatically.** The steps below
> are reference only. We will run them on the actual hosts **only after the
> sandbox runtime and security posture have been reviewed and approved.**

## Deployment modes

There are two supported modes. Pick one **before** you start; you can move
between them later by editing `infra/.env` + recreating the Traefik service.

### IP-only acceptance mode (default — `AIDEV_SANDBOX_PREVIEW_MODE=port`)

- No domain, no DNS, no Let's Encrypt, no wildcard certificate.
- Reach everything by IP + port:
  - Dashboard: `http://<ubuntu-vps-ip>:3000`
  - API: `http://<ubuntu-vps-ip>:8000`
  - Optional Traefik dashboard: `http://<ubuntu-vps-ip>:8080` (operator-IP-restricted)
  - Per-task previews: `http://<ubuntu-vps-ip>:<31000-31999>` (port allocated per task)
- Use this for the controlled Ubuntu host acceptance run. It keeps the
  attack surface minimal (no exposed ACME, no DNS provider token, no
  wildcard cert in browser caches).

### Production mode (`AIDEV_SANDBOX_PREVIEW_MODE=traefik`)

- Reach everything by domain:
  - `https://<DOMAIN>` → dashboard
  - `https://api.<DOMAIN>` → API
  - `https://task-<id>.preview.<DOMAIN>` → per-task preview
- Requires DNS (an apex `A`, `api.<DOMAIN>`, and a wildcard
  `*.preview.<DOMAIN>` record) plus an ACME flow (HTTP-01 or DNS-01).
- Out of scope for the acceptance run. Re-enable later when you're ready
  to expose the platform publicly.

The rest of this document focuses on IP-only mode.

## Reference targets

The project is being built against these initial hosts:

| Host                  | Role                                            |
| --------------------- | ----------------------------------------------- |
| Ubuntu GPU VPS        | Planned host for model server (Ollama/vLLM),    |
|                       | FastAPI API, Postgres, Redis, Celery workers,   |
|                       | Docker sandboxes, and Traefik.                  |
| Windows VPS           | Dashboard preview / manual RDP-based QA only.   |
|                       | **Does not** run the Linux Docker sandboxes.    |

> Credentials are loaded from environment / secret manager and referenced
> by name only in this repository:
> - `AIDEV_UBUNTU_VPS_PASSWORD` — Ubuntu GPU VPS administrator password.
> - `AIDEV_WINDOWS_VPS_PASSWORD` — Windows VPS administrator password.
>
> Never commit them. Rotate any password that has appeared in chat.

## Topology (IP-only mode)

```
                         ┌───────────────────────────┐
                         │  user (browser)           │
                         └─────────────┬─────────────┘
                                       │ HTTP (direct IP)
       ┌───────────────┬───────────────┼───────────────┬─────────────────┐
       ▼               ▼               ▼               ▼                 ▼
  apps/web :3000  apps/api :8000  traefik :8080  task-<id> :31xxx   ... :31yyy
  (Next.js)       (FastAPI)       (dashboard,    (sandbox dev       (another
                                   optional)     server, port-      task)
                                                 published from
                                                 container 3000)
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
        ┌───────────────┐      ┌───────────────┐      ┌─────────────────┐
        │ PostgreSQL 15 │      │ Redis 7       │      │ Ollama / vLLM   │
        │ (internal)    │      │ (internal)    │      │ (GPU, internal) │
        └───────────────┘      └───────────────┘      └─────────────────┘
                                      ▲
                                      │
                            ┌─────────┴──────────┐
                            │ agent-runner       │
                            │ sandbox-runner     │
                            │ (Celery workers)   │
                            └────────────────────┘
```

Postgres, Redis and the model server stay on the docker bridge — only
ports `3000`, `8000`, `8080` (optional) and the preview range
`31000-31999` are bound on the host.

## Step-by-step (Ubuntu GPU host, IP-only acceptance)

### 1. Base packages

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git curl ufw fail2ban
sudo systemctl enable --now docker
sudo systemctl enable --now fail2ban
sudo usermod -aG docker $USER
# log out and back in so docker group membership takes effect
```

### 2. (Optional) GPU drivers + NVIDIA Container Toolkit

```bash
sudo apt install -y nvidia-driver-550 nvidia-utils-550
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

Record VRAM here — it picks the model in step 3.

### 3. Model server (Ollama recommended for acceptance)

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
# Pick a model sized for the detected VRAM. Common safe defaults:
#   < 16 GB VRAM  ->  ollama pull qwen2.5-coder:7b
#   16-24 GB VRAM ->  ollama pull qwen2.5-coder:14b
#   >= 24 GB VRAM ->  ollama pull qwen2.5-coder:32b
ollama pull qwen2.5-coder:14b
```

Set in `infra/.env`:

```ini
MODEL_BASE_URL=http://host.docker.internal:11434/v1
```

(or use the host IP if your Docker version doesn't support
`host.docker.internal`).

### 4. Clone and configure

```bash
git clone https://github.com/Moksha89/aidev.git /opt/aidev
cd /opt/aidev/infra
cp .env.example .env
```

Required edits in `infra/.env` for IP-only mode:

```ini
# IP-only acceptance defaults -- already shipped, just confirm:
AIDEV_SANDBOX_PREVIEW_MODE=port
AIDEV_SANDBOX_PREVIEW_HOST=<ubuntu-vps-ip>
AIDEV_SANDBOX_PREVIEW_PORT_RANGE_START=31000
AIDEV_SANDBOX_PREVIEW_PORT_RANGE_END=31999

# Keep the executor on mock for the first acceptance pass, then switch to
# docker once the dashboard/API/GitHub/model paths are confirmed:
SANDBOX_EXECUTOR=mock     # change to "docker" only for the second pass

# Everything else:
POSTGRES_PASSWORD=<generate-a-strong-one>
MODEL_BASE_URL=http://host.docker.internal:11434/v1
# Optional, only if you want GitHub PR creation in the sandbox:
GITHUB_TOKEN=<short-lived-token-or-leave-unset-for-acceptance>
```

Do **not** set `AIDEV_DOMAIN`, `AIDEV_SANDBOX_PREVIEW_DOMAIN`,
`ACME_EMAIL`, or any DNS-provider tokens in IP-only mode — they are
ignored and only used by the production (Traefik+TLS) mode.

### 5. Build the sandbox + forwarder images

The sandbox-runner orchestrator needs two images pre-built **outside of
docker-compose**, because compose only builds the platform services
(api, web, workers, traefik, postgres, redis). These two images are
launched directly by the Docker SDK per task:

```bash
# Per-task agent sandbox (node + python + playwright + gh):
docker build -f docker/Dockerfile.sandbox -t aidev/sandbox:latest .

# Per-task preview forwarder (v0.2, alpine + socat). Required as soon as
# SANDBOX_EXECUTOR=docker — the executor will fail at session start if
# this image is missing.
docker build -f docker/Dockerfile.forwarder -t aidev/forwarder:latest .

docker image ls aidev/sandbox aidev/forwarder
# expect both images listed
```

### 6. Bring it up

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

Smoke-check from your laptop:

```bash
curl -sf http://<ubuntu-vps-ip>:8000/healthz
# expect: {"status":"ok"}
curl -sI http://<ubuntu-vps-ip>:3000 | head -1
# expect: HTTP/1.1 200 OK
```

### 7. Firewall (IP-only)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 3000/tcp comment 'aidev dashboard'
sudo ufw allow 8000/tcp comment 'aidev API'
# Optional Traefik dashboard -- restrict to your operator IP:
sudo ufw allow from <operator-ip> to any port 8080 proto tcp comment 'traefik dash'
# Per-task preview range (only needed when SANDBOX_EXECUTOR=docker):
sudo ufw allow 31000:31999/tcp comment 'aidev sandbox previews'
sudo ufw enable
sudo ufw status verbose
```

Postgres (`5432`), Redis (`6379`), and the model server (`11434`) stay
internal — they are only reachable on the Docker bridge and **must not**
be opened on the host.

### 8. Acceptance checklist

Run every section of `docs/SANDBOX_EXECUTOR.md` § "Manual acceptance
checklist". Record results in
`docs/runs/<YYYY-MM-DD>-ubuntu-acceptance.md` on a new branch + PR.

The two-pass acceptance sequence:

1. **Pass 1 — `SANDBOX_EXECUTOR=mock`:** verify dashboard, API, GitHub
   config, model config, task chat, approval-gate, log streaming and
   diff/screenshot viewers all work end-to-end with the mock executor.
2. **Pass 2 — `SANDBOX_EXECUTOR=docker`:** edit `infra/.env`, run
   `docker compose up -d --build sandbox-runner`, then run the v0.2
   live acceptance probe (now baked into the worker image at
   `/app/scripts/pass2_docker.py`):

   ```bash
   docker exec --user 0 \
       -e PYTHONPATH=/app \
       -w /app \
       infra-sandbox-runner-1 \
       python /app/scripts/pass2_docker.py
   ```

   Expect `ALL CHECKS PASSED` covering safety profile, dual-network
   layout, no default route in agent, raw-IP+unset-proxy both fail,
   egress allowlist works, denylist fails, FS protection,
   BACKEND_UNLOCKED, preview through forwarder, normal + exception
   cleanup, port slot recycle, and that the egress-proxy's default
   route stays pinned to `infra_default` after it joins the per-task
   internal sandbox bridge.

Do **not** open the platform to real project tasks until the
checklist is fully recorded and you've explicitly approved the next
phase.

## Updating

```bash
cd /opt/aidev
git pull origin main
docker compose up -d --build
docker compose run --rm api alembic upgrade head
```

## Backups

```bash
# Postgres
docker compose exec -T postgres pg_dump -U aidev aidev | gzip > /var/backups/aidev-$(date +%F).sql.gz
# Redis (only ephemeral state -- usually fine to skip)
```

Schedule via `cron`. Restore with `gunzip -c …sql.gz | docker compose exec -T postgres psql -U aidev aidev`.

## Windows VPS role

The Windows VPS is **not** part of the runtime path. It can be used for:

- manual QA against preview URLs in Edge/Chrome/Firefox on Windows,
- RDP-based screenshot capture if you ever need Windows-specific previews,
- a future Windows-build-target sandbox (Docker Desktop with Windows
  containers — out of scope for the MVP).

Do not attempt to host the Linux Docker sandbox on Windows; the sandbox
contract assumes a Linux kernel with overlayfs, cgroups v2, and seccomp.

## Promoting to domain-based production (future)

Once the acceptance run is signed off and you want public access:

1. Allocate `<DOMAIN>` and add three DNS records: apex `A`,
   `api.<DOMAIN>` `A`, and `*.preview.<DOMAIN>` `A`, all pointing at the
   Ubuntu GPU VPS.
2. In `infra/.env` set:
   ```ini
   AIDEV_DOMAIN=<DOMAIN>
   AIDEV_SANDBOX_PREVIEW_DOMAIN=preview.<DOMAIN>
   AIDEV_SANDBOX_PREVIEW_MODE=traefik
   ACME_EMAIL=<operator-email>
   ```
3. Re-open firewall ports `80` and `443`; close `3000`, `8000`, and the
   preview range.
4. `docker compose up -d --build traefik` to pick up the new entrypoints.
5. Validate certificate issuance (`docker compose logs traefik | grep -i
   acme`) before announcing the URL.

## Security posture in production

See `SECURITY.md`. Highlights:

- Sandboxes run as non-root with `--read-only --security-opt no-new-privileges`.
- Sandboxes are on an isolated Docker network with egress restricted to the
  model server, GitHub, and configured package mirrors via the
  `aidev-egress-proxy` tinyproxy sidecar.
- The `.env` file is owned by root, mode 0600.
- Postgres is not exposed to the public internet.
- Every approval action is recorded in `task_approvals` with `actor_user_id`
  and `actor_ip`.
