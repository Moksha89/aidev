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
--pids-limit 512
--cpus 2
--memory 4g
--network aidev_sandbox          # isolated bridge
```

The sandbox container has no host bind-mounts, no docker socket
inside, and no host network access — it joins a per-task
`internal: true` Docker network whose only egress is the
`aidev-egress-proxy` tinyproxy sidecar. The proxy applies an anchored
regex allowlist (deny-by-default) covering:

- the model server (`AIDEV_SANDBOX_MODEL_SERVER_HOST`),
- GitHub (`*.github.com`, `*.githubusercontent.com`),
- npm / pnpm / yarn registries (`registry.npmjs.org`, `*.npmjs.org`,
  `registry.yarnpkg.com`),
- PyPI / Poetry (`pypi.org`, `*.pythonhosted.org`),
- Debian / Ubuntu OS mirrors.

See [`docs/SANDBOX_EXECUTOR.md`](./SANDBOX_EXECUTOR.md) for the proxy
design and how to add hosts.

### Layer 5 — Process

The sandbox entrypoint runs as the `agent` user. It cannot `sudo`, cannot
`chmod +s`, and cannot mount filesystems. Even if RCE is achieved inside
the container, escalation requires a kernel exploit.

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
