"""Sanity tests for the mock sandbox executor."""

from __future__ import annotations

import asyncio
import os

import pytest

from sandbox_runner import MockSandboxExecutor


@pytest.mark.asyncio
async def test_write_then_read_file() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="t1") as sandbox:
        n = await sandbox.write_file("hello.txt", "world\n")
        assert n == 6
        contents = await sandbox.read_file("hello.txt")
        assert contents == b"world\n"


@pytest.mark.asyncio
async def test_run_command_succeeds() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="t2") as sandbox:
        result = await sandbox.run("echo hi")
        assert result.returncode == 0
        assert "hi" in result.stdout


@pytest.mark.asyncio
async def test_workspace_cleanup() -> None:
    executor = MockSandboxExecutor()
    workspace_path: str | None = None
    async with executor.session(task_id="t3") as sandbox:
        workspace_path = sandbox.workspace_path
        assert os.path.isdir(workspace_path)
    # workspace must be cleaned up on session exit
    assert not os.path.exists(workspace_path)


@pytest.mark.asyncio
async def test_refuses_path_traversal() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="t4") as sandbox:
        with pytest.raises(ValueError):
            await sandbox.write_file("../escape.txt", "nope")
        with pytest.raises(ValueError):
            await sandbox.read_file("/etc/passwd")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(test_write_then_read_file())
