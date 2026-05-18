# Sandbox executor

The sandbox executor is the runtime layer that gives one task its own
Docker container, isolates it from the host and from other tasks, and
enforces the frontend-first approval gate **in code, not just in
prompts**.

It implements the `SandboxExecutor` protocol in
[`workers/sandbox-runner/sandbox_runner/base.py`](../workers/sandbox-runner/sandbox_runner/base.py).
Two implementations ship with the platform:

| Variant                  | When to use                              | File                                    |
| ------------------------ | ---------------------------------------- | --------------------------------------- |
| `MockSandboxExecutor`    | Local dev & CI (in-process tempdir)      | `sandbox_runner/mock_executor.py`       |
| `DockerSandboxExecutor`  | Production / VPS deploy                  | `sandbox_runner/docker_executor.py`     |

Select via `SANDBOX_EXECUTOR=docker` (defaults to `mock`). See
[`infra/.env.example`](../infra/.env.example).

## Design goals

1. **One ephemeral container per task.** No long-lived pool. Compromise
   blast radius = a single task's lifetime.
2. **Frontend-first enforced at three layers**: prompt, rules engine,
   filesystem. The agent cannot accidentally write a backend file
   pre-approval *even if* layers 1 and 2 are bypassed by a future bug.
3. **Strict allowlist egress.** Sandboxes run on a per-task
   `internal: true` Docker network; the only path out is the
   `aidev-egress-proxy` (tinyproxy) sidecar, which deny-by-defaults
   anything not on the allowlist.
4. **Cleanup is not optional.** Container, volume, network, and Traefik
   route are all removed in a `finally` block; if any step fails it is
   logged but the others still run.

## Container safety profile

`DockerSandboxExecutor` creates each container with:

```
image           aidev/sandbox:latest         # node:20 + py3.11 + playwright + gh
command         sleep infinity               # the executor drives via docker exec
user            10001:10001                  # non-root agent UID
working_dir     /workspace
read_only       true                         # root FS is read-only
tmpfs           /tmp (512m), /home/agent/.cache (512m)
security_opt    no-new-privileges:true
cap_drop        ALL                          # drop every Linux capability
mem_limit       4g                           # AIDEV_SANDBOX_MEM_LIMIT
nano_cpus       2e9                          # AIDEV_SANDBOX_CPUS (2 CPUs)
pids_limit      512                          # AIDEV_SANDBOX_PIDS_LIMIT
network         aidev_sandbox_<task_id>      # internal=true, no default gw
volumes         aidev-sandbox-vol-<task_id>:/workspace   # only mount
```

No host bind mounts, no Docker socket inside, no host network access.

Task wall-clock is capped at `AIDEV_SANDBOX_TIMEOUT_SECONDS` (default
`1800` / 30 min). Each `session.run()` call is further capped by the
caller-provided per-command timeout; the executor returns
`SandboxCommandError` if the task-level deadline is exceeded.

## The three layers of the frontend-first gate

### Layer 1 — Prompt
Every agent's system prompt embeds the active `.ai-rules` for the
current phase and lists which paths are allowed. Necessary but not
sufficient — a prompt is not a security boundary.

### Layer 2 — Rules engine
`session.write_file(path, content)` calls
`Evaluator.assert_write_allowed(path, phase)` from
`aidev_rules_engine` before any bytes hit the container. Violations
raise `RuleViolation` and surface in the dashboard with a
human-readable reason. See [`packages/rules-engine`](../packages/rules-engine).

### Layer 3 — Filesystem (`fs_protection.py`)
After `clone_repo()` and again after every `set_phase()`, the executor
runs a generated shell script **as root** inside the sandbox that does
`chmod -R a-w,a+rX` on the backend / infra / `.env*` paths. The agent
process runs as UID 10001 with `no-new-privileges`, so even if layers 1
and 2 are bypassed, `write("apps/api/main.py")` fails with `EACCES` at
the kernel level.

`plan_for_phase(BACKEND_UNLOCKED)` is the inverse: it restores
`u+rwX,go+rX` on backend paths but **keeps `.env*` locked** so secrets
are forbidden in every phase, including post-approval.

The protected path list lives in
[`sandbox_runner/fs_protection.py`](../workers/sandbox-runner/sandbox_runner/fs_protection.py)
and intentionally mirrors the deny-list in
[`.ai-rules/frontend-first.md`](../.ai-rules/frontend-first.md). Update
both together.

## Network egress allowlist

The sandbox network is `internal: true`, so by default it has no route
to the internet. The executor wires in a single egress path:

```
        sandbox container                   egress-proxy
       (per-task network)                  (tinyproxy sidecar)
              │                                   │
              │  HTTP(S)_PROXY=http://aidev-      │  filters by anchored
              │     egress-proxy:8888 ────────────▶  regex allowlist;
              │                                   │  deny-by-default
              │                                   ▼
                                              upstream internet
```

Default allowlist (`sandbox_runner.egress.DEFAULT_ALLOWLIST`):

- `github.com`, `api.github.com`, `codeload.github.com`, `*.github.com`,
  `*.githubusercontent.com`
- `registry.npmjs.org`, `registry.yarnpkg.com`, `*.npmjs.org`
- `pypi.org`, `files.pythonhosted.org`, `*.pypi.org`,
  `*.pythonhosted.org`
- `deb.debian.org`, `security.debian.org`, `archive.ubuntu.com`,
  `security.ubuntu.com`, `ports.ubuntu.com`

`build_allowlist()` merges in the operator-configured
`AIDEV_SANDBOX_MODEL_SERVER_HOST` (the Ollama/vLLM hostname) plus any
`AIDEV_SANDBOX_EXTRA_EGRESS_HOSTS` extras.

The proxy itself is configured in
[`infra/sandbox/`](../infra/sandbox/) — tinyproxy with
`FilterDefaultDeny Yes`, `FilterExtended On`, and an anchored regex
per host (`^github\.com$`, `^[^.]+\.pypi\.org$`, …) so
`github.com.attacker.test` does not match `github.com`.

## Preview routing through Traefik

When the frontend dev server is ready,
`session.start_preview_server()` writes a small dynamic config to
`infra/traefik/dynamic/tasks/task-<task_id>.yml`. Traefik's file
provider picks it up automatically (no reload) and serves
`https://task-<task_id>.preview.<DOMAIN>` → sandbox container port
3000.

The generated config attaches three Traefik middlewares —
`aidev-security-headers`, `aidev-rate-limit`, `aidev-compress` — so
preview URLs get HSTS / X-Content-Type-Options / a basic rate limit
out of the box.

On session exit `preview.deregister(task_id)` removes the dynamic file
and Traefik tears the route down within ~1 second.

## Log / diff / screenshot capture

Every interesting step publishes a structured event on the
`aidev.sandbox.events` Redis pub/sub channel. The API subscribes and
fans events out into `task_logs` (DB) and the dashboard's live activity
panel.

Event kinds (non-exhaustive):

```
sandbox.starting      sandbox.started     sandbox.failed   sandbox.finished
evaluator.set         phase.changed       fs_protection.applied
repo.cloned           repo.clone_failed
file.written          command.ran
diff.captured         files.changed
screenshots.captured  screenshots.failed
preview.registered
```

`capture_diff()` runs `git -c color.ui=never diff --no-color
--no-ext-diff HEAD` inside the sandbox; the result is streamed back to
the worker as a `CommandResult` and stored verbatim.

`capture_changed_files()` runs `git status --porcelain=v1` and parses
the result into a flat path list (renames resolved to the new path).

`capture_screenshots(viewports=[...], route="/")` drops a generated
Playwright script into `<workspace>/.aidev/playwright_capture.py`,
runs it inside the sandbox, and returns one screenshot path per
viewport. Defaults captured by the agent-runner are mobile-375,
mobile-430, tablet-768, desktop-1280, desktop-1920.

## Configuration knobs

All knobs live in `SandboxConfig` (`config.py`) and can be overridden
via env vars in `infra/.env`:

| Env var                                | Default                       | What it does                                                 |
| -------------------------------------- | ----------------------------- | ------------------------------------------------------------ |
| `SANDBOX_EXECUTOR`                     | `mock`                        | `mock` (in-process) or `docker` (production)                 |
| `AIDEV_SANDBOX_IMAGE`                  | `aidev/sandbox:latest`        | Container image                                              |
| `AIDEV_SANDBOX_CPUS`                   | `2`                           | CPU quota (`--cpus`)                                         |
| `AIDEV_SANDBOX_MEM_LIMIT`              | `4g`                          | Memory cap (`--memory`)                                      |
| `AIDEV_SANDBOX_PIDS_LIMIT`             | `512`                         | Max processes (`--pids-limit`)                               |
| `AIDEV_SANDBOX_TIMEOUT_SECONDS`        | `1800`                        | Wall-clock cap per task                                      |
| `AIDEV_SANDBOX_AGENT_UID`              | `10001`                       | Non-root UID inside the sandbox                              |
| `AIDEV_SANDBOX_EGRESS_PROXY_URL`       | `http://aidev-egress-proxy:8888` | Upstream proxy for HTTP(S)_PROXY env                         |
| `AIDEV_SANDBOX_MODEL_SERVER_HOST`      | *unset*                       | Hostname of Ollama/vLLM, added to allowlist                  |
| `AIDEV_SANDBOX_EXTRA_EGRESS_HOSTS`     | *unset*                       | Comma-separated extra allowlist entries                      |
| `AIDEV_SANDBOX_TRAEFIK_DYNAMIC_DIR`    | `/etc/traefik/dynamic/tasks`  | Where to drop per-task router YAML                           |
| `AIDEV_SANDBOX_PREVIEW_DOMAIN`         | `preview.aidev.local`         | Base domain for `task-<id>.preview.<DOMAIN>`                 |
| `AIDEV_SANDBOX_PREVIEW_PORT`           | `3000`                        | Internal port that the dev server listens on                 |
| `AIDEV_SANDBOX_READ_ONLY_ROOTFS`       | `true`                        | Mount root FS read-only (only flip for debugging)            |
| `AIDEV_REDIS_URL`                      | `redis://localhost:6379/0`    | Pub/sub channel for sandbox events                           |

## Building the image

```sh
# from repo root
docker build -t aidev/sandbox:latest -f docker/Dockerfile.sandbox .
docker build -t aidev/egress-proxy:latest infra/sandbox/
```

The compose file in `infra/docker-compose.yml` wires both up alongside
the API, worker, Postgres, Redis, and Traefik.

## Testing the executor

Unit tests live in `workers/sandbox-runner/tests/` and run against a
faked Docker SDK so they don't need a daemon:

```sh
cd workers/sandbox-runner
uv run pytest -q
```

The mock executor is exercised end-to-end (it really shells out and
creates a tempdir), and the Docker executor is exercised with the
faked client to assert the full safety profile (resource caps, non-root,
read-only rootfs, internal network, egress proxy attached, cleanup on
exit).

## Production deployment notes

`DockerSandboxExecutor` needs read/write access to the host Docker
socket — that is the **only** privileged piece. Compose mounts it at
`/var/run/docker.sock:/var/run/docker.sock:rw` for the
`sandbox-runner` service.

Mitigations to remember:

1. The worker process itself runs as non-root and only the executor
   path code touches the SDK.
2. The Traefik dynamic-tasks directory is bind-mounted writeable by the
   worker but read-only-watched by Traefik.
3. The egress proxy is the only path out of the per-task internal
   network — losing the proxy = sandbox is fully offline (fail safe).

Future hardening tracked in
[`docs/ROADMAP.md`](./ROADMAP.md): rootless Docker, sysbox or gVisor
for the sandbox runtime, dedicated machine for the worker.
