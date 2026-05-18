"""Shared mixins used by every ORM model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid_str() -> str:
    return str(uuid4())


class UuidPkMixin:
    """String UUID primary key generated client-side."""

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )


class TimestampMixin:
    """`created_at` / `updated_at` columns kept fresh by SQLAlchemy."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )
