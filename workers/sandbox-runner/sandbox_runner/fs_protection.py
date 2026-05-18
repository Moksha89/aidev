"""Layer-3 of the frontend-first gate: kernel-level filesystem protection.

Layers 1 and 2 live elsewhere:

1. **Prompt layer** — the planner / frontend / QA agents are told which
   paths they may touch in each phase.
2. **Rules-engine layer** — `aidev_rules_engine.Evaluator` re-checks
   every file write against the active `.ai-rules` before the worker
   passes the bytes to the sandbox.

This module is layer 3. After the sandbox container has cloned the
repository, we `chmod -R 0555` the backend / infra / deployment paths
*as root inside the sandbox*. The agent runs as UID 10001 with
`no-new-privileges` and `--read-only` rootfs, so even if layers 1 and 2
were both bypassed by an exploit, a write to `apps/api/**` would still
fail with EACCES at the kernel level.

When the human operator approves the frontend via the dashboard the
executor calls `session.set_phase(BACKEND_UNLOCKED)`, which re-runs the
protection script in "unlock" mode: backend paths flip back to 0755.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from aidev_shared import TaskPhase, is_frontend_phase

# Paths whose write-bit is yanked during frontend phases. The list
# mirrors the deny-list in `.ai-rules/frontend-first.md`; if you change
# one, change the other.
DEFAULT_PROTECTED_PATHS: tuple[str, ...] = (
    "apps/api",
    "workers",
    "infra",
    "docker",
    "migrations",
    "alembic",
    ".github",
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    "packages/rules-engine",
    "packages/github-client",
    "packages/model-client",
)


@dataclass(frozen=True)
class FilesystemProtectionPlan:
    """Output of `plan_for_phase`.

    `lock_paths` are made read-only (0555); `unlock_paths` are restored
    to 0755. Paths that don't exist in the workspace are silently
    skipped at apply time.
    """

    phase: TaskPhase
    lock_paths: tuple[str, ...]
    unlock_paths: tuple[str, ...]


def plan_for_phase(
    phase: TaskPhase,
    *,
    protected_paths: Sequence[str] = DEFAULT_PROTECTED_PATHS,
) -> FilesystemProtectionPlan:
    """Decide which paths must be locked / unlocked for a given phase."""

    if is_frontend_phase(phase):
        return FilesystemProtectionPlan(
            phase=phase,
            lock_paths=tuple(protected_paths),
            unlock_paths=(),
        )
    # Backend / security / PR phases: agent is allowed to touch backend
    # files, so we restore them. Note we still don't "unlock" .env files
    # — secrets stay forbidden by the rules engine in every phase.
    safe_unlock = tuple(p for p in protected_paths if not p.startswith(".env"))
    keep_locked = tuple(p for p in protected_paths if p.startswith(".env"))
    return FilesystemProtectionPlan(
        phase=phase,
        lock_paths=keep_locked,
        unlock_paths=safe_unlock,
    )


def render_protection_script(
    plan: FilesystemProtectionPlan,
    *,
    workspace: str = "/workspace",
) -> str:
    """Render the shell script that applies `plan` inside the sandbox.

    The script is executed as root via `docker exec --user 0` so it has
    permission to flip the bits on agent-owned files. It's intentionally
    POSIX `sh`-compatible (no bashisms) so the sandbox image can stay
    on busybox if we ever shrink it.
    """

    lines = [
        "#!/bin/sh",
        f"# Auto-generated for phase={plan.phase.value}.",
        "set -eu",
        f'WORKSPACE="{workspace}"',
        'cd "$WORKSPACE"',
    ]
    for path in plan.lock_paths:
        safe = _shell_quote(path)
        lines.append(
            f'if [ -e "$WORKSPACE"/{safe} ]; then '
            f'chmod -R a-w,a+rX "$WORKSPACE"/{safe}; fi'
        )
    for path in plan.unlock_paths:
        safe = _shell_quote(path)
        lines.append(
            f'if [ -e "$WORKSPACE"/{safe} ]; then '
            f'chmod -R u+rwX,go+rX "$WORKSPACE"/{safe}; fi'
        )
    lines.append(f'echo "fs-protection applied phase={plan.phase.value}"')
    lines.append("")
    return "\n".join(lines)


def _shell_quote(path: str) -> str:
    """Conservative shell-quoting for path segments.

    Our protected paths are static and well-formed, but we still wrap
    them in single quotes to defend against future entries with shell
    metacharacters.
    """

    return "'" + path.replace("'", "'\\''") + "'"


__all__ = [
    "DEFAULT_PROTECTED_PATHS",
    "FilesystemProtectionPlan",
    "plan_for_phase",
    "render_protection_script",
]
