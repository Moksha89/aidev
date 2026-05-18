# `infra/` — deployment artifacts

This directory holds Compose, Traefik, and Nginx configs for the
single-node deployment described in `docs/DEPLOYMENT.md`.

```
infra/
  docker-compose.yml        # Postgres, Redis, API, web, workers, Traefik
  .env.example              # variables required by docker-compose
  traefik/
    dynamic/aidev.yml       # static middleware; per-task previews are
                            # written here at runtime by sandbox-runner
  nginx/
    aidev.conf              # Nginx fallback if you don't want Traefik
```

## Quickstart on the Ubuntu VPS

```bash
git clone https://github.com/Moksha89/aidev.git
cd aidev/infra
cp .env.example .env && vim .env       # set passwords + secret key
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f api
docker compose logs -f agent-runner
docker compose logs -f sandbox-runner
```

The model server (Ollama or vLLM) is **not** in compose — it runs on
the host so it can talk to the GPU. See `docs/MODEL_SERVER_SETUP.md`.
