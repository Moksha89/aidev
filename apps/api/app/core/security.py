"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_settings = get_settings()
_ALGORITHM = "HS256"
_DEFAULT_TTL = timedelta(hours=12)


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(password, hashed)
    except (ValueError, TypeError):
        return False


def create_access_token(
    *, subject: str, extra_claims: dict[str, Any] | None = None, ttl: timedelta | None = None
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + (ttl or _DEFAULT_TTL)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _settings.aidev_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Returns the decoded payload, or raises `JWTError` on failure."""
    return jwt.decode(token, _settings.aidev_secret_key, algorithms=[_ALGORITHM])


__all__ = [
    "JWTError",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
