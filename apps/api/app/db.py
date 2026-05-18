"""SQLAlchemy engine + session factory."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()
_engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
if _settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(_settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, future=True
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a request-scoped DB session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
