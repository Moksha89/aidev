"""Centralised configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the API.

    Read once at startup and cached. Never reach into `os.environ`
    elsewhere in the codebase.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- runtime ---
    aidev_env: Literal["development", "staging", "production"] = "development"
    aidev_secret_key: str = "dev-only-change-me-please"

    # --- storage ---
    database_url: str = (
        "postgresql+psycopg://aidev:aidev@localhost:5432/aidev"
    )
    redis_url: str = "redis://localhost:6379/0"

    # --- model server ---
    model_base_url: str = "http://localhost:11434/v1"
    model_name: str = "qwen2.5-coder:14b"
    model_api_key: str = "ollama"

    # --- GitHub ---
    github_token: str | None = None
    github_app_id: int | None = None
    github_app_private_key_path: str | None = None
    github_app_installation_id: int | None = None
    github_webhook_secret: str | None = None

    # --- CORS ---
    cors_origins: str = "http://localhost:3000,http://aidev.local"

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
