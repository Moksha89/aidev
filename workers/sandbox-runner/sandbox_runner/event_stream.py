"""Stream sandbox lifecycle events to Redis so the API can fan them out.

Every meaningful step inside the sandbox (container started, file
written, command run, screenshot captured, container removed) publishes
a small JSON envelope on a single Redis pub/sub channel. The API
subscribes and tees them into `task_logs` and the dashboard's live
activity panel.

We deliberately keep the schema small and stable; future event kinds
can be added without breaking older consumers because they ignore
unknown `kind`s.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SandboxEvent:
    """One event published to the pub/sub channel."""

    task_id: str
    kind: str
    payload: dict[str, Any]
    timestamp: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "task_id": self.task_id,
                "kind": self.kind,
                "payload": self.payload,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class _RedisPublisher(Protocol):
    def publish(self, channel: str, message: str) -> int: ...
    def close(self) -> None: ...


class EventStream:
    """Thin wrapper around redis-py's publish.

    Two design choices:

    * **No buffering** — events are best-effort, fire-and-forget, and
      we'd rather lose a log line than block the executor.
    * **No subscriber side here** — the API owns the subscriber. This
      keeps the worker dependency-light (only `redis`, no aio).
    """

    def __init__(
        self,
        *,
        redis_url: str,
        channel: str = "aidev.sandbox.events",
        client: _RedisPublisher | None = None,
    ) -> None:
        self._channel = channel
        self._url = redis_url
        self._client = client
        self._owns_client = client is None

    def _ensure_client(self) -> _RedisPublisher | None:
        if self._client is not None:
            return self._client
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "redis package not installed; sandbox events will be dropped"
            )
            return None
        try:
            self._client = redis.Redis.from_url(self._url, decode_responses=True)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("could not connect to redis at %s: %s", self._url, exc)
            return None
        return self._client

    def publish(self, *, task_id: str, kind: str, payload: dict[str, Any]) -> bool:
        """Publish one event. Returns True if the publish was attempted."""

        client = self._ensure_client()
        event = SandboxEvent(
            task_id=task_id,
            kind=kind,
            payload=payload,
            timestamp=time.time(),
        )
        if client is None:
            logger.debug("event dropped (no redis): %s", event.to_json())
            return False
        try:
            client.publish(self._channel, event.to_json())
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "could not publish event to redis (kind=%s task=%s): %s",
                kind,
                task_id,
                exc,
            )
            return False
        return True

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            # Best-effort: redis client may already be torn down.
            with contextlib.suppress(Exception):  # pragma: no cover
                self._client.close()


__all__ = ["EventStream", "SandboxEvent"]
