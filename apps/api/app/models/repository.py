"""Repositories — a GitHub repo linked to a project."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import TimestampMixin, UuidPkMixin


class Repository(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "repositories"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    github_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    github_name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), default="main", nullable=False)
    html_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    @property
    def full_name(self) -> str:
        return f"{self.github_owner}/{self.github_name}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Repository {self.full_name}>"
