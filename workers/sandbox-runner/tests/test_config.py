"""SandboxConfig parses env vars and exposes the right defaults."""

from __future__ import annotations

import pytest

from sandbox_runner.config import SandboxConfig


def test_defaults_match_approved_design() -> None:
    cfg = SandboxConfig()
    assert cfg.cpus == 2.0
    assert cfg.mem_limit == "4g"
    assert cfg.pids_limit == 512
    assert cfg.agent_uid == 10001
    assert cfg.task_timeout_seconds == 1800
    assert cfg.workspace_path == "/workspace"
    assert cfg.image == "aidev/sandbox:latest"
    assert cfg.preview_internal_port == 3000
    assert cfg.read_only_root is True
    # IP-only acceptance defaults: port-based previews on 31000-31999.
    assert cfg.preview_mode == "port"
    assert cfg.preview_public_host == "127.0.0.1"
    assert cfg.preview_port_range_start == 31000
    assert cfg.preview_port_range_end == 31999


def test_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIDEV_SANDBOX_CPUS", "4")
    monkeypatch.setenv("AIDEV_SANDBOX_MEM_LIMIT", "8g")
    monkeypatch.setenv("AIDEV_SANDBOX_PIDS_LIMIT", "1024")
    monkeypatch.setenv("AIDEV_SANDBOX_TIMEOUT_SECONDS", "3600")
    monkeypatch.setenv("AIDEV_SANDBOX_AGENT_UID", "20001")
    monkeypatch.setenv("AIDEV_SANDBOX_IMAGE", "custom/sandbox:dev")
    monkeypatch.setenv(
        "AIDEV_SANDBOX_EGRESS_PROXY_URL", "http://proxy.aidev.local:8888"
    )
    monkeypatch.setenv(
        "AIDEV_SANDBOX_MODEL_SERVER_HOST", "ollama.aidev.local"
    )
    monkeypatch.setenv(
        "AIDEV_SANDBOX_EXTRA_EGRESS_HOSTS",
        "mirrors.example.com, deb.example.org , ",
    )
    monkeypatch.setenv("AIDEV_SANDBOX_PREVIEW_MODE", "traefik")
    monkeypatch.setenv("AIDEV_SANDBOX_PREVIEW_HOST", "10.0.0.5")
    monkeypatch.setenv("AIDEV_SANDBOX_PREVIEW_PORT_RANGE_START", "32100")
    monkeypatch.setenv("AIDEV_SANDBOX_PREVIEW_PORT_RANGE_END", "32199")

    cfg = SandboxConfig.from_env()

    assert cfg.cpus == 4.0
    assert cfg.mem_limit == "8g"
    assert cfg.pids_limit == 1024
    assert cfg.task_timeout_seconds == 3600
    assert cfg.agent_uid == 20001
    assert cfg.image == "custom/sandbox:dev"
    assert cfg.egress_proxy_url == "http://proxy.aidev.local:8888"
    assert cfg.model_server_host == "ollama.aidev.local"
    assert cfg.extra_egress_hosts == ("mirrors.example.com", "deb.example.org")
    assert cfg.preview_mode == "traefik"
    assert cfg.preview_public_host == "10.0.0.5"
    assert cfg.preview_port_range_start == 32100
    assert cfg.preview_port_range_end == 32199


def test_per_task_naming_is_deterministic() -> None:
    cfg = SandboxConfig()
    assert cfg.network_name("abc123") == "aidev_sandbox_abc123"
    assert cfg.container_name("abc123") == "aidev-sandbox-abc123"
    assert cfg.volume_name("abc123") == "aidev-sandbox-vol-abc123"
    assert cfg.preview_host("abc123") == "task-abc123.preview.aidev.local"
