"""Sanity tests for the mock sandbox executor."""

from __future__ import annotations

import asyncio
import os

import pytest
from aidev_shared import TaskPhase

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


@pytest.mark.asyncio
async def test_set_phase_tracks_current_phase() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="t5") as sandbox:
        assert sandbox.current_phase == TaskPhase.FRONTEND_CODING
        await sandbox.set_phase(TaskPhase.AWAITING_APPROVAL)
        assert sandbox.current_phase == TaskPhase.AWAITING_APPROVAL
        await sandbox.set_phase(TaskPhase.BACKEND_UNLOCKED)
        assert sandbox.current_phase == TaskPhase.BACKEND_UNLOCKED


@pytest.mark.asyncio
async def test_initial_phase_can_be_overridden() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(
        task_id="t6", initial_phase=TaskPhase.BACKEND_CODING
    ) as sandbox:
        assert sandbox.current_phase == TaskPhase.BACKEND_CODING


@pytest.mark.asyncio
async def test_capture_screenshots_writes_stub_pngs() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="t7") as sandbox:
        paths = await sandbox.capture_screenshots(
            viewports=[
                {"name": "mobile-375", "width": 375, "height": 812},
                {"name": "desktop-1280", "width": 1280, "height": 720},
            ],
            route="/",
        )
        assert paths == [
            ".aidev/screenshots/mobile-375.png",
            ".aidev/screenshots/desktop-1280.png",
        ]
        for rel in paths:
            full = os.path.join(sandbox.workspace_path, rel)
            assert os.path.exists(full)
            with open(full, "rb") as fh:
                assert fh.read().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_start_preview_server_records_url() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="abc") as sandbox:
        assert sandbox.preview_url is None
        url = await sandbox.start_preview_server()
        assert url == "https://task-abc.preview.aidev.local"
        assert sandbox.preview_url == url


@pytest.mark.asyncio
async def test_capture_changed_files_after_git_init() -> None:
    executor = MockSandboxExecutor()
    async with executor.session(task_id="t8") as sandbox:
        # Bootstrap a tiny repo so git status returns deterministic data.
        await sandbox.run(
            "git init -q && git config user.email a@b && "
            "git config user.name a && git commit --allow-empty -qm init"
        )
        await sandbox.write_file("new.txt", "hello")
        files = await sandbox.capture_changed_files()
        assert "new.txt" in files


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(test_write_then_read_file())
