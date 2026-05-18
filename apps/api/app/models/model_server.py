"""Configured OpenAI-compatible model server endpoints."""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class ModelServer(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "model_servers"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(256), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    server_type: Mapped[str] = mapped_column(String(32), default="openai", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
