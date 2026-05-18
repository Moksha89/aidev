"""Configuration for the sandbox executor.

All knobs are read from environment variables prefixed with `AIDEV_SANDBOX_`
so a deploy-time `infra/.env` can re-tune the resource caps and allowlist
without code changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name) or default


def _env_optional(name: str) -> str | None:
    raw = os.environ.get(name)
    return raw or None


@dataclass(frozen=True)
class SandboxConfig:
    """Resource caps, image, network, and egress settings for one sandbox.

    Defaults match the approved design:
      * 2 CPU, 4 GB RAM, 512 pids, non-root UID 10001
      * read-only root filesystem, `no-new-privileges`
      * 30-minute task timeout
      * dedicated `internal: true` network per task, egress only through
        the tinyproxy allowlist sidecar
    """

    image: str = "aidev/sandbox:latest"
    cpus: float = 2.0
    mem_limit: str = "4g"
    pids_limit: int = 512
    task_timeout_seconds: int = 1800
    agent_uid: int = 10001
    workspace_path: str = "/workspace"

    # Networking
    network_name_prefix: str = "aidev_sandbox_"
    egress_proxy_url: str | None = None
    egress_proxy_alias: str = "aidev-egress-proxy"
    model_server_host: str | None = None

    # Traefik preview
    traefik_dynamic_dir: str = "/etc/traefik/dynamic/tasks"
    preview_domain: str = "preview.aidev.local"
    preview_internal_port: int = 3000

    # Event stream
    redis_url: str = "redis://localhost:6379/0"
    event_channel: str = "aidev.sandbox.events"

    # Optional Docker connection override (for tests / remote daemons).
    docker_base_url: str | None = None

    # Extra HTTP(S) hosts to allowlist beyond the package mirrors.
    extra_egress_hosts: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> SandboxConfig:
        extra_raw = os.environ.get("AIDEV_SANDBOX_EXTRA_EGRESS_HOSTS", "")
        extras = tuple(h.strip() for h in extra_raw.split(",") if h.strip())
        return cls(
            image=_env_str("AIDEV_SANDBOX_IMAGE", "aidev/sandbox:latest"),
            cpus=_env_float("AIDEV_SANDBOX_CPUS", 2.0),
            mem_limit=_env_str("AIDEV_SANDBOX_MEM_LIMIT", "4g"),
            pids_limit=_env_int("AIDEV_SANDBOX_PIDS_LIMIT", 512),
            task_timeout_seconds=_env_int("AIDEV_SANDBOX_TIMEOUT_SECONDS", 1800),
            agent_uid=_env_int("AIDEV_SANDBOX_AGENT_UID", 10001),
            workspace_path=_env_str("AIDEV_SANDBOX_WORKSPACE", "/workspace"),
            network_name_prefix=_env_str(
                "AIDEV_SANDBOX_NETWORK_PREFIX", "aidev_sandbox_"
            ),
            egress_proxy_url=_env_optional("AIDEV_SANDBOX_EGRESS_PROXY_URL"),
            egress_proxy_alias=_env_str(
                "AIDEV_SANDBOX_EGRESS_PROXY_ALIAS", "aidev-egress-proxy"
            ),
            model_server_host=_env_optional("AIDEV_SANDBOX_MODEL_SERVER_HOST"),
            traefik_dynamic_dir=_env_str(
                "AIDEV_SANDBOX_TRAEFIK_DYNAMIC_DIR", "/etc/traefik/dynamic/tasks"
            ),
            preview_domain=_env_str(
                "AIDEV_SANDBOX_PREVIEW_DOMAIN", "preview.aidev.local"
            ),
            preview_internal_port=_env_int("AIDEV_SANDBOX_PREVIEW_PORT", 3000),
            redis_url=_env_str("AIDEV_REDIS_URL", "redis://localhost:6379/0"),
            event_channel=_env_str(
                "AIDEV_SANDBOX_EVENT_CHANNEL", "aidev.sandbox.events"
            ),
            docker_base_url=_env_optional("AIDEV_SANDBOX_DOCKER_URL"),
            extra_egress_hosts=extras,
        )

    @property
    def read_only_root(self) -> bool:
        """Whether the container root FS is mounted read-only.

        Always `True` for the production config; tests can patch this.
        """
        return _env_bool("AIDEV_SANDBOX_READ_ONLY_ROOTFS", default=True)

    def network_name(self, task_id: str) -> str:
        return f"{self.network_name_prefix}{task_id}"

    def container_name(self, task_id: str) -> str:
        return f"aidev-sandbox-{task_id}"

    def volume_name(self, task_id: str) -> str:
        return f"aidev-sandbox-vol-{task_id}"

    def preview_host(self, task_id: str) -> str:
        return f"task-{task_id}.{self.preview_domain}"


__all__ = ["SandboxConfig"]
