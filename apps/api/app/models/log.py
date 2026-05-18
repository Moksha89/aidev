"""Structured logs streamed from the worker, append-only."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class TaskLog(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "task_logs"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    agent_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
