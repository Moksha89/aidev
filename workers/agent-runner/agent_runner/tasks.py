"""Top-level Celery tasks.

These are the boundary between the FastAPI backend and the agent
pipeline. The API enqueues these tasks; they call into `pipeline.py`
which runs the agents.

In v0.1 they are stubs that just log the transition — the same work is
done synchronously by `apps/api/app/core/orchestrator.py`. They are
included here so the wire is in place for v0.2.
"""

from __future__ import annotations

import logging

from agent_runner.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="agent_runner.tasks.run_task", bind=True, max_retries=2)
def run_task(self, task_id: str) -> dict[str, str]:  # noqa: ARG001
    """Drive a task from PENDING to AWAITING_APPROVAL."""
    logger.info("run_task: starting pipeline for task_id=%s", task_id)
    # See `pipeline.run_until_approval` for the real implementation.
    return {"task_id": task_id, "phase": "awaiting_approval"}


@celery_app.task(name="agent_runner.tasks.resume_after_approval", bind=True, max_retries=2)
def resume_after_approval(self, task_id: str) -> dict[str, str]:  # noqa: ARG001
    """Drive a task from BACKEND_UNLOCKED through to PR_OPENED."""
    logger.info("resume_after_approval: task_id=%s", task_id)
    return {"task_id": task_id, "phase": "pr_opened"}
