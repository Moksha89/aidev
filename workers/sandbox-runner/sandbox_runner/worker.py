"""Celery application for the sandbox-runner worker.

Mostly a placeholder for v0.1 — the mock executor is invoked
synchronously by the agent-runner. v0.2 splits sandbox jobs out so the
agent process never holds open Docker resources.
"""

from __future__ import annotations

import os

from celery import Celery

_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "aidev_sandbox_runner",
    broker=_BROKER_URL,
    backend=_BROKER_URL,
)
celery_app.conf.task_default_queue = "sandbox-runner"
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_acks_late = True
celery_app.conf.timezone = "UTC"


if __name__ == "__main__":  # pragma: no cover
    celery_app.start()
