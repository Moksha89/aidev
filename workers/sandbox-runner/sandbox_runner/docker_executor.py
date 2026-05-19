"""Docker-in-Docker sandbox executor — the real one (v0.2 layout).

One ephemeral *agent* container per task plus a per-task *forwarder*
sidecar. The agent lives on an ``internal: true`` bridge (no default
gateway, no MASQUERADE, no direct internet route). The forwarder sits
on both that internal bridge AND a per-task plain bridge that absorbs
the host's ``-p 31xxx:3000`` mapping, so IP-only previews keep working.

Network picture per task::

    host :31xxx ────────────────► docker-proxy
                                       │
                            aidev_pub_<task>  (plain bridge, MASQUERADE)
                                       │
                              [forwarder sidecar]
                                       │
                            aidev_sandbox_<task>  (internal: true, NO gw)
                          ┌────────────┼────────────────────┐
                     [agent :3000]                    [egress-proxy alias]
                                                            │
                                              infra_default (plain bridge)
                                                            │
                                                       internet (allowlist)

The egress-proxy container itself lives on ``infra_default`` (which is
where it gets its default route to the internet). It is then attached
as a *second* NIC to each per-task ``aidev_sandbox_<task>`` network via
``network.connect()``. Empirically (and per the docker SDK code path),
attaching an ``internal: true`` network as an additional NIC does NOT
rewrite the container's default gateway — the new network simply has
no gateway, so the kernel keeps the existing default route. The agent
reaches the proxy by docker DNS over L2 on the internal subnet; the
proxy reaches the internet over its primary NIC.

Resource caps, non-root user, read-only root filesystem,
``no-new-privileges``, and the frontend-first FS protection layer all
carry over unchanged from v0.1/PR #4. See ``docs/SANDBOX_EXECUTOR.md``
for the full operational checklist.
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
    2. Create TWO per-task networks:
       * ``aidev_pub_<id>`` — plain bridge for the forwarder sidecar
         (host published port lives here).
       * ``aidev_sandbox_<id>`` — ``internal: true`` bridge for the
         agent + egress-proxy multihome.
       If an egress proxy is configured, attach the proxy container to
       the sandbox network.
    3. Create a named volume `aidev-sandbox-vol-<task_id>` for the
       workspace. The volume is mounted at `/workspace` so writes
       survive across `docker exec` calls but vanish when we remove it.
    4. Create the agent container on the *internal* network only with
       the full safety profile:
       - `read_only=True`, `tmpfs={'/tmp': '...'}`
       - `security_opt=['no-new-privileges:true']`
       - `cap_drop=['ALL']` + minimum `cap_add=['CHOWN','FOWNER']`
       - `user=10001:10001`
       - `mem_limit`, `nano_cpus`, `pids_limit`
       - `environment` includes HTTP(S)_PROXY pointing at the sidecar
       - NO host port bindings — the forwarder handles those.
    5. Create the forwarder container on the *pub* network with the
       host port published, then connect it to the *internal*
       network so it can reach the agent.
    6. Start both containers, yield the `_DockerSession`.
    7. On context exit (or timeout / exception):
       - Stop + remove the forwarder.
       - Disconnect the egress-proxy from the internal network.
       - Stop + remove the agent container with `force=True, v=True`.
       - Remove the volume.
       - Remove the internal network, then the pub network.
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

        sandbox_network = None
        pub_network = None
        volume = None
        container = None
        forwarder = None
        try:
            # Sandbox network is internal=true; agent lives here. Pub
            # network is a plain bridge; forwarder lives there with the
            # published host port.
            sandbox_network = await asyncio.to_thread(
                _create_sandbox_network,
                client=client,
                name=self._config.network_name(task_id),
            )
            pub_network = await asyncio.to_thread(
                _create_public_network,
                client=client,
                name=self._config.public_network_name(task_id),
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

            # The agent container is *never* on the pub network and
            # *never* publishes a host port. The forwarder owns both.
            container = await asyncio.to_thread(
                _create_container,
                client=client,
                config=self._config,
                task_id=task_id,
                volume_name=volume.name,
                network_name=sandbox_network.name,
                environment=env,
            )
            await asyncio.to_thread(container.start)

            # Wire the egress proxy onto our sandbox (internal) network
            # so the agent can reach it by DNS alias. The proxy's
            # default gateway stays on infra_default — attaching an
            # internal network as a second NIC does not rewrite it.
            # Failures here are non-fatal: the agent will simply have
            # no working egress, which is the safe default.
            if self._config.egress_proxy_url:
                await asyncio.to_thread(
                    _attach_egress_proxy,
                    client=client,
                    network=sandbox_network,
                    alias=self._config.egress_proxy_alias,
                )

            # Forwarder sidecar — only created in port mode; traefik
            # mode reaches the agent on the docker bridge directly.
            if mode == "port" and port_allocation is not None:
                forwarder = await asyncio.to_thread(
                    _create_forwarder,
                    client=client,
                    config=self._config,
                    task_id=task_id,
                    pub_network_name=pub_network.name,
                    sandbox_network_name=sandbox_network.name,
                    agent_container_name=self._config.container_name(task_id),
                    agent_port=self._config.preview_internal_port,
                    port_bindings=port_allocation.port_bindings,
                )
                await asyncio.to_thread(forwarder.start)

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
                    "sandbox_network": sandbox_network.name,
                    "public_network": pub_network.name,
                    "forwarder": (
                        getattr(forwarder, "name", None) if forwarder else None
                    ),
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
            # Forwarder first: it's the only thing on the pub network,
            # so removing it lets us drop the pub network cleanly.
            if forwarder is not None:
                try:
                    await asyncio.to_thread(
                        forwarder.remove, force=True, v=True
                    )
                except Exception:
                    logger.warning(
                        "forwarder.remove failed for task %s", task_id
                    )
            # Disconnect the egress proxy from the sandbox network
            # before removing it; Docker refuses to remove a network
            # that still has active endpoints.
            if sandbox_network is not None and self._config.egress_proxy_url:
                try:
                    await asyncio.to_thread(
                        _detach_egress_proxy,
                        client=client,
                        network=sandbox_network,
                        alias=self._config.egress_proxy_alias,
                    )
                except Exception:
                    logger.warning(
                        "egress proxy detach failed for task %s", task_id
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
            # Disconnect any still-attached containers (egress proxy on
            # sandbox_network, lingering forwarder on pub_network) so
            # ``network.remove`` does not error with "has active
            # endpoints". Best-effort; ``remove`` is still wrapped.
            for _net_label, _net in (
                ("sandbox_network", sandbox_network),
                ("pub_network", pub_network),
            ):
                if _net is None:
                    continue
                try:
                    await asyncio.to_thread(_net.reload)
                    attached = (_net.attrs.get("Containers") or {}).keys()
                    for cid in list(attached):
                        try:
                            await asyncio.to_thread(
                                _net.disconnect, cid, force=True
                            )
                        except Exception:
                            logger.warning(
                                "%s.disconnect failed for task %s container %s",
                                _net_label,
                                task_id,
                                cid,
                            )
                except Exception:
                    logger.warning(
                        "could not enumerate %s endpoints for task %s",
                        _net_label,
                        task_id,
                    )
                try:
                    await asyncio.to_thread(_net.remove)
                except Exception:
                    logger.warning(
                        "%s.remove failed for task %s", _net_label, task_id
                    )
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


def _create_sandbox_network(*, client: Any, name: str) -> Any:
    """Create the per-task ``internal: true`` sandbox bridge.

    Why ``internal: true``:
        Docker installs no MASQUERADE and no default gateway for an
        internal bridge. Containers attached to it cannot send any
        packet to an off-bridge destination unless they are *also*
        attached to a second non-internal network. The agent
        container is only on this network, so the kernel itself
        guarantees the agent has no path to the internet. ``unset
        HTTP_PROXY`` inside the agent does not help — there is no
        route to set the SYN packet on. ``curl https://1.1.1.1``
        fails with ``Network is unreachable``.

    Why this design supersedes the v0.1 plain-bridge approach:
        v0.1 used a plain bridge so that ``-p 31xxx:3000`` host
        DNAT worked for IP-only previews, at the cost of leaving the
        agent with a default route to the internet (cooperative
        egress only — an agent could ``unset HTTP_PROXY`` and reach
        raw IPs directly). v0.2 closes that gap by putting the agent
        on this ``internal: true`` bridge AND adding a per-task
        forwarder sidecar (see ``_create_forwarder``) that joins
        both this internal bridge and a separate pub network where
        host-side DNAT publishes the preview port.

    The forwarder + egress-proxy bridge to other networks for their
    own reasons (see ``_create_forwarder`` and ``_attach_egress_proxy``).
    """

    existing = client.networks.list(names=[name])
    if existing:
        return existing[0]
    return client.networks.create(name=name, driver="bridge", internal=True)


def _create_public_network(*, client: Any, name: str) -> Any:
    """Create the per-task public/plain bridge.

    The forwarder sidecar lives on this network and absorbs the host's
    ``-p 31xxx:3000`` published port via docker-proxy + DNAT. No agent
    or workload container is ever attached to this network.
    """

    existing = client.networks.list(names=[name])
    if existing:
        return existing[0]
    return client.networks.create(name=name, driver="bridge")


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
) -> Any:
    """Create the sandbox AGENT container with the full safety profile.

    Notes:
    * `nano_cpus` is the SDK's unit for `--cpus`: 1 CPU = 1e9.
    * `tmpfs` is required when `read_only=True` so /tmp is still writable
      for the agent process (Playwright caches, pip wheels, etc.).
    * We do NOT bind-mount the host docker socket; the container has
      no way to reach the host daemon, period.
    * No ``ports=`` mapping \u2014 in port mode the forwarder owns the
      published host port; in traefik mode Traefik reaches the agent
      over the docker bridge.
    * ``cap_add=['CHOWN','FOWNER']`` is the minimum needed for the
      in-container chmod that enforces frontend-first FS protection on
      agent-owned files. ``DAC_OVERRIDE`` is intentionally NOT added.
    * ``network`` is set to the internal sandbox bridge \u2014 the agent
      has no default route to anything except the egress-proxy alias
      on the same internal subnet.
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
        # Drop ALL caps, then re-add the two needed by the in-container
        # fs-protection script. With `cap_drop=ALL` the in-container
        # root has *no* DAC bypass and so cannot `chmod -R a-w` files
        # owned by the unprivileged agent UID — which means the whole
        # three-tier FS protection collapses to no-op. We re-add only
        # CHOWN + FOWNER:
        #   - CHOWN: allows `chown` if the protection script ever needs
        #     to re-parent agent-owned files.
        #   - FOWNER: bypass the "owner check" for chmod/utime, so the
        #     in-container root can flip a-w on agent-owned dirs.
        # Neither enables privilege escalation because
        # no-new-privileges blocks suid binaries from gaining anything
        # back and there is no network capability re-added.
        "cap_drop": ["ALL"],
        "cap_add": ["CHOWN", "FOWNER"],
        "mem_limit": config.mem_limit,
        "nano_cpus": nano_cpus,
        "pids_limit": config.pids_limit,
        "labels": {
            "com.aidev.task": task_id,
            "com.aidev.role": "sandbox",
        },
    }
    return client.containers.create(**create_kwargs)


def _create_forwarder(
    *,
    client: Any,
    config: SandboxConfig,
    task_id: str,
    pub_network_name: str,
    sandbox_network_name: str,
    agent_container_name: str,
    agent_port: int,
    port_bindings: dict[str, int],
) -> Any:
    """Create the per-task preview-forwarder sidecar.

    The forwarder runs ``socat TCP-LISTEN:3000,fork TCP:<agent>:3000``.
    It is created on the *pub* network (so the host's ``-p 31xxx:3000``
    DNAT actually has somewhere to deliver packets) and then connected
    to the *sandbox* network so it can reach the agent by docker DNS.

    Safety:
    * Non-root UID 10002.
    * ``cap_drop=ALL`` (no extra caps needed).
    * ``read_only=True``, no tmpfs needed \u2014 socat does not write disk.
    * ``no-new-privileges``.
    * No bind mounts, no docker socket, no shared namespaces.
    """

    nano_cpus = int(0.5 * 1_000_000_000)  # 0.5 CPU is plenty for socat
    create_kwargs: dict[str, Any] = {
        "image": config.forwarder_image,
        "name": config.forwarder_name(task_id),
        "user": "10002:10002",
        "network": pub_network_name,
        "environment": {
            "AIDEV_FORWARDER_TARGET": f"{agent_container_name}:{agent_port}",
            "AIDEV_FORWARDER_LISTEN": str(agent_port),
        },
        "read_only": True,
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "mem_limit": "128m",
        "nano_cpus": nano_cpus,
        "pids_limit": 64,
        "ports": port_bindings,
        "labels": {
            "com.aidev.task": task_id,
            "com.aidev.role": "forwarder",
        },
    }
    forwarder = client.containers.create(**create_kwargs)
    # Connect to the internal sandbox network so docker DNS resolves
    # the agent container's name to its sandbox IP.
    sandbox_net = client.networks.get(sandbox_network_name)
    try:
        sandbox_net.connect(forwarder)
    except Exception as exc:
        msg = str(exc).lower()
        if "already" not in msg:
            logger.warning(
                "could not connect forwarder to sandbox network: %s", exc
            )
    return forwarder


def _attach_egress_proxy(*, client: Any, network: Any, alias: str) -> None:
    """Wire the egress proxy container onto the per-task sandbox network.

    The proxy keeps its primary attachment on ``infra_default`` (where
    it has a working default route to the internet). We add the
    per-task sandbox bridge as a *second* NIC. Because the sandbox
    bridge is ``internal: true`` it has no gateway of its own, so
    adding it does not rewrite the proxy's default route \u2014 verified
    against Docker 27.x.
    """

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


def _detach_egress_proxy(*, client: Any, network: Any, alias: str) -> None:
    """Disconnect the egress proxy from the per-task sandbox network.

    Must be called *before* removing the network \u2014 Docker refuses to
    remove a network with active endpoints. The proxy's primary
    attachment on ``infra_default`` is untouched.
    """

    try:
        proxy = client.containers.get(alias)
    except Exception:
        return
    try:
        network.disconnect(proxy, force=True)
    except Exception as exc:
        # Not connected is fine; everything else logs.
        msg = str(exc).lower()
        if "not connected" not in msg and "no such" not in msg:
            logger.warning(
                "could not detach egress proxy from network: %s", exc
            )


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
