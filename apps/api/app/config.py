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
    github_token: str | None = None
    github_app_id: int | None = None
    github_app_private_key_path: str | None = None
    github_app_installation_id: int | None = None
    github_webhook_secret: str | None = None

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
