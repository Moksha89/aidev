"""Unit tests for `DockerSandboxExecutor` with a faked Docker SDK.

These tests do NOT spin up real containers — they assert that the
executor wires the docker-py SDK with the right safety profile
(non-root, read-only rootfs, no-new-privileges, resource caps,
v0.2 dual-network layout), drives the per-task lifecycle in the right
order, and cleans up on exit.

The v0.2 architecture has:
  * one ``internal: true`` per-task sandbox bridge (agent + egress-proxy)
  * one plain per-task pub bridge (forwarder only)
  * one agent container on the sandbox bridge
  * one forwarder sidecar multi-homed on pub + sandbox
  * the shared egress-proxy multi-homed onto the sandbox bridge

So every successful session creates 2 networks and 1–2 containers via
the fake SDK; cleanup must remove the forwarder, disconnect the proxy,
remove the agent, then remove both networks.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from aidev_shared import TaskPhase

from sandbox_runner.config import SandboxConfig
from sandbox_runner.docker_executor import DockerSandboxExecutor
from sandbox_runner.preview import PortPreviewRegistrar, PreviewRegistrar

# ---- fake docker SDK ------------------------------------------------------


class _FakeContainer:
    def __init__(self, name: str, kwargs: dict[str, Any]) -> None:
        self.id = f"deadbeef-{name}"
        self.name = name
        self.create_kwargs = kwargs
        self.exec_calls: list[dict[str, Any]] = []
        self.archive_writes: list[tuple[str, bytes]] = []
        self.started = False
        self.removed = False
        self.remove_kwargs: dict[str, Any] | None = None
        # The fake honours queued exec results in FIFO order; unknown
        # commands return (0, b"", b"").
        self.exec_queue: list[tuple[int, bytes, bytes]] = []

    def start(self) -> None:
        self.started = True

    def exec_run(
        self,
        *,
        cmd: Any,
        user: str = "",
        workdir: str = "",
        demux: bool = False,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        self.exec_calls.append(
            {
                "cmd": cmd,
                "user": user,
                "workdir": workdir,
                "demux": demux,
                "environment": environment,
            }
        )
        if self.exec_queue:
            rc, stdout, stderr = self.exec_queue.pop(0)
        else:
            rc, stdout, stderr = 0, b"", b""
        if demux:
            return rc, (stdout, stderr)
        return rc, stdout

    def put_archive(self, path: str, data: bytes) -> bool:
        self.archive_writes.append((path, data))
        return True

    def get_archive(self, path: str) -> tuple[Iterator[bytes], dict[str, Any]]:
        # Build a tar containing the requested file with stub content.
        buf = io.BytesIO()
        name = path.rsplit("/", 1)[-1]
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=name)
            content = b"fake-content"
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        buf.seek(0)
        return iter([buf.read()]), {"name": name, "size": 12}

    def remove(self, *, force: bool = False, v: bool = False) -> None:
        self.removed = True
        self.remove_kwargs = {"force": force, "v": v}


class _FakeNetwork:
    def __init__(self, name: str) -> None:
        self.name = name
        self.id = f"net-{name}"
        self.removed = False
        self.remove_failures = 0  # if >0 the next N remove() calls raise
        self.connections: list[tuple[Any, list[str]]] = []
        # ``disconnects`` records ids (cleanup-loop pattern from
        # PR #4); ``disconnections`` records (container, force) tuples
        # (egress-proxy detach pattern from v0.2). Both are written
        # by ``disconnect`` so both test styles work.
        self.disconnects: list[Any] = []
        self.disconnections: list[tuple[Any, bool]] = []
        self.attrs: dict[str, Any] = {"Containers": {}}

    def connect(self, container: Any, aliases: list[str] | None = None) -> None:
        cid = getattr(container, "id", str(id(container)))
        self.connections.append((container, list(aliases or [])))
        self.attrs.setdefault("Containers", {})[cid] = {
            "Name": getattr(container, "name", cid),
        }

    def disconnect(self, container: Any, *, force: bool = False) -> None:
        cid = container if isinstance(container, str) else getattr(
            container, "id", str(container)
        )
        self.disconnects.append(cid)
        self.disconnections.append((container, force))
        if isinstance(self.attrs.get("Containers"), dict):
            self.attrs["Containers"].pop(cid, None)

    def reload(self) -> None:
        # Fake daemon round-trip; in real Docker, this re-fetches attrs.
        return None

    def remove(self) -> None:
        if self.remove_failures > 0:
            self.remove_failures -= 1
            raise RuntimeError(
                f"network has active endpoints (fake remove_failures left "
                f"{self.remove_failures})"
            )
        self.removed = True


class _FakeVolume:
    def __init__(self, name: str) -> None:
        self.name = name
        self.removed = False

    def remove(self, *, force: bool = False) -> None:
        self.removed = True


class _FakeNetworks:
    def __init__(self) -> None:
        self.created: list[_FakeNetwork] = []

    def list(self, names: list[str] | None = None) -> list[_FakeNetwork]:
        if not names:
            return []
        return [n for n in self.created if n.name in set(names)]

    def get(self, name: str) -> _FakeNetwork:
        for n in self.created:
            if n.name == name:
                return n
        raise LookupError(name)

    def create(
        self,
        *,
        name: str,
        driver: str = "bridge",
        internal: bool = False,
        options: dict[str, str] | None = None,
    ) -> _FakeNetwork:
        # Capture the kwargs so tests can assert hardening flags.
        net = _FakeNetwork(name)
        net.driver = driver  # type: ignore[attr-defined]
        net.internal = internal  # type: ignore[attr-defined]
        net.options = dict(options or {})  # type: ignore[attr-defined]
        self.created.append(net)
        return net


class _FakeVolumes:
    def __init__(self) -> None:
        self.created: list[_FakeVolume] = []

    def list(self, *, filters: dict[str, str] | None = None) -> list[_FakeVolume]:
        if not filters:
            return list(self.created)
        wanted = filters.get("name")
        return [v for v in self.created if v.name == wanted]

    def create(self, *, name: str) -> _FakeVolume:
        vol = _FakeVolume(name)
        self.created.append(vol)
        return vol


class _FakeContainers:
    def __init__(self) -> None:
        self.created: list[_FakeContainer] = []

    def create(self, **kwargs: Any) -> _FakeContainer:
        c = _FakeContainer(kwargs["name"], kwargs)
        self.created.append(c)
        return c

    def get(self, name: str) -> _FakeContainer:
        for c in self.created:
            if c.name == name:
                return c
        raise LookupError(name)


class _FakeDocker:
    def __init__(self) -> None:
        self.networks = _FakeNetworks()
        self.volumes = _FakeVolumes()
        self.containers = _FakeContainers()


# ---- fixtures -------------------------------------------------------------


@pytest.fixture
def fake_client() -> _FakeDocker:
    return _FakeDocker()


@pytest.fixture
def config(tmp_path: Path) -> SandboxConfig:
    """Port-based preview mode — the IP-only acceptance default."""

    return SandboxConfig(
        image="aidev/sandbox:test",
        cpus=2.0,
        mem_limit="4g",
        pids_limit=512,
        task_timeout_seconds=1800,
        agent_uid=10001,
        egress_proxy_url="http://aidev-egress-proxy:8888",
        egress_proxy_alias="aidev-egress-proxy",
        model_server_host="ollama.aidev.local",
        preview_mode="port",
        preview_public_host="203.0.113.10",
        preview_port_range_start=31000,
        preview_port_range_end=31099,
        traefik_dynamic_dir=str(tmp_path / "traefik-dynamic"),
        preview_domain="preview.aidev.local",
        redis_url="redis://ignored",
    )


@pytest.fixture
def traefik_config(tmp_path: Path) -> SandboxConfig:
    """Domain-based preview mode — future production path."""

    return SandboxConfig(
        image="aidev/sandbox:test",
        cpus=2.0,
        mem_limit="4g",
        pids_limit=512,
        task_timeout_seconds=1800,
        agent_uid=10001,
        egress_proxy_url="http://aidev-egress-proxy:8888",
        egress_proxy_alias="aidev-egress-proxy",
        model_server_host="ollama.aidev.local",
        preview_mode="traefik",
        traefik_dynamic_dir=str(tmp_path / "traefik-dynamic"),
        preview_domain="preview.aidev.local",
        redis_url="redis://ignored",
    )


def _build_executor(
    *, config: SandboxConfig, fake_client: _FakeDocker
) -> DockerSandboxExecutor:
    from sandbox_runner.event_stream import EventStream

    class _NullClient:
        def publish(self, channel: str, message: str) -> int:
            return 0

        def close(self) -> None:
            pass

    return DockerSandboxExecutor(
        config=config,
        docker_client=fake_client,
        event_stream=EventStream(
            redis_url="redis://ignored",
            channel=config.event_channel,
            client=_NullClient(),
        ),
        preview_registrar=PreviewRegistrar(
            dynamic_dir=config.traefik_dynamic_dir
        ),
        port_registrar=PortPreviewRegistrar(
            public_host=config.preview_public_host,
            port_range_start=config.preview_port_range_start,
            port_range_end=config.preview_port_range_end,
        ),
    )


@pytest.fixture
def executor(
    fake_client: _FakeDocker, config: SandboxConfig
) -> DockerSandboxExecutor:
    return _build_executor(config=config, fake_client=fake_client)


@pytest.fixture
def traefik_executor(
    fake_client: _FakeDocker, traefik_config: SandboxConfig
) -> DockerSandboxExecutor:
    return _build_executor(config=traefik_config, fake_client=fake_client)


# ---- tests ----------------------------------------------------------------


def _agent_container(fake_client: _FakeDocker) -> _FakeContainer:
    """Pick the agent container out of the fake client.

    Identified by the ``com.aidev.role: sandbox`` label so the test
    doesn't depend on creation order with the forwarder.
    """

    for c in fake_client.containers.created:
        if c.create_kwargs.get("labels", {}).get("com.aidev.role") == "sandbox":
            return c
    raise AssertionError("agent container not found in fake client")


def _forwarder_container(fake_client: _FakeDocker) -> _FakeContainer:
    for c in fake_client.containers.created:
        if (
            c.create_kwargs.get("labels", {}).get("com.aidev.role")
            == "forwarder"
        ):
            return c
    raise AssertionError("forwarder container not found in fake client")


def _network_by_name(fake_client: _FakeDocker, name: str) -> _FakeNetwork:
    for n in fake_client.networks.created:
        if n.name == name:
            return n
    raise AssertionError(f"network {name!r} not created")


@pytest.mark.asyncio
async def test_session_applies_full_safety_profile(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    async with executor.session(task_id="t1") as session:
        assert session.task_id == "t1"
        assert session.workspace_path == "/workspace"
        assert session.current_phase == TaskPhase.FRONTEND_CODING

    container = _agent_container(fake_client)
    kwargs = container.create_kwargs

    # Resource caps
    assert kwargs["mem_limit"] == "4g"
    assert kwargs["pids_limit"] == 512
    assert kwargs["nano_cpus"] == 2 * 1_000_000_000
    # Non-root agent
    assert kwargs["user"] == "10001:10001"
    # Read-only root + tmpfs for /tmp
    assert kwargs["read_only"] is True
    assert "/tmp" in kwargs["tmpfs"]
    # Hardening flags
    assert "no-new-privileges:true" in kwargs["security_opt"]
    assert kwargs["cap_drop"] == ["ALL"]
    # Minimum caps re-added so in-container root can chmod
    # agent-owned files for the fs-protection layer. DAC_OVERRIDE is
    # NOT in this list — the protection script does not need it.
    assert kwargs["cap_add"] == ["CHOWN", "FOWNER"]
    # Per-task volume mounted at /workspace
    assert kwargs["volumes"]["aidev-sandbox-vol-t1"] == {
        "bind": "/workspace",
        "mode": "rw",
    }
    # v0.2 architecture: the agent's only network is the *internal*
    # sandbox bridge — kernel-level egress isolation. The plain pub
    # bridge exists for the forwarder, not the agent.
    sandbox_net = _network_by_name(fake_client, "aidev_sandbox_t1")
    pub_net = _network_by_name(fake_client, "aidev_pub_t1")
    assert kwargs["network"] == sandbox_net.name
    assert sandbox_net.internal is True
    assert pub_net.internal is False
    # The agent must NOT publish a host port — only the forwarder does.
    assert "ports" not in kwargs
    # Egress proxy env injected
    assert kwargs["environment"]["HTTP_PROXY"] == "http://aidev-egress-proxy:8888"
    assert kwargs["environment"]["HTTPS_PROXY"] == "http://aidev-egress-proxy:8888"
    # No host docker socket
    for v in kwargs["volumes"]:
        assert "docker.sock" not in v


@pytest.mark.asyncio
async def test_session_cleans_up_on_exit(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    # Pre-register the egress proxy so the executor finds it and we
    # exercise the disconnect-on-exit path.
    fake_client.containers.create(
        image="tinyproxy",
        name="aidev-egress-proxy",
        labels={"com.aidev.role": "infra"},
    )
    async with executor.session(task_id="t2"):
        pass

    agent = _agent_container(fake_client)
    forwarder = _forwarder_container(fake_client)
    sandbox_net = _network_by_name(fake_client, "aidev_sandbox_t2")
    pub_net = _network_by_name(fake_client, "aidev_pub_t2")
    volume = fake_client.volumes.created[0]

    # Both containers removed force+volumes
    assert agent.removed
    assert agent.remove_kwargs == {"force": True, "v": True}
    assert forwarder.removed
    assert forwarder.remove_kwargs == {"force": True, "v": True}
    # Egress proxy was disconnected from the sandbox bridge before
    # network removal.
    assert sandbox_net.disconnections, (
        "sandbox network must be disconnected from the egress proxy "
        "before being removed"
    )
    # Both networks removed
    assert sandbox_net.removed
    assert pub_net.removed
    # Volume removed
    assert volume.removed


@pytest.mark.asyncio
async def test_write_file_validates_rules_engine(
    executor: DockerSandboxExecutor,
) -> None:
    from aidev_rules_engine import Evaluator
    from aidev_rules_engine.parser import Rule

    rules = [
        Rule(
            id="frontend",
            title="frontend-only",
            applies_to="phases.frontend_coding",
            priority=50,
            allowed_paths=("apps/web/**",),
            forbidden_paths=("apps/api/**",),
        ),
    ]
    evaluator = Evaluator(rules)

    async with executor.session(task_id="t3") as session:
        session.set_evaluator(evaluator)

        # Writing a frontend file is fine.
        n = await session.write_file("apps/web/page.tsx", "export default {}")
        assert n == len(b"export default {}")

        # Writing a backend file in frontend_coding phase is blocked.
        from aidev_rules_engine import RuleViolation

        with pytest.raises(RuleViolation):
            await session.write_file("apps/api/main.py", "print(1)")


@pytest.mark.asyncio
async def test_set_phase_runs_protection_script(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    async with executor.session(task_id="t4") as session:
        await session.set_phase(TaskPhase.BACKEND_UNLOCKED)

    agent = _agent_container(fake_client)
    # Every fs-protection invocation runs as root on the agent and
    # execs the rendered script. We expect at least one such call
    # after set_phase(BACKEND_UNLOCKED).
    root_protection_calls = [
        c
        for c in agent.exec_calls
        if c["user"] == "0"
        and any(".aidev/fs_protection.sh" in str(part) for part in c["cmd"])
    ]
    assert root_protection_calls, agent.exec_calls


@pytest.mark.asyncio
async def test_start_preview_server_registers_traefik_route(
    traefik_executor: DockerSandboxExecutor, traefik_config: SandboxConfig
) -> None:
    async with traefik_executor.session(task_id="abc") as session:
        url = await session.start_preview_server(command="echo dev-server")
        assert url == "https://task-abc.preview.aidev.local"
        assert session.preview_url == url

        dynamic_file = (
            Path(traefik_config.traefik_dynamic_dir) / "task-abc.yml"
        )
        assert dynamic_file.exists()
        content = dynamic_file.read_text(encoding="utf-8")
        assert "task-abc.preview.aidev.local" in content
        assert "http://aidev-sandbox-abc:3000" in content

    # Session exit deregisters the route.
    assert not (
        Path(traefik_config.traefik_dynamic_dir) / "task-abc.yml"
    ).exists()


@pytest.mark.asyncio
async def test_port_mode_publishes_host_port_on_forwarder_not_agent(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    async with executor.session(task_id="abc"):
        pass

    agent = _agent_container(fake_client)
    forwarder = _forwarder_container(fake_client)
    # In v0.2 the forwarder owns the host port mapping; the agent
    # has no host port at all (and lives on internal=true).
    assert "ports" not in agent.create_kwargs
    assert forwarder.create_kwargs.get("ports") == {"3000/tcp": 31000}
    # Forwarder is created on the plain pub bridge and then connected
    # to the internal sandbox bridge for agent DNS.
    assert forwarder.create_kwargs["network"] == "aidev_pub_abc"
    sandbox_net = _network_by_name(fake_client, "aidev_sandbox_abc")
    assert any(c is forwarder for c, _ in sandbox_net.connections), (
        "forwarder must be attached to the internal sandbox bridge "
        "so it can reach the agent by docker DNS"
    )


@pytest.mark.asyncio
async def test_port_mode_start_preview_server_returns_ip_url(
    executor: DockerSandboxExecutor, config: SandboxConfig
) -> None:
    async with executor.session(task_id="abc") as session:
        url = await session.start_preview_server(command="echo dev-server")
        # IP-only acceptance URL: http://<public-host>:<allocated-port>
        assert url == f"http://{config.preview_public_host}:31000"
        assert session.preview_url == url


@pytest.mark.asyncio
async def test_port_mode_releases_allocation_on_exit(
    executor: DockerSandboxExecutor,
) -> None:
    async with executor.session(task_id="abc") as session:
        await session.start_preview_server(command="echo dev-server")
    # After exit the same port is free again for a new task.
    async with executor.session(task_id="def") as session2:
        url = await session2.start_preview_server(command="echo dev-server")
        # First allocation reused since the previous task released it.
        assert url.endswith(":31000")


@pytest.mark.asyncio
async def test_traefik_mode_does_not_publish_host_ports(
    traefik_executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    async with traefik_executor.session(task_id="abc"):
        pass

    agent = _agent_container(fake_client)
    # Domain-mode agents stay off the host port table — Traefik
    # reaches them on the docker bridge instead. And in traefik mode
    # we do NOT spin up a forwarder at all.
    assert "ports" not in agent.create_kwargs
    forwarders = [
        c
        for c in fake_client.containers.created
        if c.create_kwargs.get("labels", {}).get("com.aidev.role") == "forwarder"
    ]
    assert forwarders == [], (
        "traefik mode must not create a forwarder — the published "
        "port architecture is only needed for IP-only/port mode"
    )


@pytest.mark.asyncio
async def test_run_returns_command_result(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    async with executor.session(task_id="t5") as session:
        # Queue an exec result on the AGENT container so the run() call
        # below sees stdout. (The forwarder doesn't run exec.)
        agent = _agent_container(fake_client)
        agent.exec_queue.append((0, b"hello\n", b""))
        result = await session.run("echo hello")
        assert result.returncode == 0
        assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_read_file_round_trips_via_tar_archive(
    executor: DockerSandboxExecutor,
) -> None:
    async with executor.session(task_id="t6") as session:
        contents = await session.read_file("README.md")
        # Our fake get_archive returns "fake-content" for any read.
        assert contents == b"fake-content"


@pytest.mark.asyncio
async def test_write_file_rejects_path_traversal(
    executor: DockerSandboxExecutor,
) -> None:
    async with executor.session(task_id="t7") as session:
        with pytest.raises(ValueError):
            await session.write_file("../escape.txt", "nope")
        with pytest.raises(ValueError):
            await session.write_file("/etc/passwd", "nope")


@pytest.mark.asyncio
async def test_capture_changed_files_parses_porcelain(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    async with executor.session(task_id="t8") as session:
        agent = _agent_container(fake_client)
        agent.exec_queue.append(
            (
                0,
                b" M apps/web/page.tsx\n?? new.txt\nR  old.txt -> new-name.txt\n",
                b"",
            )
        )
        files = await session.capture_changed_files()
        assert "apps/web/page.tsx" in files
        assert "new.txt" in files
        assert "new-name.txt" in files


@pytest.mark.asyncio
async def test_egress_proxy_attached_when_configured(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    # Pre-register the proxy container so the executor can look it up.
    fake_client.containers.create(
        name="aidev-egress-proxy",
        command=["true"],
    )
    async with executor.session(task_id="t9"):
        pass

    network = fake_client.networks.created[0]
    proxy_attached = any(
        getattr(c, "name", None) == "aidev-egress-proxy"
        for c, _ in network.connections
    )
    assert proxy_attached


@pytest.mark.asyncio
async def test_session_disconnects_endpoints_before_network_remove(
    executor: DockerSandboxExecutor, fake_client: _FakeDocker
) -> None:
    """Regression: real Docker refuses to remove a network with active
    endpoints. The cleanup path must disconnect every attached container
    (the egress proxy is the typical lingerer) before calling remove().
    """

    # Pre-register the proxy container so the executor attaches it.
    fake_client.containers.create(
        name="aidev-egress-proxy",
        command=["true"],
    )
    async with executor.session(task_id="t-net-cleanup"):
        pass

    network = fake_client.networks.created[0]
    # The proxy is the typical lingerer; we assert at least one
    # disconnect call happened before the network was removed so the
    # real `network has active endpoints` daemon error is avoided.
    assert network.disconnects, (
        f"expected disconnect() to be called before remove(); "
        f"got disconnects={network.disconnects!r}"
    )
    assert network.removed, "network.remove() must succeed after disconnect"


# ---- v0.3 Docker socket gatekeeper -----------------------------------------
#
# These tests are *static checks against `infra/docker-compose.yml`*. They
# encode the v0.3 contract:
#
#   1. The sandbox-runner worker has NO direct bind on /var/run/docker.sock.
#   2. The sandbox-runner worker reaches the Docker Engine API only via
#      `DOCKER_HOST=tcp://docker-socket-proxy:2375`.
#   3. A `docker-socket-proxy` service exists with the right allow/deny
#      policy and the right hardening (read-only mount, cap_drop=ALL,
#      no host port).
#
# If anyone ever re-mounts the host socket on sandbox-runner, or drops
# `DOCKER_HOST`, or weakens the proxy policy (e.g. flips BUILD=1 or
# SWARM=1 or SYSTEM=1), these tests fail at PR review time — long
# before the change reaches the VPS.


def _load_compose() -> dict[str, Any]:
    import yaml

    repo_root = Path(__file__).resolve().parents[3]
    compose_path = repo_root / "infra" / "docker-compose.yml"
    with compose_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_sandbox_runner_has_no_docker_sock_mount() -> None:
    compose = _load_compose()
    svc = compose["services"]["sandbox-runner"]
    volumes = svc.get("volumes", [])
    assert isinstance(volumes, list), volumes
    offenders = [v for v in volumes if "docker.sock" in str(v)]
    assert offenders == [], (
        "sandbox-runner must NOT bind the host docker socket directly. "
        "It must reach Docker via the docker-socket-proxy service. "
        f"Offending volumes: {offenders!r}"
    )


def test_sandbox_runner_routes_docker_via_proxy() -> None:
    compose = _load_compose()
    svc = compose["services"]["sandbox-runner"]
    env = svc.get("environment", {})
    assert isinstance(env, dict), env
    docker_host = env.get("DOCKER_HOST")
    assert docker_host == "tcp://docker-socket-proxy:2375", (
        "sandbox-runner must set DOCKER_HOST=tcp://docker-socket-proxy:2375 "
        f"so the Docker SDK routes calls through the gatekeeper. Got: "
        f"{docker_host!r}"
    )
    depends_on = svc.get("depends_on", {})
    assert "docker-socket-proxy" in depends_on, (
        "sandbox-runner must depend_on docker-socket-proxy so the proxy is "
        "up before any Docker SDK call is issued."
    )


def test_docker_socket_proxy_service_exists_with_hardened_policy() -> None:
    compose = _load_compose()
    services = compose["services"]
    assert "docker-socket-proxy" in services, (
        "v0.3 requires a docker-socket-proxy service in front of the host "
        "Docker daemon"
    )
    proxy = services["docker-socket-proxy"]

    # Image pinned (no floating `latest`).
    assert ":" in proxy["image"], proxy["image"]
    assert proxy["image"].startswith("tecnativa/docker-socket-proxy:"), proxy[
        "image"
    ]

    # Only the proxy still binds the host socket — and read-only.
    proxy_volumes = proxy.get("volumes", [])
    sock_binds = [v for v in proxy_volumes if "docker.sock" in str(v)]
    assert sock_binds, "the proxy must bind the host docker.sock to forward"
    for v in sock_binds:
        assert str(v).endswith(":ro"), (
            f"docker-socket-proxy must mount /var/run/docker.sock READ-ONLY; "
            f"got: {v!r}"
        )

    # No host port: the proxy must only be reachable on the compose network.
    assert "ports" not in proxy, (
        "docker-socket-proxy must NOT publish a host port — it is internal-only"
    )

    # Hardening flags expected on the proxy itself.
    assert proxy.get("read_only") is True
    assert proxy.get("cap_drop") == ["ALL"]
    assert "no-new-privileges:true" in proxy.get("security_opt", [])

    # API allowlist: only the families the executor needs.
    env = proxy["environment"]
    for allowed in ("CONTAINERS", "NETWORKS", "VOLUMES", "EXEC", "IMAGES", "POST"):
        assert env.get(allowed) == 1, (
            f"docker-socket-proxy must allow {allowed} (got {env.get(allowed)!r})"
        )
    # Required by the SDK on connect.
    for required in ("PING", "VERSION"):
        assert env.get(required) == 1, (
            f"docker-socket-proxy must allow {required} for SDK handshake "
            f"(got {env.get(required)!r})"
        )

    # API blocklist: must be explicitly off. This is the v0.3 contract;
    # do NOT relax these without an architecture review.
    blocked = (
        "AUTH",
        "BUILD",
        "COMMIT",
        "CONFIGS",
        "DISTRIBUTION",
        "EVENTS",
        "INFO",
        "NODES",
        "PLUGINS",
        "SECRETS",
        "SERVICES",
        "SESSION",
        "SWARM",
        "SYSTEM",
        "TASKS",
    )
    for denied in blocked:
        assert env.get(denied) == 0, (
            f"docker-socket-proxy must block {denied} (got {env.get(denied)!r}). "
            f"v0.3 contract: only containers/networks/volumes/exec/images/ping/"
            f"version are reachable via the proxy."
        )


# ---- v0.3 executor-side wiring ---------------------------------------------


def test_executor_falls_back_to_from_env_when_no_base_url(
    config: SandboxConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AIDEV_SANDBOX_DOCKER_URL is unset (the v0.3 default), the
    executor must construct its Docker client via `docker.from_env()` so
    the SDK picks up `DOCKER_HOST=tcp://docker-socket-proxy:2375` from
    the environment. We don't want to second-guess the SDK — but we do
    want a regression test that nobody re-introduces a hard-coded
    `unix:///var/run/docker.sock`.
    """

    sentinel = object()

    calls: dict[str, Any] = {}

    class _FakeDockerModule:
        @staticmethod
        def from_env() -> Any:
            calls["from_env"] = True
            return sentinel

        class DockerClient:  # pragma: no cover — should NOT be called
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                calls["DockerClient"] = (args, kwargs)

    import sys

    monkeypatch.setitem(sys.modules, "docker", _FakeDockerModule)

    # No docker_base_url set on the config → must use from_env().
    cfg = SandboxConfig(
        image=config.image,
        cpus=config.cpus,
        mem_limit=config.mem_limit,
        pids_limit=config.pids_limit,
        task_timeout_seconds=config.task_timeout_seconds,
        agent_uid=config.agent_uid,
        egress_proxy_url=config.egress_proxy_url,
        egress_proxy_alias=config.egress_proxy_alias,
        model_server_host=config.model_server_host,
        preview_mode=config.preview_mode,
        preview_public_host=config.preview_public_host,
        preview_port_range_start=config.preview_port_range_start,
        preview_port_range_end=config.preview_port_range_end,
        traefik_dynamic_dir=config.traefik_dynamic_dir,
        preview_domain=config.preview_domain,
        redis_url=config.redis_url,
        docker_base_url=None,
    )
    exe = DockerSandboxExecutor(config=cfg)
    client = exe._get_client()

    assert client is sentinel, (
        "executor must build its client via docker.from_env() when no "
        "docker_base_url is set, so DOCKER_HOST=tcp://docker-socket-proxy:2375 "
        "from the compose env is honoured by the SDK"
    )
    assert calls.get("from_env") is True
    assert "DockerClient" not in calls, (
        "executor must NOT bypass DOCKER_HOST by hard-coding a base_url"
    )
