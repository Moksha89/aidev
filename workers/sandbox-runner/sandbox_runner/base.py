"""The `SandboxExecutor` interface.

This is the only contract the agent-runner depends on. Switching from
the mock executor to the Docker executor is a configuration change.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


class SandboxSession(Protocol):
    """One-task session inside a `SandboxExecutor`."""

    task_id: str
    workspace_path: str

    async def write_file(self, relative_path: str, content: str) -> int: ...
    async def read_file(self, relative_path: str) -> bytes: ...
    async def run(
        self, command: str, *, timeout: int = 600
    ) -> CommandResult: ...


class SandboxExecutor(Protocol):
    """Factory of `SandboxSession`s.

    Implementations: `MockSandboxExecutor` (v0.1, in-process),
    `DockerSandboxExecutor` (v0.2, Docker container per task).
    """

    @asynccontextmanager
    def session(self, *, task_id: str) -> AsyncIterator[SandboxSession]: ...


def build_executor() -> SandboxExecutor:
    """Return the executor selected by `SANDBOX_EXECUTOR` env var.

    Default: `mock`. The Docker implementation lives in v0.2 — see
    `docs/ARCHITECTURE.md` for the design.
    """
    kind = os.environ.get("SANDBOX_EXECUTOR", "mock").lower()
    if kind == "mock":
        from sandbox_runner.mock_executor import MockSandboxExecutor

        return MockSandboxExecutor()
    if kind == "docker":
        raise NotImplementedError(
            "DockerSandboxExecutor is scheduled for v0.2. "
            "Set SANDBOX_EXECUTOR=mock for the MVP."
        )
    raise ValueError(f"Unknown SANDBOX_EXECUTOR={kind!r}")
