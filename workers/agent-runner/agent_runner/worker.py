"""Celery application + task registration."""

from __future__ import annotations

import os

from celery import Celery

_BROKER_URL = (
    os.environ.get("AIDEV_REDIS_URL")
    or os.environ.get("REDIS_URL")
    or "redis://localhost:6379/0"
)
_BACKEND_URL = os.environ.get("CELERY_RESULT_BACKEND", _BROKER_URL)

celery_app = Celery(
    "aidev_agent_runner",
    broker=_BROKER_URL,
    backend=_BACKEND_URL,
    include=["agent_runner.tasks"],
)
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_default_queue = "agent-runner"
celery_app.conf.timezone = "UTC"
celery_app.conf.task_routes = {
    "agent_runner.tasks.run_task": {"queue": "agent-runner"},
    "agent_runner.tasks.resume_after_approval": {"queue": "agent-runner"},
}


if __name__ == "__main__":  # pragma: no cover
    celery_app.start()
