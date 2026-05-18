"""Per-task preview URL and Playwright screenshots."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class TaskPreview(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "task_previews"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    viewport: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    route: Mapped[str] = mapped_column(String(512), default="/", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
