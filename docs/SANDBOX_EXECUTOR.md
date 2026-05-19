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
3. **Allowlist egress.** Every sandbox container has
   `HTTP_PROXY` / `HTTPS_PROXY` pointed at the per-task-attached
   `aidev-egress-proxy` (tinyproxy) sidecar, which deny-by-defaults
   anything not on the allowlist. Currently *cooperative* — see
   "Known limitations" below for the kernel-level follow-up.
4. **Cleanup is not optional.** Container, volume, network, and preview
   registration (port allocation in IP-only mode, or Traefik dynamic
   file in domain mode) are all removed in a `finally` block; if any
   step fails it is logged but the others still run.

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
network         aidev_sandbox_<task_id>      # per-task bridge; egress proxy attached
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

Every sandbox container has `HTTP_PROXY` / `HTTPS_PROXY` env vars
pointed at the `aidev-egress-proxy` (tinyproxy) sidecar attached to
its per-task bridge:

```
        sandbox container                   egress-proxy
       (per-task bridge)                   (tinyproxy sidecar)
              │                                   │
              │  HTTP(S)_PROXY=http://aidev-      │  filters by anchored
              │     egress-proxy:8888 ────────────▶  regex allowlist;
              │                                   │  deny-by-default
              │                                   ▼
                                              upstream internet
```

The proxy enforces a hostname allowlist (anchored regex,
deny-by-default). Any HTTP / HTTPS client that honours `HTTP_PROXY`
(curl, wget, pip, npm, pnpm, go, cargo, requests, urllib, axios, fetch
via Node, …) goes through tinyproxy and is filtered. Direct outbound
to raw IPs from the sandbox is *not* blocked at the kernel layer —
see "Known limitations" below.

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

## Preview routing

The sandbox supports two preview-registration backends. The active one
is selected by `AIDEV_SANDBOX_PREVIEW_MODE` (default `port`).

### `port` mode — IP-only acceptance (default)

Used for the controlled Ubuntu host acceptance run and any environment
where DNS / TLS is not desired. The executor allocates one host port
from `AIDEV_SANDBOX_PREVIEW_PORT_RANGE_START..END` (default 31000-31999)
**before** creating the container and publishes it via the standard
Docker `ports` map: `host:<allocated>` → `container:3000`. The dev
server becomes reachable at
`http://<AIDEV_SANDBOX_PREVIEW_HOST>:<allocated>` as soon as it binds.

The pool is in-memory and process-local — one sandbox-runner owns it.
Allocation is thread-safe (`PortPreviewRegistrar`), idempotent on
`task_id` (re-calls return the same port), and released on session
exit so the next task can reuse the slot.

```
   task A allocate -> 31000   (http://<host>:31000)
   task B allocate -> 31001   (http://<host>:31001)
   task A finishes -> release(31000)
   task C allocate -> 31000   (recycled)
```

When the pool is exhausted, `PortPoolExhaustedError` propagates and the
task transitions to `FAILED` rather than colliding on a port. Pick a
range wide enough for your peak concurrent task count (1000 slots is
plenty for the acceptance run).

### `traefik` mode — future domain-based production

Kept as the production path. `session.start_preview_server()` writes
a small dynamic config to
`infra/traefik/dynamic/tasks/task-<task_id>.yml`. Traefik's file
provider picks it up automatically (no reload) and serves
`https://task-<task_id>.preview.<DOMAIN>` → sandbox container port
3000. In this mode the container is **not** published on a host port
— Traefik reaches it on the docker bridge by service name.

The generated config attaches three Traefik middlewares —
`aidev-security-headers`, `aidev-rate-limit`, `aidev-compress` — so
preview URLs get HSTS / X-Content-Type-Options / a basic rate limit
out of the box.

### Cleanup

On session exit:
- `port` mode: `PortPreviewRegistrar.release(task_id)` frees the slot
  immediately; the container teardown removes the host port binding.
- `traefik` mode: `PreviewRegistrar.deregister(task_id)` removes the
  dynamic file and Traefik tears the route down within ~1 second.

In both modes failure of one cleanup step does not skip the others
(container, volume, network are still removed in the `finally`).

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
| `AIDEV_SANDBOX_PREVIEW_MODE`           | `port`                        | `port` (IP-only acceptance) or `traefik` (domain-based)      |
| `AIDEV_SANDBOX_PREVIEW_HOST`           | `127.0.0.1`                   | Public hostname/IP advertised in `port`-mode preview URLs    |
| `AIDEV_SANDBOX_PREVIEW_PORT_RANGE_START` | `31000`                     | First host port the registrar can hand out (`port` mode)     |
| `AIDEV_SANDBOX_PREVIEW_PORT_RANGE_END`   | `31999`                     | Last host port the registrar can hand out (`port` mode)      |
| `AIDEV_SANDBOX_TRAEFIK_DYNAMIC_DIR`    | `/etc/traefik/dynamic/tasks`  | Where to drop per-task router YAML (`traefik` mode)          |
| `AIDEV_SANDBOX_PREVIEW_DOMAIN`         | `preview.aidev.local`         | Base domain for `task-<id>.preview.<DOMAIN>` (`traefik` mode)|
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

## Manual sandbox acceptance checklist

Unit tests run against a faked Docker SDK and prove the *structure* of
the executor (resource caps applied, cleanup ordered, rules engine
called) — but they cannot prove the kernel actually denies a write or
that tinyproxy actually blocks an unknown domain. Run this list
**once on every host** before serving real tasks. Each step is a
pass/fail gate. Do not skip.

### 0. Build and bring up the stack

```sh
docker compose -f infra/docker-compose.yml build sandbox-runner egress-proxy
docker compose -f infra/docker-compose.yml up -d traefik egress-proxy redis db api sandbox-runner
```

In `infra/.env`, for the IP-only acceptance run:

```ini
SANDBOX_EXECUTOR=docker
AIDEV_SANDBOX_MODEL_SERVER_HOST=<your-ollama-or-vllm-host>
AIDEV_SANDBOX_PREVIEW_MODE=port
AIDEV_SANDBOX_PREVIEW_HOST=<ubuntu-vps-ip>
AIDEV_SANDBOX_PREVIEW_PORT_RANGE_START=31000
AIDEV_SANDBOX_PREVIEW_PORT_RANGE_END=31999
```

For the future domain-based production mode instead:

```ini
AIDEV_SANDBOX_PREVIEW_MODE=traefik
AIDEV_SANDBOX_PREVIEW_DOMAIN=<your-preview-domain>
```

### 1. Container safety profile (kernel-level)

Open one task end-to-end through the dashboard; in another shell:

```sh
CID=$(docker ps --filter "label=aidev.sandbox=true" -q | head -1)
docker inspect "$CID" --format '{{.HostConfig.Memory}}'         # → 4294967296   (4g)
docker inspect "$CID" --format '{{.HostConfig.NanoCpus}}'       # → 2000000000   (2 cpus)
docker inspect "$CID" --format '{{.HostConfig.PidsLimit}}'      # → 512
docker inspect "$CID" --format '{{.HostConfig.ReadonlyRootfs}}' # → true
docker inspect "$CID" --format '{{.HostConfig.SecurityOpt}}'    # contains   no-new-privileges:true
docker inspect "$CID" --format '{{.HostConfig.CapDrop}}'        # → [ALL]
docker inspect "$CID" --format '{{.Config.User}}'               # → 10001:10001
docker inspect "$CID" --format '{{.HostConfig.NetworkMode}}'    # → aidev_sandbox_<task-id>
docker network inspect aidev_sandbox_<task-id> --format '{{.Internal}}'  # → true
```

Every line must match the expected value. A miss = stop and
investigate before serving traffic.

### 2. Frontend-first filesystem protection actually blocks writes

While a task is in `FRONTEND_CODING`:

```sh
docker exec -u 10001 "$CID" sh -c 'echo x > /workspace/apps/api/main.py'
#  expect:  sh: ...: Permission denied      (exit code != 0)

docker exec -u 10001 "$CID" sh -c 'echo x > /workspace/infra/docker-compose.yml'
#  expect:  Permission denied

docker exec -u 10001 "$CID" sh -c 'echo x > /workspace/.env'
#  expect:  Permission denied

docker exec -u 10001 "$CID" sh -c 'echo x > /workspace/apps/web/page.tsx'
#  expect:  exit 0   (frontend writes are allowed)
```

Then drive the task to `BACKEND_UNLOCKED` from the dashboard:

```sh
docker exec -u 10001 "$CID" sh -c 'echo x > /workspace/apps/api/main.py'
#  expect:  exit 0   (backend now writable)

docker exec -u 10001 "$CID" sh -c 'echo x > /workspace/.env'
#  expect:  Permission denied   (env files stay locked in EVERY phase)
```

### 3. Egress allowlist actually filters

From inside the sandbox:

```sh
docker exec "$CID" env HTTPS_PROXY=http://aidev-egress-proxy:8888 \
    curl -sS -o /dev/null -w '%{http_code}\n' https://api.github.com/zen
#  expect:  200

docker exec "$CID" env HTTPS_PROXY=http://aidev-egress-proxy:8888 \
    curl -sS -o /dev/null -w '%{http_code}\n' https://attacker.test
#  expect:  403   (or connection-error if DNS is also gated)

# Anchor regression — should NOT match github.com prefix:
docker exec "$CID" env HTTPS_PROXY=http://aidev-egress-proxy:8888 \
    curl -sS -o /dev/null -w '%{http_code}\n' https://github.com.attacker.test
#  expect:  403
```

Bypass attempt — currently *informational only* (cooperative egress):

```sh
docker exec "$CID" sh -c 'unset HTTP_PROXY HTTPS_PROXY; curl --connect-timeout 5 -sS -o /dev/null -w "%{http_code}\n" https://1.1.1.1'
#  expect today:  any 2xx/3xx  (sandbox CAN currently reach raw IPs)
#  expected after v0.2 sidecar-forwarder hardening:  000 (no route)
```

See "Known limitations" below for why this check is informational and
how it will become a hard gate.

### 4. Preview registration is live in <1s

Run the variant that matches `AIDEV_SANDBOX_PREVIEW_MODE`.

#### 4a. `port` mode (IP-only acceptance)

Trigger `start_preview_server()` (the agent-runner does this when
`frontend_qa` passes). Then:

```sh
# Confirm the host published the allocated port (3000 -> 31xxx mapping)
docker port "$CID"
#  expect:  3000/tcp -> 0.0.0.0:31000   (or whichever host port was allocated)

# Read the public URL from the sandbox.preview.registered event
docker exec aidev-redis redis-cli LRANGE aidev:task:<task-id>:events 0 -1 \
    | grep preview.registered
#  expect:  ..."mode":"port"... "public_url":"http://<vps-ip>:31000"...

# Reach it from your laptop
curl -sS -o /dev/null -w '%{http_code}\n' http://<ubuntu-vps-ip>:31000
#  expect:  200   (frontend dev server reachable)
```

Cancel / approve / fail the task → confirm:

```sh
docker ps -f label=aidev.sandbox=true -f task=<task-id>
#  expect:  empty

curl --connect-timeout 3 -sS -o /dev/null -w '%{http_code}\n' http://<ubuntu-vps-ip>:31000
#  expect:  000   (connection refused / no listener)
```

Then start a new task and confirm the registrar **recycles** the port:

```sh
docker port "$NEW_CID"
#  expect:  3000/tcp -> 0.0.0.0:31000   (same slot reused)
```

#### 4b. `traefik` mode (future domain-based production)

Trigger `start_preview_server()`. Then:

```sh
ls -la infra/traefik/dynamic/tasks/
#  expect:  task-<task-id>.yml exists, ~1 KB

curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: task-<task-id>.preview.<DOMAIN>' http://localhost:80
#  expect:  308 redirect to HTTPS (Traefik websecure)

curl -sS -o /dev/null -w '%{http_code}\n' https://task-<task-id>.preview.<DOMAIN>
#  expect:  200   (frontend dev server reachable)
```

Cancel / approve / fail the task → confirm:

```sh
ls infra/traefik/dynamic/tasks/task-<task-id>.yml
#  expect:  No such file or directory

curl -sS -o /dev/null -w '%{http_code}\n' https://task-<task-id>.preview.<DOMAIN>
#  expect:  404 within ~1s
```

### 5. Cleanup on every exit path

Trigger all four termination paths in separate tasks:

| Path                    | Expected after exit                                                                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------ |
| `DONE` (happy path)     | `docker ps -a -f label=aidev.sandbox=true -f task=<id>` → empty; `docker volume ls -f name=<id>` empty; `docker network ls -f name=<id>` empty; `port` mode: allocated host port no longer in `docker port` output; `traefik` mode: preview YAML gone |
| `REJECTED` after FE QA  | Same as above                                                                                          |
| `CANCELLED` mid-run     | Same as above                                                                                          |
| `FAILED` (uncaught exc) | Same as above. The executor `__aexit__` runs cleanup in a `finally`; one failed cleanup step must not skip the others |

If any artefact survives, that is a leak — file an issue and do not
serve more tasks until fixed.

### 6. Timeout enforcement

Submit a task whose plan deliberately sleeps for `AIDEV_SANDBOX_TIMEOUT_SECONDS + 60`:

```sh
# expect in the dashboard:
#   - sandbox.failed event with payload.error = "task deadline exceeded"
#   - task transitions to FAILED
#   - container, volume, network, preview file all removed
```

### 7. Observability sanity

```sh
docker logs aidev-sandbox-runner --tail 50    # structured logs
docker exec aidev-redis redis-cli SUBSCRIBE aidev.sandbox.events &
# trigger a task → expect events: sandbox.starting, sandbox.started,
# repo.cloned, fs_protection.applied, command.ran, preview.registered,
# diff.captured, sandbox.finished
```

All seven sections must pass before flipping `SANDBOX_EXECUTOR=docker`
for production traffic. Keep a dated copy of the run output in
`docs/runs/` so you can show provenance later.

## Known limitations

These are documented gaps discovered during the Ubuntu host acceptance
run (see `docs/runs/2026-05-18-ubuntu-acceptance.md`). Each has a
tracked follow-up before the platform is opened to real project
traffic.

1. **Cooperative egress, not kernel-level (v0.2 follow-up).**
   The sandbox network is a *plain* Docker bridge. We originally tried
   `internal: true` (Docker's "no traffic in or out" mode) but that
   silently disables host-side DNAT, so `-p 31xxx:3000` published
   ports become dead mappings. We then tried
   `com.docker.network.bridge.enable_ip_masquerade=false`, but Docker's
   `network.connect()` on the multi-homed egress proxy rewrote the
   proxy's default gateway to the new (no-masq) bridge, breaking
   tinyproxy's outbound relay across the board.

   The current shape works end-to-end (28/28 acceptance checks pass,
   including egress allow / deny via the proxy and the host-curl
   reachability check on the published preview port) but a determined
   agent could bypass tinyproxy by hitting a raw IP directly. This is
   acceptable for the IP-only acceptance phase because the agent
   runtime is *our own code* (not adversarial), and the platform is
   gated behind operator-CIDR firewall and explicit user approval
   before serving real project tasks.

   The v0.2 hardening: add a per-task port-forwarder sidecar that
   sits on both a plain bridge (so `-p` works for the host port
   mapping) and an `internal: true` sandbox bridge (where the agent
   actually lives). The sidecar forwards `host:31xxx` → `agent:3000`
   via socat / nginx-stream. The egress proxy moves entirely off the
   sandbox bridge; the sandbox container's only route off the
   internal bridge is through the proxy. That restores the
   kernel-level outbound block without breaking previews.

2. **In-memory port pool (single sandbox-runner only).** The
   `PortPreviewRegistrar` is process-local. If the platform ever
   scales to more than one sandbox-runner instance, ports must move
   to Redis. Tracked but not urgent — one runner is plenty until
   real-traffic enablement.

3. **No Playwright recording playback in `port` mode.** Screenshot
   capture works (the agent runs Playwright inside the sandbox and
   we exfiltrate the PNGs); but the live-preview tab in the
   dashboard does not stream video. Not a regression — `traefik`
   mode behaves the same. Tracked for the dashboard team.

4. **GT 730 + CPU-only model.** Discovered by the deployment GPU
   probe. The shipped Ubuntu VPS reports `NVIDIA GeForce GT 730` —
   compute capability 3.5, unsupported by modern CUDA / cuBLAS /
   llama.cpp. Acceptance runs use the Ollama CPU backend with a
   small model (`tinyllama` or `phi3:mini`). Real project tasks
   should switch to a hosted LLM endpoint (added to the egress
   allowlist via `AIDEV_SANDBOX_MODEL_SERVER_HOST`) until the host
   gets a usable GPU.

## Production deployment notes

`DockerSandboxExecutor` needs read/write access to the host Docker
socket — that is the **only** privileged piece. Compose mounts it at
`/var/run/docker.sock:/var/run/docker.sock:rw` for the
`sandbox-runner` service.

Mitigations to remember:

1. **The worker process itself runs as a non-root user** and only the
   executor path code touches the SDK. The Docker socket is not
   exposed to the agent's sandbox containers — only to the worker.
2. **The Traefik dynamic-tasks directory is bind-mounted writable by
   the worker** but read-only-watched by Traefik (file provider). The
   worker is the only writer.
3. **The egress proxy is the only path out of the per-task internal
   network** — losing the proxy = sandbox is fully offline (fail-safe,
   not fail-open).
4. **The sandbox container has no Docker socket and no host bind
   mounts**, so even with root inside the sandbox (which it doesn't
   have — UID 10001 + no-new-privileges), it cannot reach the host
   filesystem or other containers.
5. **The host Docker socket on the operator's box is the trust root.**
   Anyone with write access to the socket can run arbitrary
   containers as root on the host — so keep the VPS itself locked
   down (SSH key only, no password auth, no public Docker API port).

Future hardening tracked in
[`docs/ROADMAP.md`](./ROADMAP.md): rootless Docker, sysbox or gVisor
for the sandbox runtime, dedicated machine for the worker.
