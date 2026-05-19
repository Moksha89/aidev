"""Configuration for the agent-runner worker.

Loaded from environment variables. The agent-runner shares the
``AIDEV_*`` prefix with the API so a single ``infra/.env`` configures
both processes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


def _env_optional(name: str) -> str | None:
    raw = os.environ.get(name)
    return raw or None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class AgentRunnerConfig:
    """Runtime configuration for one agent-runner worker process.

    All knobs come from environment variables. Defaults mirror the
    ``mock`` API defaults so an agent-runner started without any extra
    env vars is harmless — it just refuses to run the real pipeline.
    """

    database_url: str
    redis_url: str
    agent_pipeline: str  # "mock" or "real"
    sandbox_executor: str  # "mock" or "docker"

    github_token: str | None
    github_app_id: int | None
    github_app_private_key_path: str | None
    github_app_installation_id: int | None

    model_base_url: str
    model_name: str
    model_api_key: str
    model_timeout_seconds: int

    pr_default_base_branch: str
    pr_title_template: str
    pr_body_template: str

    @classmethod
    def from_env(cls) -> AgentRunnerConfig:
        app_id_raw = _env_optional("AIDEV_GITHUB_APP_ID")
        return cls(
            database_url=_env(
                "AIDEV_DATABASE_URL",
                _env(
                    "DATABASE_URL",
                    "postgresql+psycopg://aidev:aidev@localhost:5432/aidev",
                ),
            ),
            redis_url=_env(
                "AIDEV_REDIS_URL", _env("REDIS_URL", "redis://localhost:6379/0")
            ),
            agent_pipeline=_env("AIDEV_AGENT_PIPELINE", "mock").lower(),
            sandbox_executor=_env("SANDBOX_EXECUTOR", "mock").lower(),
            github_token=_env_optional("AIDEV_GITHUB_TOKEN")
            or _env_optional("GITHUB_TOKEN"),
            github_app_id=int(app_id_raw) if app_id_raw else None,
            github_app_private_key_path=_env_optional(
                "AIDEV_GITHUB_APP_PRIVATE_KEY_PATH"
            ),
            github_app_installation_id=_env_int(
                "AIDEV_GITHUB_APP_INSTALLATION_ID", 0
            )
            or None,
            model_base_url=_env(
                "AIDEV_MODEL_BASE_URL", "http://localhost:11434/v1"
            ),
            model_name=_env("AIDEV_DEFAULT_MODEL", "llama3.1:8b-instruct"),
            model_api_key=_env("AIDEV_MODEL_API_KEY", "ollama"),
            model_timeout_seconds=_env_int(
                "AIDEV_MODEL_TIMEOUT_SECONDS", 60
            ),
            pr_default_base_branch=_env(
                "AIDEV_PR_DEFAULT_BASE_BRANCH", "main"
            ),
            pr_title_template=_env(
                "AIDEV_PR_TITLE_TEMPLATE", "aidev: {title}"
            ),
            pr_body_template=_env(
                "AIDEV_PR_BODY_TEMPLATE",
                (
                    "Automated PR from the AI Developer platform.\n\n"
                    "Task instruction:\n\n{instruction}\n\n"
                    "Branch: `{branch}`\n"
                    "Pipeline: `{pipeline}` / executor: `{executor}`\n"
                ),
            ),
        )

    # ---- helpers --------------------------------------------------

    @property
    def real_pipeline_active(self) -> bool:
        """Both v0.4 flags must be on for the real pipeline to run."""
        return self.agent_pipeline == "real" and self.sandbox_executor == "docker"

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token) or bool(self.github_app_id)


__all__ = ["AgentRunnerConfig"]
