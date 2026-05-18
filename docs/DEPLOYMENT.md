# Deployment

This document covers deploying AI Developer to a Linux VPS with optional
GPU. For a local dev setup see `INSTALLATION.md`.

## Reference targets

The project is being built against these initial hosts:

| Host                  | Role                                            |
| --------------------- | ----------------------------------------------- |
| Ubuntu 24 LTS (GPU)   | Model server (Ollama/vLLM), API, workers, DB,   |
|                       | sandbox containers, Traefik                     |
| Windows 11 Pro VPS    | Optional manual-QA / RDP preview client only.   |
|                       | **Does not** run the Linux Docker sandboxes.    |

> Production credentials are loaded from environment / secret manager.
> Never commit them. Rotate any password that has appeared in chat.

## Topology

```
                         ┌───────────────────────────┐
                         │  user (browser)           │
                         └─────────────┬─────────────┘
                                       │ HTTPS
                            ┌──────────▼──────────┐
                            │  Traefik (TLS)      │
                            │  *.aidev.example.com│
                            └──────────┬──────────┘
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
        ┌───────────────┐      ┌───────────────┐      ┌─────────────────┐
        │ apps/web      │      │ apps/api      │      │ task-<id>       │
        │ Next.js       │      │ FastAPI       │      │ .preview.…      │
        │ (port 3000)   │      │ (port 8000)   │      │ → sandbox:3000  │
        └───────────────┘      └──────┬────────┘      └─────────────────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
        ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
        │ PostgreSQL    │     │ Redis         │     │ Ollama / vLLM │
        │ 15            │     │ 7             │     │ (GPU)         │
        └───────────────┘     └───────────────┘     └───────────────┘
                                      ▲
                                      │
                            ┌─────────┴──────────┐
                            │ agent-runner       │
                            │ sandbox-runner     │
                            │ (Celery workers)   │
                            └────────────────────┘
```

## Step-by-step (Ubuntu 24 GPU host)

### 1. Base packages

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git curl ufw
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
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

Verify: `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`.

### 3. Model server

Pick one (see `MODEL_SERVER_SETUP.md`):

```bash
# Ollama (simplest)
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5-coder:14b
```

Set in `infra/.env`: `MODEL_BASE_URL=http://host.docker.internal:11434/v1`
(or use the host IP if your Docker version doesn't support
`host.docker.internal`).

### 4. Clone and configure

```bash
git clone https://github.com/Moksha89/aidev.git /opt/aidev
cd /opt/aidev/infra
cp .env.example .env
# edit .env — set DOMAIN, POSTGRES_PASSWORD, MODEL_BASE_URL,
# GITHUB_TOKEN (or GitHub App), and ACME_EMAIL for Let's Encrypt
```

### 5. Bring it up

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

### 6. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Open ports `5432` (Postgres), `6379` (Redis), and `11434` (Ollama) **only**
to localhost — they are exposed inside the Docker network only.

### 7. DNS

Point `aidev.example.com`, `api.aidev.example.com`, and a wildcard
`*.preview.aidev.example.com` at the VPS IP. Traefik will request
Let's Encrypt certs on first contact.

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
# Redis (only ephemeral state — usually fine to skip)
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

## Security posture in production

See `SECURITY.md`. Highlights:

- Sandboxes run as non-root with `--read-only --security-opt no-new-privileges`.
- Sandboxes are on an isolated Docker network with egress restricted to the
  model server, GitHub, and configured package mirrors.
- The `.env` file is owned by root, mode 0600.
- Postgres is not exposed to the public internet.
- Every approval action is recorded in `task_approvals` with `actor_user_id`
  and `actor_ip`.
