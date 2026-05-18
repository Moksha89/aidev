"""Tasks — one instruction → one branch → (optionally) one PR."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class Task(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    creator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    active_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task {self.id} phase={self.phase}>"
