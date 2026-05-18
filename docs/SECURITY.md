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

The sandbox mounts the workspace with a phase-aware overlay:

- `FRONTEND_CODING` phase: backend paths (`apps/api/**`, `migrations/**`,
  `.env*`, `**/secrets/**`, `infra/**`, `**/.github/workflows/deploy*.yml`)
  are mounted **read-only** via overlayfs. A write attempt fails with
  `EROFS`.
- `BACKEND_CODING` phase: the read-only overlay is dropped, but
  `**/.env*` and `**/secrets/**` remain read-only.

This is the layer that protects you even if the rules engine has a bug.

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

The container has no host bind-mounts, no docker socket, and no access to
the host network. Egress is restricted to:

- the model server (`MODEL_BASE_URL`),
- the GitHub API (`api.github.com`, `*.githubusercontent.com`),
- configured package registries (`registry.npmjs.org`, `pypi.org`,
  `files.pythonhosted.org`).

This is implemented by attaching the sandbox network to an outbound
Squid/whitelist HTTP proxy and rejecting all other traffic via iptables.

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
