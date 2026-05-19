"""Centralised configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the API.

    Read once at startup and cached. Never reach into `os.environ`
    elsewhere in the codebase.

    Env vars use the `AIDEV_` prefix in deployment (set by
    `infra/docker-compose.yml` and `infra/.env`); the unprefixed name
    is accepted as a fallback so local pytest runs that set
    `DATABASE_URL` etc. keep working.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- runtime ---
    aidev_env: Literal["development", "staging", "production"] = "development"
    aidev_secret_key: str = "dev-only-change-me-please"

    # --- storage ---
    database_url: str = Field(
        default="postgresql+psycopg://aidev:aidev@localhost:5432/aidev",
        validation_alias=AliasChoices("AIDEV_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("AIDEV_REDIS_URL", "REDIS_URL"),
    )

    # --- model server ---
    model_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias=AliasChoices("AIDEV_MODEL_BASE_URL", "MODEL_BASE_URL"),
    )
    model_name: str = Field(
        default="qwen2.5-coder:14b",
        validation_alias=AliasChoices(
            "AIDEV_DEFAULT_MODEL", "MODEL_NAME", "AIDEV_MODEL_NAME"
        ),
    )
    model_api_key: str = Field(
        default="ollama",
        validation_alias=AliasChoices("AIDEV_MODEL_API_KEY", "MODEL_API_KEY"),
    )

    # --- GitHub ---
    # ``AIDEV_GITHUB_TOKEN`` is the v0.4 canonical name (also documented
    # in ``infra/.env.example``); ``GITHUB_TOKEN`` is accepted as a
    # fallback so existing deployments keep working unchanged.
    github_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AIDEV_GITHUB_TOKEN", "GITHUB_TOKEN"),
    )
    github_app_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("AIDEV_GITHUB_APP_ID", "GITHUB_APP_ID"),
    )
    github_app_private_key_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AIDEV_GITHUB_APP_PRIVATE_KEY_PATH", "GITHUB_APP_PRIVATE_KEY_PATH"
        ),
    )
    github_app_installation_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AIDEV_GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_INSTALLATION_ID"
        ),
    )
    github_webhook_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AIDEV_GITHUB_WEBHOOK_SECRET", "GITHUB_WEBHOOK_SECRET"
        ),
    )

    # --- CORS ---
    cors_origins: str = Field(
        default="http://localhost:3000,http://aidev.local",
        validation_alias=AliasChoices("AIDEV_CORS_ORIGINS", "CORS_ORIGINS"),
    )

    # --- bootstrap admin (used by the first-run seeder) ---
    admin_email: str = Field(
        default="admin@aidev.local",
        validation_alias=AliasChoices("AIDEV_ADMIN_EMAIL", "ADMIN_EMAIL"),
    )
    admin_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AIDEV_ADMIN_PASSWORD", "ADMIN_PASSWORD"),
    )

    # --- sandbox ---
    sandbox_executor: Literal["mock", "docker"] = "mock"

    # --- agent pipeline ---
    # v0.4: `mock` (default) keeps the in-process orchestrator that ships
    # demo data; `real` enqueues the Celery agent-runner pipeline that
    # spawns the real Docker sandbox, calls the local model server, and
    # opens a real PR on the connected repository. The real path also
    # requires ``sandbox_executor=docker``; if either flag is missing the
    # API falls back to the mock orchestrator so dashboard tasks never
    # touch a real repository.
    agent_pipeline: Literal["mock", "real"] = Field(
        default="mock",
        validation_alias=AliasChoices("AIDEV_AGENT_PIPELINE", "AGENT_PIPELINE"),
    )

    # --- misc ---
    audit_retention_days: int = 365

    # --- derived ---
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.aidev_env == "production"

    # Avoid Pydantic v2 protected-namespace warning on "model_*" fields.
    @classmethod
    def settings_customise_sources(cls, settings_cls, *args, **kwargs):
        return super().settings_customise_sources(settings_cls, *args, **kwargs)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_env_file=".env")  # type: ignore[call-arg]


# Silence the pydantic v2 "model_" namespace warning at import time;
# we deliberately use `model_name`, `model_base_url`, etc.
Settings.model_config["protected_namespaces"] = ()  # type: ignore[index]


__all__ = ["Settings", "get_settings"]
