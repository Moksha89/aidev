"""Tests for ``AgentRunnerConfig`` and its v0.4 readiness flags.

These run without a database — they only exercise environment-variable
parsing and the ``real_pipeline_active`` / ``github_configured``
properties the dispatcher relies on.
"""

from __future__ import annotations

import pytest

from agent_runner.config import AgentRunnerConfig


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every AIDEV_* and SANDBOX_* var so each test starts blank."""
    for name in (
        "AIDEV_AGENT_PIPELINE",
        "AGENT_PIPELINE",
        "SANDBOX_EXECUTOR",
        "AIDEV_GITHUB_TOKEN",
        "GITHUB_TOKEN",
        "AIDEV_GITHUB_APP_ID",
        "AIDEV_GITHUB_APP_INSTALLATION_ID",
        "AIDEV_GITHUB_APP_PRIVATE_KEY_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_config_is_safely_mocked() -> None:
    cfg = AgentRunnerConfig.from_env()
    assert cfg.agent_pipeline == "mock"
    assert cfg.sandbox_executor == "mock"
    assert cfg.real_pipeline_active is False
    assert cfg.github_configured is False


def test_real_pipeline_requires_both_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIDEV_AGENT_PIPELINE", "real")
    assert AgentRunnerConfig.from_env().real_pipeline_active is False
    monkeypatch.setenv("SANDBOX_EXECUTOR", "docker")
    assert AgentRunnerConfig.from_env().real_pipeline_active is True


def test_only_executor_flag_is_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_EXECUTOR", "docker")
    assert AgentRunnerConfig.from_env().real_pipeline_active is False


def test_github_token_marks_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIDEV_GITHUB_TOKEN", "ghp_dummy_for_unit_test")
    cfg = AgentRunnerConfig.from_env()
    assert cfg.github_configured is True
    assert cfg.github_token == "ghp_dummy_for_unit_test"


def test_github_app_marks_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIDEV_GITHUB_APP_ID", "12345")
    monkeypatch.setenv("AIDEV_GITHUB_APP_INSTALLATION_ID", "987")
    monkeypatch.setenv(
        "AIDEV_GITHUB_APP_PRIVATE_KEY_PATH", "/etc/aidev/github-app.pem"
    )
    cfg = AgentRunnerConfig.from_env()
    assert cfg.github_configured is True
    assert cfg.github_app_id == 12345
    assert cfg.github_app_installation_id == 987


def test_pipeline_value_is_lowercased(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIDEV_AGENT_PIPELINE", "REAL")
    monkeypatch.setenv("SANDBOX_EXECUTOR", "DOCKER")
    cfg = AgentRunnerConfig.from_env()
    assert cfg.agent_pipeline == "real"
    assert cfg.sandbox_executor == "docker"
    assert cfg.real_pipeline_active is True
