"""Approve/reject audit trail."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class TaskApproval(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "task_approvals"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved | rejected
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
