"""Per-project rule-set overrides (additive to the global .ai-rules)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class RuleSet(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "rule_sets"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    extra_forbidden_globs: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extra_allowed_globs: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
