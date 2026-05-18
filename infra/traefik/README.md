# Traefik

This directory holds Traefik's static and dynamic configuration. The
static configuration is passed via CLI flags in
`infra/docker-compose.yml`; only the dynamic part lives here.

## Files

- `dynamic/aidev.yml` — middleware definitions (security headers,
  rate limit, gzip).
- `dynamic/task-<id>.yml` — **generated at runtime** by the
  sandbox-runner worker each time a preview goes live. Removed when
  the task ends. Do NOT commit these.

## Per-task preview routing

When a frontend QA run succeeds inside a sandbox, the worker:

1. Reads the task's preview port from the sandbox metadata.
2. Writes a Traefik file provider entry that maps
   `task-<id>.preview.<AIDEV_DOMAIN>` to that container.
3. Traefik picks up the file (watched mount) and starts proxying.

This avoids running a long-lived public web server inside each
sandbox — the sandbox stays isolated, and Traefik handles TLS and
egress.
