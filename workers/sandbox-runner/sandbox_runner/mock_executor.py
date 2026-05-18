"""In-process sandbox executor used for development and CI.

Behaviour matches the `SandboxExecutor` interface but runs everything on
the worker host inside a temp directory. The Docker executor is the
production path; the mock keeps unit tests fast and CI hermetic.

The mock implements every method on the `SandboxSession` protocol but
several are intentionally "degraded":

* `clone_repo` runs `git clone` locally (works in CI).
* `set_phase` records the phase but does not actually `chmod -R` —
  layer 3 (fs-protection) only meaningfully applies in the Docker
  executor.
* `capture_screenshots` writes 1×1 PNG stubs so the agent-runner
  pipeline can be exercised without Playwright.
* `start_preview_server` does not start a server; it just records the
  preview URL string so the dashboard mock task lifecycle can show it.
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
from dataclasses import dataclass, field

from aidev_shared import TaskPhase

from sandbox_runner.base import CommandResult
from sandbox_runner.config import SandboxConfig
from sandbox_runner.preview import PortPreviewRegistrar

_PNG_STUB = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
    b"\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass
class _MockSession:
    task_id: str
    workspace_path: str
    preview_url: str | None = None
    current_phase: TaskPhase = TaskPhase.FRONTEND_CODING
    evaluator: object | None = None
    preview_mode: str = "port"
    preview_public_host: str = "127.0.0.1"
    preview_domain: str = "preview.aidev.local"
    preview_host_port: int | None = None
    _phase_history: list[TaskPhase] = field(default_factory=list)

    def set_evaluator(self, evaluator: object) -> None:
        self.evaluator = evaluator

    async def set_phase(self, phase: TaskPhase) -> None:
        self._phase_history.append(self.current_phase)
        self.current_phase = phase

    async def clone_repo(
        self,
        *,
        git_url: str,
        branch: str | None = None,
        depth: int = 1,
    ) -> CommandResult:
        # Clone into a subdirectory of the existing workspace, then
        # promote contents one level up so the workspace itself becomes
        # the repo root (matches the Docker executor contract).
        target = os.path.join(self.workspace_path, "_clone")
        cmd = ["git", "clone", "--depth", str(depth)]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([git_url, target])
        started = time.monotonic()
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            for name in os.listdir(target):
                shutil.move(
                    os.path.join(target, name),
                    os.path.join(self.workspace_path, name),
                )
            shutil.rmtree(target, ignore_errors=True)
        return CommandResult(
            command=" ".join(cmd),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_seconds=time.monotonic() - started,
        )

    async def write_file(self, relative_path: str, content: str) -> int:
        normalised = os.path.normpath(relative_path).replace(os.sep, "/")
        if normalised.startswith("../") or normalised.startswith("/"):
            raise ValueError(
                f"refusing to write outside workspace: {relative_path!r}"
            )
        full = os.path.join(self.workspace_path, normalised)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        await asyncio.to_thread(_write_text, full, content)
        return len(content)

    async def read_file(self, relative_path: str) -> bytes:
        normalised = os.path.normpath(relative_path).replace(os.sep, "/")
        if normalised.startswith("../") or normalised.startswith("/"):
            raise ValueError(
                f"refusing to read outside workspace: {relative_path!r}"
            )
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

    async def capture_diff(self) -> str:
        result = await self.run(
            "git -c color.ui=never diff --no-color --no-ext-diff HEAD"
        )
        return result.stdout

    async def capture_changed_files(self) -> list[str]:
        result = await self.run("git status --porcelain=v1")
        files: list[str] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            files.append(line[3:].split(" -> ")[-1].strip())
        return files

    async def capture_screenshots(
        self,
        *,
        viewports: list[dict[str, int | str]],
        route: str = "/",
        out_dir: str = ".aidev/screenshots",
    ) -> list[str]:
        del route  # mock ignores the route — see module docstring.
        target_dir = os.path.join(self.workspace_path, out_dir)
        await asyncio.to_thread(os.makedirs, target_dir, exist_ok=True)
        paths: list[str] = []
        for vp in viewports:
            name = str(vp["name"])
            full = os.path.join(target_dir, f"{name}.png")
            await asyncio.to_thread(_write_bytes, full, _PNG_STUB)
            paths.append(os.path.join(out_dir, f"{name}.png"))
        return paths

    async def start_preview_server(
        self,
        *,
        command: str | None = None,
        port: int | None = None,
    ) -> str:
        del command, port  # mock does not actually launch a server.
        if self.preview_mode == "port" and self.preview_host_port is not None:
            self.preview_url = (
                f"http://{self.preview_public_host}:{self.preview_host_port}"
            )
        elif self.preview_mode == "port":
            # No port reserved (mock without registrar) — synthesize a
            # placeholder so the dashboard can still render something.
            self.preview_url = f"http://{self.preview_public_host}:31000"
        else:
            self.preview_url = (
                f"https://task-{self.task_id}.{self.preview_domain}"
            )
        return self.preview_url


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write_bytes(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


class MockSandboxExecutor:
    """In-process executor: creates a temp dir per session and cleans up.

    Honours ``SandboxConfig.preview_mode`` so the dashboard sees the
    same preview-URL shape the Docker executor would emit on the same
    deployment. Port allocations are tracked by a shared
    ``PortPreviewRegistrar`` so concurrent mock sessions never collide.
    """

    def __init__(
        self,
        *,
        config: SandboxConfig | None = None,
        port_registrar: PortPreviewRegistrar | None = None,
    ) -> None:
        self._config = config or SandboxConfig.from_env()
        self._port_registrar = port_registrar

    @property
    def config(self) -> SandboxConfig:
        return self._config

    def _get_port_registrar(self) -> PortPreviewRegistrar:
        if self._port_registrar is None:
            self._port_registrar = PortPreviewRegistrar(
                public_host=self._config.preview_public_host,
                port_range_start=self._config.preview_port_range_start,
                port_range_end=self._config.preview_port_range_end,
            )
        return self._port_registrar

    @asynccontextmanager
    async def session(
        self,
        *,
        task_id: str,
        initial_phase: TaskPhase = TaskPhase.FRONTEND_CODING,
    ) -> AsyncIterator[_MockSession]:
        workspace = tempfile.mkdtemp(prefix=f"aidev-mock-{task_id}-")
        mode = (self._config.preview_mode or "port").lower()
        host_port: int | None = None
        registrar: PortPreviewRegistrar | None = None
        if mode == "port":
            registrar = self._get_port_registrar()
            allocation = registrar.allocate(
                task_id=task_id,
                internal_port=self._config.preview_internal_port,
            )
            host_port = allocation.host_port
        try:
            yield _MockSession(
                task_id=task_id,
                workspace_path=workspace,
                current_phase=initial_phase,
                preview_mode=mode,
                preview_public_host=self._config.preview_public_host,
                preview_domain=self._config.preview_domain,
                preview_host_port=host_port,
            )
        finally:
            if registrar is not None:
                registrar.release(task_id)
            shutil.rmtree(workspace, ignore_errors=True)
