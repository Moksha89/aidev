"""Database access for the agent-runner worker.

The worker re-declares a minimal subset of the ``apps/api`` ORM models so
it can talk to the same Postgres without taking a runtime dependency on
``apps/api`` itself (which would pull in FastAPI / uvicorn / passlib).

Schema parity is enforced by tests in ``apps/api/tests`` and by the
shared Alembic migration in ``apps/api/alembic``. Adding a new column on
the API side that the worker needs is a two-step diff (migration +
model entry here).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import AgentRunnerConfig


class Base(DeclarativeBase):
    """Local declarative base — separate from the API's so each process
    owns its own metadata. The schema must match the API's Alembic
    migrations because both processes read/write the same tables.
    """


# --- mixin --------------------------------------------------------------


class _UuidPkMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)


class _TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# --- models -------------------------------------------------------------


class Repository(_UuidPkMixin, _TimestampMixin, Base):
    __tablename__ = "repositories"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    github_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    github_name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(128), default="main", nullable=False
    )
    html_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    @property
    def full_name(self) -> str:
        return f"{self.github_owner}/{self.github_name}"


class Task(_UuidPkMixin, _TimestampMixin, Base):
    __tablename__ = "tasks"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    creator_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    active_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_mode: Mapped[str] = mapped_column(
        String(16), default="mock", nullable=False
    )
    branch_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskFile(_UuidPkMixin, _TimestampMixin, Base):
    __tablename__ = "task_files"

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    lines_added: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    lines_removed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    diff_snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_b64: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskLog(_UuidPkMixin, _TimestampMixin, Base):
    __tablename__ = "task_logs"

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    agent_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TaskMessage(_UuidPkMixin, _TimestampMixin, Base):
    __tablename__ = "task_messages"

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)


# --- engine / session ---------------------------------------------------


@lru_cache(maxsize=1)
def _engine(database_url: str):  # noqa: ANN202 — sqlalchemy Engine
    return create_engine(database_url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(
        bind=_engine(database_url), autoflush=False, expire_on_commit=False
    )


@contextmanager
def session_scope(config: AgentRunnerConfig) -> Iterator[Session]:
    """Yield a SQLAlchemy session that commits on success / rolls back."""
    factory = _session_factory(config.database_url)
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


__all__ = [
    "Base",
    "Repository",
    "Task",
    "TaskFile",
    "TaskLog",
    "TaskMessage",
    "session_scope",
]
