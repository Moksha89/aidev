"""Docker-in-Docker sandbox executor — the real one.

One ephemeral container per task. Resource caps, non-root user,
read-only root filesystem, no-new-privileges, isolated `internal: true`
network, egress only through the allowlist proxy sidecar.

The executor talks to the host Docker daemon through the `docker` SDK.
The agent-runner consumes the resulting `SandboxSession` through the
`SandboxExecutor` protocol — no code in the agent layer cares whether
the session is backed by the mock or by a real container.

See `docs/SANDBOX_EXECUTOR.md` for the full design and operational
notes (resource caps, allowlist, fs-protection layer).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shlex
import tarfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from aidev_rules_engine import Evaluator
from aidev_shared import TaskPhase

from sandbox_runner.base import CommandResult
from sandbox_runner.config import SandboxConfig
from sandbox_runner.egress import build_allowlist, proxy_env
from sandbox_runner.event_stream import EventStream
from sandbox_runner.fs_protection import (
    plan_for_phase,
    render_protection_script,
)
from sandbox_runner.preview import (
    PortAllocation,
    PortPreviewRegistrar,
    PreviewRegistrar,
    PreviewRoute,
)

logger = logging.getLogger(__name__)


class SandboxLaunchError(RuntimeError):
    """Raised when the executor cannot bring a sandbox up."""


class SandboxCommandError(RuntimeError):
    """Raised when a `docker exec` returns a non-zero exit and the
    caller asked us to surface it as an error rather than a result."""


@dataclass
class _DockerSession:
    """Live handle for one task. Created by `DockerSandboxExecutor`."""

    task_id: str
    workspace_path: str
    container: Any
    config: SandboxConfig
    events: EventStream
    preview_registrar: PreviewRegistrar | None = None
    port_registrar: PortPreviewRegistrar | None = None
    port_allocation: PortAllocation | None = None
    preview_url: str | None = None
    current_phase: TaskPhase = TaskPhase.FRONTEND_CODING
    evaluator: Evaluator | None = None
    _started_at: float = field(default_factory=time.monotonic)

    # ---- public API --------------------------------------------------

    def set_evaluator(self, evaluator: Evaluator) -> None:
        """Attach the rules-engine evaluator parsed from the cloned repo."""

        self.evaluator = evaluator
        self.events.publish(
            task_id=self.task_id,
            kind="evaluator.set",
            payload={"rule_count": len(evaluator.rules)},
        )

    async def set_phase(self, phase: TaskPhase) -> None:
        """Update the in-session phase and re-apply FS protection.

        Calling `set_phase(BACKEND_UNLOCKED)` is what flips backend paths
        from 0555 back to 0755 — the worker invokes it from the API's
        approve-frontend handler.
        """

        previous = self.current_phase
        self.current_phase = phase
        await self._apply_filesystem_protection(phase)
        self.events.publish(
            task_id=self.task_id,
            kind="phase.changed",
            payload={"from": previous.value, "to": phase.value},
        )

    async def clone_repo(
        self,
        *,
        git_url: str,
        branch: str | None = None,
        depth: int = 1,
    ) -> CommandResult:
        """Clone `git_url` into `<workspace>` inside the sandbox.

        After the clone succeeds we re-apply the FS-protection plan so
        backend paths are immediately locked for frontend phases.
        """

        target = self.workspace_path
        cmd_parts = ["git", "clone", "--depth", str(depth)]
        if branch:
            cmd_parts.extend(["--branch", branch])
        cmd_parts.extend([git_url, target])
        result = await self.run(" ".join(shlex.quote(p) for p in cmd_parts))
        if result.returncode == 0:
            await self._apply_filesystem_protection(self.current_phase)
            self.events.publish(
                task_id=self.task_id,
                kind="repo.cloned",
                payload={"git_url": git_url, "branch": branch, "depth": depth},
            )
        else:
            self.events.publish(
                task_id=self.task_id,
                kind="repo.clone_failed",
                payload={
                    "git_url": git_url,
                    "returncode": result.returncode,
                    "stderr": result.stderr[:2048],
                },
            )
        return result

    async def write_file(self, relative_path: str, content: str) -> int:
        """Write `content` to `<workspace>/<relative_path>`.

        Three guards apply:

        1. Path-traversal guard rejects `..` / absolute paths.
        2. The rules engine — if attached — vetoes phase-forbidden writes.
        3. The container's chmod-0555 mask catches anything the first
           two layers missed (EACCES from the kernel).
        """

        normalised = _normalise_relative(relative_path)
        if self.evaluator is not None:
            self.evaluator.assert_write_allowed(normalised, self.current_phase)
        encoded = content.encode("utf-8")
        await asyncio.to_thread(
            _put_file_into_container,
            container=self.container,
            workspace=self.workspace_path,
            relative_path=normalised,
            payload=encoded,
            uid=self.config.agent_uid,
        )
        self.events.publish(
            task_id=self.task_id,
            kind="file.written",
            payload={"path": normalised, "bytes": len(encoded)},
        )
        return len(encoded)

    async def read_file(self, relative_path: str) -> bytes:
        normalised = _normalise_relative(relative_path)
        return await asyncio.to_thread(
            _read_file_from_container,
            container=self.container,
            workspace=self.workspace_path,
            relative_path=normalised,
        )

    async def run(
        self,
        command: str,
        *,
        timeout: int = 600,
        user: int | str | None = None,
    ) -> CommandResult:
        """Execute `command` inside the sandbox.

        Default user is the non-root agent UID; pass `user=0` to run as
        root (only the executor itself does this, e.g. for the chmod
        protection script).
        """

        effective_user = self.config.agent_uid if user is None else user
        deadline = self._started_at + self.config.task_timeout_seconds
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SandboxCommandError(
                f"sandbox task {self.task_id} exceeded "
                f"{self.config.task_timeout_seconds}s timeout"
            )
        capped_timeout = min(timeout, max(1, int(remaining)))
        started = time.monotonic()
        rc, stdout, stderr = await asyncio.to_thread(
            _exec_in_container,
            container=self.container,
            command=command,
            user=str(effective_user),
            workdir=self.workspace_path,
            timeout=capped_timeout,
        )
        duration = time.monotonic() - started
        self.events.publish(
            task_id=self.task_id,
            kind="command.ran",
            payload={
                "command": command,
                "returncode": rc,
                "duration_seconds": round(duration, 3),
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
            },
        )
        return CommandResult(
            command=command,
            returncode=rc,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            duration_seconds=duration,
        )

    async def capture_diff(self) -> str:
        """Return the unified diff of the current workspace vs HEAD."""

        result = await self.run(
            "git -c color.ui=never diff --no-color --no-ext-diff HEAD"
        )
        self.events.publish(
            task_id=self.task_id,
            kind="diff.captured",
            payload={"bytes": len(result.stdout)},
        )
        return result.stdout

    async def capture_changed_files(self) -> list[str]:
        result = await self.run("git status --porcelain=v1")
        files: list[str] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            files.append(line[3:].split(" -> ")[-1].strip())
        self.events.publish(
            task_id=self.task_id,
            kind="files.changed",
            payload={"count": len(files)},
        )
        return files

    async def capture_screenshots(
        self,
        *,
        viewports: list[dict[str, int | str]],
        route: str = "/",
        out_dir: str = ".aidev/screenshots",
    ) -> list[str]:
        """Drive Playwright inside the sandbox and return the paths
        of every screenshot it wrote (relative to the workspace).
        """

        script = _build_playwright_script(
            viewports=viewports, route=route, out_dir=out_dir
        )
        # Drop the script into the container as a regular file so the
        # command line stays short and inspectable in logs.
        await self.write_via_root(".aidev/playwright_capture.py", script)
        result = await self.run(
            "python3 .aidev/playwright_capture.py",
            timeout=600,
        )
        if result.returncode != 0:
            self.events.publish(
                task_id=self.task_id,
                kind="screenshots.failed",
                payload={
                    "returncode": result.returncode,
                    "stderr": result.stderr[:2048],
                },
            )
            return []
        paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        self.events.publish(
            task_id=self.task_id,
            kind="screenshots.captured",
            payload={"count": len(paths), "route": route},
        )
        return paths

    async def write_via_root(self, relative_path: str, content: str) -> int:
        """Like `write_file` but bypasses the rules engine. Used only by
        the executor itself to drop helper scripts (playwright capture,
        fs-protection) into the sandbox.
        """

        normalised = _normalise_relative(relative_path)
        encoded = content.encode("utf-8")
        await asyncio.to_thread(
            _put_file_into_container,
            container=self.container,
            workspace=self.workspace_path,
            relative_path=normalised,
            payload=encoded,
            uid=self.config.agent_uid,
        )
        return len(encoded)

    async def start_preview_server(
        self,
        *,
        command: str | None = None,
        port: int | None = None,
    ) -> str:
        """Launch the frontend dev server inside the sandbox and publish
        the preview URL.

        In ``port`` mode (IP-only acceptance) the URL is
        ``http://<public-host>:<allocated-port>`` and the container's
        published port was reserved before container create, so the
        dev server is reachable as soon as it binds.

        In ``traefik`` mode the registrar writes a dynamic file router
        and the URL is ``https://task-<id>.preview.<DOMAIN>``.
        """

        chosen_port = port or self.config.preview_internal_port
        actual_command = command or (
            f"sh -c 'pnpm install --frozen-lockfile && "
            f"pnpm exec next dev -p {chosen_port}'"
        )
        # Run the dev server detached so this call returns quickly.
        await self.run(
            f"nohup {actual_command} > .aidev/preview.log 2>&1 &",
        )

        if self.port_allocation is not None:
            self.preview_url = self.port_allocation.public_url
            self.events.publish(
                task_id=self.task_id,
                kind="preview.registered",
                payload={
                    "mode": "port",
                    "public_url": self.preview_url,
                    "host_port": self.port_allocation.host_port,
                    "internal_port": chosen_port,
                },
            )
            return self.preview_url

        if self.preview_registrar is None:
            raise SandboxLaunchError(
                "no preview registrar configured for traefik mode"
            )
        backend = f"http://{self.config.container_name(self.task_id)}:{chosen_port}"
        route = PreviewRoute(
            task_id=self.task_id,
            domain=self.config.preview_host(self.task_id),
            backend_url=backend,
        )
        path = await asyncio.to_thread(self.preview_registrar.register, route)
        self.preview_url = f"https://{route.domain}"
        self.events.publish(
            task_id=self.task_id,
            kind="preview.registered",
            payload={
                "mode": "traefik",
                "domain": route.domain,
                "backend_url": backend,
                "dynamic_file": path,
            },
        )
        return self.preview_url

    # ---- internals ---------------------------------------------------

    async def _apply_filesystem_protection(self, phase: TaskPhase) -> None:
        plan = plan_for_phase(phase)
        script = render_protection_script(plan, workspace=self.workspace_path)
        await self.write_via_root(".aidev/fs_protection.sh", script)
        result = await self.run(
            f"sh {self.workspace_path}/.aidev/fs_protection.sh",
            user=0,
        )
        if result.returncode != 0:
            logger.warning(
                "fs-protection script failed for task %s phase=%s rc=%s",
                self.task_id,
                phase.value,
                result.returncode,
            )
        self.events.publish(
            task_id=self.task_id,
            kind="fs_protection.applied",
            payload={
                "phase": phase.value,
                "locked": list(plan.lock_paths),
                "unlocked": list(plan.unlock_paths),
                "returncode": result.returncode,
            },
        )


class DockerSandboxExecutor:
    """Build, launch and tear down one Docker sandbox per task.

    Lifecycle (per `session()`):

    1. Pre-flight: validate config, build the egress allowlist, publish
       a `sandbox.starting` event.
    2. Create a per-task network with `internal: true`. If an egress
       proxy is configured, attach the proxy container to the network.
    3. Create a named volume `aidev-sandbox-vol-<task_id>` for the
       workspace. The volume is mounted at `/workspace` so writes
       survive across `docker exec` calls but vanish when we remove it.
    4. Create the sandbox container with the full safety profile:
       - `read_only=True`, `tmpfs={'/tmp': '...'}`
       - `security_opt=['no-new-privileges:true']`
       - `cap_drop=['ALL']`
       - `user=10001:10001`
       - `mem_limit`, `nano_cpus`, `pids_limit`
       - `environment` includes HTTP(S)_PROXY pointing at the sidecar
    5. Start the container, yield the `_DockerSession`.
    6. On context exit (or timeout / exception):
       - Stop + remove the container with `force=True, v=True`.
       - Remove the volume.
       - Remove the network.
       - Deregister the Traefik preview route.
       - Publish `sandbox.finished` with the final phase.
    """

    def __init__(
        self,
        *,
        config: SandboxConfig | None = None,
        docker_client: Any | None = None,
        event_stream: EventStream | None = None,
        preview_registrar: PreviewRegistrar | None = None,
        port_registrar: PortPreviewRegistrar | None = None,
    ) -> None:
        self._config = config or SandboxConfig.from_env()
        self._client = docker_client
        self._events = event_stream
        self._preview = preview_registrar
        self._port_registrar = port_registrar

    @property
    def config(self) -> SandboxConfig:
        return self._config

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import docker  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — runtime dep
            raise SandboxLaunchError(
                "docker SDK not installed; install `docker>=7,<8`"
            ) from exc
        if self._config.docker_base_url:
            self._client = docker.DockerClient(base_url=self._config.docker_base_url)
        else:
            self._client = docker.from_env()
        return self._client

    def _get_events(self) -> EventStream:
        if self._events is None:
            self._events = EventStream(
                redis_url=self._config.redis_url,
                channel=self._config.event_channel,
            )
        return self._events

    def _get_preview(self) -> PreviewRegistrar:
        if self._preview is None:
            self._preview = PreviewRegistrar(
                dynamic_dir=self._config.traefik_dynamic_dir
            )
        return self._preview

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
    ) -> AsyncIterator[_DockerSession]:
        client = self._get_client()
        events = self._get_events()

        mode = (self._config.preview_mode or "port").lower()
        if mode not in {"port", "traefik"}:
            raise SandboxLaunchError(
                f"unknown preview_mode {mode!r}; expected 'port' or 'traefik'"
            )

        # Allocate the preview slot up-front so port-mode containers can
        # publish their host port at create time.
        port_registrar: PortPreviewRegistrar | None = None
        port_allocation: PortAllocation | None = None
        traefik_registrar: PreviewRegistrar | None = None
        if mode == "port":
            port_registrar = self._get_port_registrar()
            port_allocation = port_registrar.allocate(
                task_id=task_id,
                internal_port=self._config.preview_internal_port,
            )
        else:
            traefik_registrar = self._get_preview()

        events.publish(
            task_id=task_id,
            kind="sandbox.starting",
            payload={
                "image": self._config.image,
                "cpus": self._config.cpus,
                "mem_limit": self._config.mem_limit,
                "pids_limit": self._config.pids_limit,
                "agent_uid": self._config.agent_uid,
                "read_only_root": self._config.read_only_root,
                "timeout_seconds": self._config.task_timeout_seconds,
                "preview_mode": mode,
                "preview_host_port": (
                    port_allocation.host_port if port_allocation else None
                ),
            },
        )

        network = None
        volume = None
        container = None
        try:
            network = await asyncio.to_thread(
                _create_network, client=client, name=self._config.network_name(task_id)
            )
            volume = await asyncio.to_thread(
                _create_volume, client=client, name=self._config.volume_name(task_id)
            )

            allowlist = build_allowlist(
                extra_hosts=self._config.extra_egress_hosts,
                model_server_host=self._config.model_server_host,
            )
            env = {
                "AIDEV_TASK_ID": task_id,
                "AIDEV_TASK_PHASE": initial_phase.value,
                "AIDEV_ALLOWLIST_COUNT": str(len(allowlist)),
            }
            env.update(proxy_env(proxy_url=self._config.egress_proxy_url))

            port_bindings = (
                port_allocation.port_bindings if port_allocation else None
            )
            container = await asyncio.to_thread(
                _create_container,
                client=client,
                config=self._config,
                task_id=task_id,
                volume_name=volume.name,
                network_name=network.name,
                environment=env,
                port_bindings=port_bindings,
            )
            await asyncio.to_thread(container.start)

            # Wire the egress proxy onto our network if it's running on
            # the host. Failures here are non-fatal — they just mean
            # external traffic is blocked, which is the safe default.
            if self._config.egress_proxy_url:
                await asyncio.to_thread(
                    _attach_egress_proxy,
                    client=client,
                    network=network,
                    alias=self._config.egress_proxy_alias,
                )

            session = _DockerSession(
                task_id=task_id,
                workspace_path=self._config.workspace_path,
                container=container,
                config=self._config,
                events=events,
                preview_registrar=traefik_registrar,
                port_registrar=port_registrar,
                port_allocation=port_allocation,
                current_phase=initial_phase,
            )
            events.publish(
                task_id=task_id,
                kind="sandbox.started",
                payload={
                    "container_id": getattr(container, "id", None),
                    "network": network.name,
                    "volume": volume.name,
                    "phase": initial_phase.value,
                    "preview_mode": mode,
                },
            )
            yield session
        except Exception as exc:
            events.publish(
                task_id=task_id,
                kind="sandbox.failed",
                payload={"error": str(exc)[:1024]},
            )
            raise
        finally:
            if port_registrar is not None:
                try:
                    port_registrar.release(task_id)
                except Exception:  # pragma: no cover — best-effort cleanup
                    logger.warning(
                        "port_registrar.release failed for task %s", task_id
                    )
            if traefik_registrar is not None:
                try:
                    traefik_registrar.deregister(task_id)
                except Exception:  # pragma: no cover — best-effort cleanup
                    logger.warning(
                        "preview.deregister failed for task %s", task_id
                    )
            if container is not None:
                try:
                    await asyncio.to_thread(container.remove, force=True, v=True)
                except Exception:
                    logger.warning("container.remove failed for task %s", task_id)
            if volume is not None:
                try:
                    await asyncio.to_thread(volume.remove, force=True)
                except Exception:
                    logger.warning("volume.remove failed for task %s", task_id)
            if network is not None:
                try:
                    await asyncio.to_thread(network.remove)
                except Exception:
                    logger.warning("network.remove failed for task %s", task_id)
            events.publish(
                task_id=task_id,
                kind="sandbox.finished",
                payload={"task_id": task_id},
            )


# ---- module-level helpers (synchronous, run in `to_thread`) ----------


def _normalise_relative(path: str) -> str:
    """Reject path-traversal and absolute paths; normalise separators."""

    normalised = os.path.normpath(path).replace(os.sep, "/")
    if normalised.startswith("../") or normalised == ".." or normalised.startswith("/"):
        raise ValueError(f"refusing to operate outside workspace: {path!r}")
    return normalised


def _create_network(*, client: Any, name: str) -> Any:
    """Create the per-task internal network (idempotent on name)."""

    existing = client.networks.list(names=[name])
    if existing:
        return existing[0]
    return client.networks.create(name=name, driver="bridge", internal=True)


def _create_volume(*, client: Any, name: str) -> Any:
    existing = client.volumes.list(filters={"name": name})
    for vol in existing:
        if vol.name == name:
            return vol
    return client.volumes.create(name=name)


def _create_container(
    *,
    client: Any,
    config: SandboxConfig,
    task_id: str,
    volume_name: str,
    network_name: str,
    environment: dict[str, str],
    port_bindings: dict[str, int] | None = None,
) -> Any:
    """Create the sandbox container with the full safety profile.

    Notes:
    * `nano_cpus` is the SDK's unit for `--cpus`: 1 CPU = 1e9.
    * `tmpfs` is required when `read_only=True` so /tmp is still writable
      for the agent process (Playwright caches, pip wheels, etc.).
    * We do NOT bind-mount the host docker socket; the container has
      no way to reach the host daemon, period.
    * `port_bindings` is only passed for ``preview_mode='port'`` —
      Traefik mode keeps the container off the host port table.
    """

    nano_cpus = int(config.cpus * 1_000_000_000)
    create_kwargs: dict[str, Any] = {
        "image": config.image,
        "name": config.container_name(task_id),
        "command": ["sleep", "infinity"],
        "user": f"{config.agent_uid}:{config.agent_uid}",
        "working_dir": config.workspace_path,
        "environment": environment,
        "network": network_name,
        "read_only": config.read_only_root,
        "tmpfs": {
            "/tmp": "rw,nosuid,nodev,exec,size=512m",
            "/home/agent/.cache": "rw,nosuid,nodev,size=512m",
        },
        "volumes": {
            volume_name: {"bind": config.workspace_path, "mode": "rw"},
        },
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "mem_limit": config.mem_limit,
        "nano_cpus": nano_cpus,
        "pids_limit": config.pids_limit,
        "labels": {
            "com.aidev.task": task_id,
            "com.aidev.role": "sandbox",
        },
    }
    if port_bindings:
        create_kwargs["ports"] = port_bindings
    return client.containers.create(**create_kwargs)


def _attach_egress_proxy(*, client: Any, network: Any, alias: str) -> None:
    """Wire the egress proxy container onto the per-task network."""

    try:
        proxy = client.containers.get(alias)
    except Exception:
        logger.warning(
            "egress proxy container %s not found; "
            "sandbox will have no external access",
            alias,
        )
        return
    try:
        network.connect(proxy, aliases=[alias])
    except Exception as exc:
        # Already attached is fine; everything else logs.
        msg = str(exc).lower()
        if "already" not in msg:
            logger.warning("could not attach egress proxy to network: %s", exc)


def _put_file_into_container(
    *,
    container: Any,
    workspace: str,
    relative_path: str,
    payload: bytes,
    uid: int,
) -> None:
    """Tar-stream `payload` into `<workspace>/<relative_path>`."""

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=relative_path)
        info.size = len(payload)
        info.mode = 0o644
        info.uid = uid
        info.gid = uid
        tar.addfile(info, io.BytesIO(payload))
    buf.seek(0)
    # Make sure intermediate dirs exist; ignore errors if it's just /.
    parent_dir = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
    if parent_dir:
        container.exec_run(
            cmd=["mkdir", "-p", f"{workspace}/{parent_dir}"],
            user=str(uid),
        )
    ok = container.put_archive(path=workspace, data=buf.getvalue())
    if not ok:
        raise SandboxCommandError(
            f"put_archive returned False for {relative_path!r}"
        )


def _read_file_from_container(
    *,
    container: Any,
    workspace: str,
    relative_path: str,
) -> bytes:
    """Read a single file out via `get_archive` and untar it."""

    target = f"{workspace}/{relative_path}"
    bits, _stat = container.get_archive(target)
    buf = io.BytesIO()
    for chunk in bits:
        buf.write(chunk)
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        member_name = relative_path.rsplit("/", 1)[-1]
        member = tar.getmember(member_name)
        fileobj = tar.extractfile(member)
        if fileobj is None:
            raise SandboxCommandError(
                f"could not extract {relative_path!r} from container archive"
            )
        return fileobj.read()


def _exec_in_container(
    *,
    container: Any,
    command: str,
    user: str,
    workdir: str,
    timeout: int,  # noqa: ARG001 — surfaced via task-level deadline upstream
) -> tuple[int, bytes, bytes]:
    """Run `command` inside the container with stdout/stderr demuxed."""

    exit_code, output = container.exec_run(
        cmd=["sh", "-lc", command],
        user=user,
        workdir=workdir,
        demux=True,
        environment={
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        },
    )
    if isinstance(output, tuple):
        stdout, stderr = output
    else:
        stdout, stderr = output, b""
    return int(exit_code or 0), stdout or b"", stderr or b""


def _build_playwright_script(
    *,
    viewports: list[dict[str, int | str]],
    route: str,
    out_dir: str,
) -> str:
    """Generate the Python entrypoint that drives Playwright in-sandbox.

    Lives in `<workspace>/.aidev/playwright_capture.py`. It expects the
    dev server to already be reachable at `http://127.0.0.1:<port>`
    (preview port from `SandboxConfig`) and prints one screenshot path
    per line on stdout.
    """

    import json

    encoded = json.dumps(
        {
            "viewports": viewports,
            "route": route,
            "out_dir": out_dir,
        }
    )
    return _PLAYWRIGHT_TEMPLATE.replace("__AIDEV_CONFIG_JSON__", encoded)


_PLAYWRIGHT_TEMPLATE = '''
"""Auto-generated by sandbox_runner.docker_executor."""
from __future__ import annotations

import json
import os
import sys
import time

CONFIG = json.loads("""__AIDEV_CONFIG_JSON__""")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed", file=sys.stderr)
        return 2

    base = os.environ.get("AIDEV_PREVIEW_BASE", "http://127.0.0.1:3000")
    out_dir = os.path.abspath(CONFIG["out_dir"])
    os.makedirs(out_dir, exist_ok=True)

    paths: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            for vp in CONFIG["viewports"]:
                ctx = browser.new_context(
                    viewport={
                        "width": int(vp["width"]),
                        "height": int(vp["height"]),
                    }
                )
                page = ctx.new_page()
                url = base.rstrip("/") + CONFIG["route"]
                # Tolerate slow first paints from cold dev servers.
                for attempt in range(5):
                    try:
                        page.goto(url, wait_until="networkidle", timeout=15_000)
                        break
                    except Exception:
                        if attempt == 4:
                            raise
                        time.sleep(2)
                target = os.path.join(out_dir, f"{vp['name']}.png")
                page.screenshot(path=target, full_page=True)
                paths.append(target)
                ctx.close()
        finally:
            browser.close()
    for screenshot_path in paths:
        print(screenshot_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


__all__ = [
    "DockerSandboxExecutor",
    "SandboxCommandError",
    "SandboxLaunchError",
]
