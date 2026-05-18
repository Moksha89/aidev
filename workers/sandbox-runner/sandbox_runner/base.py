"""The `SandboxExecutor` interface.

This is the only contract the agent-runner depends on. Switching from
the mock executor to the Docker executor is a single env-var flip
(`SANDBOX_EXECUTOR=docker`).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from aidev_shared import TaskPhase


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


class SandboxSession(Protocol):
    """One-task session inside a `SandboxExecutor`.

    Surfaces every operation the agent pipeline needs:

    * Filesystem: `write_file`, `read_file`, `clone_repo`.
    * Execution: `run`.
    * State: `set_phase`, `set_evaluator` so layer-3 fs protection and
      layer-2 rules-engine validation stay in lock-step with the
      task-lifecycle phase.
    * Capture: `capture_diff`, `capture_changed_files`,
      `capture_screenshots`, `start_preview_server`.

    Implementations that don't really run inside a container (the
    in-process mock) may implement the capture methods in a degraded
    way; the contract is "best-effort, never raises for unsupported".
    """

    task_id: str
    workspace_path: str
    preview_url: str | None
    current_phase: TaskPhase

    def set_evaluator(self, evaluator: object) -> None: ...
    async def set_phase(self, phase: TaskPhase) -> None: ...
    async def clone_repo(
        self, *, git_url: str, branch: str | None = None, depth: int = 1
    ) -> CommandResult: ...
    async def write_file(self, relative_path: str, content: str) -> int: ...
    async def read_file(self, relative_path: str) -> bytes: ...
    async def run(
        self, command: str, *, timeout: int = 600
    ) -> CommandResult: ...
    async def capture_diff(self) -> str: ...
    async def capture_changed_files(self) -> list[str]: ...
    async def capture_screenshots(
        self,
        *,
        viewports: list[dict[str, int | str]],
        route: str = "/",
        out_dir: str = ".aidev/screenshots",
    ) -> list[str]: ...
    async def start_preview_server(
        self, *, command: str | None = None, port: int | None = None
    ) -> str: ...


class SandboxExecutor(Protocol):
    """Factory of `SandboxSession`s.

    Implementations: `MockSandboxExecutor` (development / CI in-process),
    `DockerSandboxExecutor` (production, Docker container per task).
    """

    @asynccontextmanager
    def session(
        self,
        *,
        task_id: str,
        initial_phase: TaskPhase = TaskPhase.FRONTEND_CODING,
    ) -> AsyncIterator[SandboxSession]: ...


def build_executor() -> SandboxExecutor:
    """Return the executor selected by `SANDBOX_EXECUTOR` env var.

    * `mock` (default) — in-process, used for dev + CI.
    * `docker`         — `DockerSandboxExecutor`, the real one.
    """
    kind = os.environ.get("SANDBOX_EXECUTOR", "mock").lower()
    if kind == "mock":
        from sandbox_runner.mock_executor import MockSandboxExecutor

        return MockSandboxExecutor()
    if kind == "docker":
        from sandbox_runner.docker_executor import DockerSandboxExecutor

        return DockerSandboxExecutor()
    raise ValueError(f"Unknown SANDBOX_EXECUTOR={kind!r}")
