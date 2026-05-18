"""In-process sandbox executor used for the MVP.

Behaviour matches the `SandboxExecutor` interface but runs everything on
the worker host inside a temp directory. The Docker executor will swap
in at v0.2; agent-runner code does not need to change.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sandbox_runner.base import CommandResult


@dataclass
class _MockSession:
    task_id: str
    workspace_path: str

    async def write_file(self, relative_path: str, content: str) -> int:
        normalised = os.path.normpath(relative_path).replace(os.sep, "/")
        if normalised.startswith("../") or normalised.startswith("/"):
            raise ValueError(f"refusing to write outside workspace: {relative_path!r}")
        full = os.path.join(self.workspace_path, normalised)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        await asyncio.to_thread(_write_text, full, content)
        return len(content)

    async def read_file(self, relative_path: str) -> bytes:
        normalised = os.path.normpath(relative_path).replace(os.sep, "/")
        if normalised.startswith("../") or normalised.startswith("/"):
            raise ValueError(f"refusing to read outside workspace: {relative_path!r}")
        full = os.path.join(self.workspace_path, normalised)
        return await asyncio.to_thread(_read_bytes, full)

    async def run(self, command: str, *, timeout: int = 600) -> CommandResult:
        started = time.monotonic()
        proc = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,  # noqa: S603 — host-side mock executor only
            cwd=self.workspace_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_seconds=time.monotonic() - started,
        )


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


class MockSandboxExecutor:
    """In-process executor: creates a temp dir per session and cleans up."""

    @asynccontextmanager
    async def session(self, *, task_id: str) -> AsyncIterator[_MockSession]:
        workspace = tempfile.mkdtemp(prefix=f"aidev-mock-{task_id}-")
        try:
            yield _MockSession(task_id=task_id, workspace_path=workspace)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
