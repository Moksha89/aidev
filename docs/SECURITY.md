# Security

This document describes the security model of the AI Developer platform.
It is opinionated — if you disagree with a choice, fork the rules engine
rather than punching holes in the sandbox.

## Threat model

The platform must remain safe against three adversaries:

1. **A buggy or hallucinating agent** that writes the wrong files.
2. **A jailbroken agent** that has been prompt-injected into trying to
   exfiltrate data or modify forbidden files.
3. **A malicious user** (operator) trying to escalate the agent's
   privileges beyond what the rules allow.

The platform does **not** defend against a malicious host operator with
root on the box; that is out of scope.

## Defence layers

### Layer 1 — Prompt

Every agent system prompt includes the active `.ai-rules` content and a
hard restriction stating which paths the agent may write to in the current
phase. This is necessary but **not sufficient** — a prompt is not a
security boundary.

### Layer 2 — Rules engine

Before any file is written to the workspace, the agent-runner calls
`rules_engine.Evaluator.is_write_allowed(path, phase, rules)`. Violations
abort the agent step and surface in the dashboard with a human-readable
reason. The evaluator is pure, total, and unit-tested.

### Layer 3 — Filesystem

After the sandbox clones the repo, the executor runs a generated shell
script **as root inside the container** that flips backend paths to
read-only using `chmod -R a-w,a+rX`:

- `FRONTEND_CODING` / `FRONTEND_QA` / `AWAITING_APPROVAL`: backend paths
  (`apps/api/**`, `workers/**`, `infra/**`, `docker/**`, `migrations/**`,
  `alembic/**`, `.github/**`, `.env*`, `packages/{rules-engine,github-client,model-client}/**`)
  are read-only. The agent runs as a non-root UID with
  `no-new-privileges` and a read-only rootfs, so any write attempt
  fails with `EACCES` at the kernel level.
- `BACKEND_UNLOCKED` / `BACKEND_CODING` / `SECURITY_REVIEW`: backend
  paths are restored to `u+rwX,go+rX`, but `.env*` stays locked in
  every phase — secrets are forbidden post-approval too.

The protected path list and shell script are emitted by
`sandbox_runner.fs_protection`. See
[`docs/SANDBOX_EXECUTOR.md`](./SANDBOX_EXECUTOR.md) for the full
design. This is the layer that protects you even if the rules engine
has a bug.

### Layer 4 — Container

Each task runs in its own Docker container with:

```
--user 10001:10001               # non-root
--read-only                      # root FS is read-only
--tmpfs /tmp:size=512m,exec
--security-opt no-new-privileges
--cap-drop ALL
--cap-add CHOWN --cap-add FOWNER # minimum for fs_protection chmods
--pids-limit 512
--cpus 2
--memory 4g
--network aidev_sandbox_<task>   # internal=true, NO default gateway
                                 # NO host port bindings (forwarder owns them)
```

The sandbox container has no host bind-mounts, no docker socket
inside, no host network access, and **no host port bindings of its
own**. Host preview ports are published by a per-task `forwarder`
sidecar that lives on a separate plain bridge and proxies traffic over
the internal sandbox network.

### Layer 5 — Kernel-enforced egress (v0.2)

Per-task network layout (see
[`docs/SANDBOX_EXECUTOR.md#v02-network-layout`](./SANDBOX_EXECUTOR.md#v02-network-layout)
for the full diagram):

```
   aidev_pub_<task>           plain bridge      forwarder + docker-proxy live here
   aidev_sandbox_<task>       internal=true     agent + egress-proxy alias live here
```

The agent container has **only** the internal bridge as its NIC.
Because `internal: true` installs no MASQUERADE and no default
gateway, the kernel's `fib_lookup` refuses every off-bridge address.
A `curl https://1.1.1.1` from the agent fails with `Network is
unreachable` even when every proxy env var has been unset. This is
"kernel-enforced": it is not policy or a guard process, it is the
absence of a routing-table entry for any destination off the bridge.

The shared `aidev-egress-proxy` (tinyproxy sidecar) is then attached
to the same internal sandbox bridge as a *second* NIC. Its primary
NIC stays on `infra_default`, where it has its own default route to
the internet; the secondary internal attachment is the agent's only
hop. The proxy applies an anchored regex allowlist (deny-by-default)
covering:

- the model server (`AIDEV_SANDBOX_MODEL_SERVER_HOST`),
- GitHub (`*.github.com`, `*.githubusercontent.com`),
- npm / pnpm / yarn registries (`registry.npmjs.org`, `*.npmjs.org`,
  `registry.yarnpkg.com`),
- PyPI / Poetry (`pypi.org`, `*.pythonhosted.org`),
- Debian / Ubuntu OS mirrors.

Two doors must both be open before bytes leave the host:

1. **Kernel door** — must have a route. The agent has none for
   off-bridge addresses.
2. **Proxy door** — even on-bridge, only the egress-proxy alias
   forwards anywhere; it enforces the allowlist.

See [`docs/SANDBOX_EXECUTOR.md`](./SANDBOX_EXECUTOR.md) for the proxy
design and how to add hosts.

### Layer 5 — Process

The sandbox entrypoint runs as the `agent` user. It cannot `sudo`, cannot
`chmod +s`, and cannot mount filesystems. Even if RCE is achieved inside
the container, escalation requires a kernel exploit.

### Layer 6 — Docker socket gatekeeper (v0.3)

The `sandbox-runner` worker drives Docker through a filtering proxy
instead of holding the host socket directly.

```
sandbox-runner ──▶ tcp://docker-socket-proxy:2375 ──▶ /var/run/docker.sock (host)
                          (allowlist filter)               (ro mount, proxy only)
```

* The worker no longer bind-mounts `/var/run/docker.sock`. That bind
  used to mean "a bug in the worker = root on the host"; it is gone.
* The worker connects via `DOCKER_HOST=tcp://docker-socket-proxy:2375`
  on the compose network. The proxy port is not published on the host.
* The proxy itself runs the `tecnativa/docker-socket-proxy:0.2.0`
  image with `read_only: true`, `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, and the host socket
  mounted **read-only**. It is the only container in the stack that
  can see `/var/run/docker.sock`.
* Allowed Engine API surfaces (CONTAINERS, NETWORKS, VOLUMES, EXEC,
  IMAGES, plus PING and VERSION for the SDK handshake) cover exactly
  what `DockerSandboxExecutor` actually calls.
* Everything else returns **HTTP 403** at the proxy: SWARM, SERVICES,
  TASKS, NODES, SECRETS, CONFIGS, PLUGINS, SYSTEM (incl.
  `/system/df`, `/events`), BUILD, COMMIT, AUTH, DISTRIBUTION,
  SESSION, INFO.

A run-time probe (`workers/sandbox-runner/scripts/pass2_docker.py`,
section 0a) calls each blocked endpoint against the live proxy and
asserts 403. A static probe
(`tests/test_docker_executor.py::test_docker_socket_proxy_service_exists_with_hardened_policy`)
asserts the compose file still encodes this contract at PR review
time — flips like `BUILD=1` or `SWARM=1` fail CI before reaching the
VPS.

**What this still does NOT defend against:**

* A bug in *Tecnativa's filter logic itself*. The proxy is small
  (a single haproxy config) but it is in the trusted path.
* Misuse of an **allowed** endpoint — e.g. `POST /containers/create`
  with `HostConfig.Privileged: true`. That escape is what
  [`docs/ROOTLESS_DOCKER.md`](./ROOTLESS_DOCKER.md) discusses as the
  v0.4 mitigation.
* An attacker who already has shell on `sandbox-runner` and can
  craft Engine API calls; the proxy reduces blast radius but does
  not eliminate it.

See [`docs/ROOTLESS_DOCKER.md`](./ROOTLESS_DOCKER.md) for the
feasibility analysis of rootless Docker as the next layer beyond
v0.3.

## Secret management

- `.env` files are loaded via `pydantic-settings` and never logged.
- The dashboard masks secret fields by default; reveal requires re-auth.
- GitHub tokens and model-server keys are stored encrypted-at-rest using
  `cryptography.fernet` with a key derived from `AIDEV_SECRET_KEY`.
- The agent prompt never sees raw tokens — only a placeholder
  `{{GITHUB_TOKEN}}` that is substituted at HTTP send time by the
  github-client package.

## Audit log

All state transitions and human approvals are recorded:

- `task_approvals` — every approve/reject decision with `actor_user_id`,
  `actor_ip`, `actor_user_agent`, and `decision_reason`.
- `task_logs` — append-only structured log of every agent action,
  rule check, and tool call.
- The audit log is kept for `AUDIT_RETENTION_DAYS` (default: 365).

## Reporting a vulnerability

Email security@<your-domain> or open a private security advisory on the
GitHub repository. Please do not file public issues for security bugs.

## What is NOT defended

These are explicit non-goals; assume they are possible and design around
them:

- An operator on the host can read the workspace volume.
- The model server can see every prompt and response.
- A user with `admin` role can override the rules engine via
  `/settings/rules` — the override is logged and an org admin is
  notified.
