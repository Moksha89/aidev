"""Lightweight Celery sender for the FastAPI process.

The API never needs to *run* Celery tasks, only enqueue them. We
instantiate a tiny Celery app pointed at the same Redis broker the
agent-runner uses; calling ``send_task`` is a single round-trip to
Redis with no worker code imported.

The app is cached at module import so the API does not pay the
``Celery()`` setup cost per request. Tests can call
``reset_celery_app`` if they need a fresh client (e.g. to patch the
broker URL).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from celery import Celery

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_celery_app() -> Celery:
    """Return the cached Celery client used by the API to enqueue jobs."""
    settings = get_settings()
    app = Celery(
        "aidev_api_dispatcher",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    # The API never executes tasks; it only sends them. Disable any
    # accidental local execution that might happen if the import order
    # exposes the worker module.
    app.conf.task_always_eager = False
    app.conf.task_default_queue = "agent-runner"
    return app


def reset_celery_app() -> None:
    """Reset the cached Celery client (used by tests after env mutation)."""
    get_celery_app.cache_clear()


def send_task(name: str, *, args: list[Any], queue: str) -> str:
    """Send a Celery task by name, return the task ID.

    Wrapped so the dispatcher (and tests) have a single seam to mock.
    Logs the dispatch at INFO so the API logs show the handoff to the
    agent-runner.
    """
    app = get_celery_app()
    result = app.send_task(name, args=args, queue=queue)
    logger.info(
        "dispatched celery task name=%s queue=%s task_id=%s args=%s",
        name,
        queue,
        result.id,
        args,
    )
    return result.id


__all__ = ["get_celery_app", "reset_celery_app", "send_task"]
