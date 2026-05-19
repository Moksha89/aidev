"""Files changed in the task workspace."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class TaskFile(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "task_files"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # added | modified | deleted
    lines_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lines_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    diff_snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # v0.4: full file content (base64-encoded UTF-8) staged by the real
    # pipeline between AWAITING_APPROVAL and the post-approval commit.
    # Only populated when the task ran under ``execution_mode='real'``
    # and the file is meant to be part of the PR. ``NULL`` for the mock
    # pipeline (diff_snippet is the only artefact it generates).
    content_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
