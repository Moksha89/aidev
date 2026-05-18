"""DockerSandboxExecutor — v0.2 placeholder.

This file documents the planned implementation so reviewers can see the
shape of the work without us shipping unfinished, dangerous code.
The MVP uses `MockSandboxExecutor`; this class will be turned on by
setting `SANDBOX_EXECUTOR=docker` once the Dockerfile and resource caps
are reviewed.

See `docs/ARCHITECTURE.md` and the Docker sandbox proposal in the PR
description for full design details.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sandbox_runner.base import SandboxSession


class DockerSandboxExecutor:
    """Planned for v0.2.

    Configuration that the executor will apply when activated:

    - image: `aidev/sandbox:latest` (built from `docker/Dockerfile.sandbox`)
    - network: dedicated `aidev_sandbox` bridge, egress restricted to
      the model server, github.com, and the configured package mirrors.
    - user: non-root UID 10001 inside the container.
    - read_only: True; writes only allowed under `/workspace` (tmpfs
      mount of the per-task named volume).
    - cap_drop: ALL; no `--privileged`.
    - security_opt: `no-new-privileges`, seccomp `default`, apparmor
      `docker-default`.
    - mem_limit: `4g`, `cpus: 2`, `pids_limit: 512`.
    - timeout: 30 minutes hard cap per session.

    The session API matches `_MockSession` so agent-runner does not
    care which executor is active.
    """

    @asynccontextmanager
    async def session(self, *, task_id: str) -> AsyncIterator[SandboxSession]:
        del task_id
        raise NotImplementedError(
            "DockerSandboxExecutor will be enabled in v0.2 once the "
            "sandbox image, egress whitelist proxy, and resource caps "
            "are reviewed. Use SANDBOX_EXECUTOR=mock for the MVP."
        )
        # The yield is unreachable but required for type-checker happiness.
        yield  # pragma: no cover
