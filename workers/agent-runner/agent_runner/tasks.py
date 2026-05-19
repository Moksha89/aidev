"""Top-level Celery tasks.

These are the boundary between the FastAPI backend and the agent
pipeline. The API enqueues these tasks via
``apps/api/app/services/celery_client.py``; they delegate to
:mod:`agent_runner.pipeline` which owns the real Docker sandbox and
GitHub PR work.

The task names — ``agent_runner.tasks.run_task`` and
``agent_runner.tasks.resume_after_approval`` — are part of the API's
public contract with the worker. Renaming them is a coordinated
change.
"""

from __future__ import annotations

import logging

from agent_runner import pipeline
from agent_runner.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="agent_runner.tasks.run_task",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def run_task(self, task_id: str) -> dict[str, str]:  # noqa: ARG001
    """Drive a task from PENDING to AWAITING_APPROVAL.

    Retries are disabled (``max_retries=0``) at v0.4 because the
    pipeline already catches every exception and converts it to a
    deterministic ``FAILED`` state; retrying on top of that would
    double-spend sandbox resources without changing the outcome.
    """
    logger.info("run_task: starting pipeline for task_id=%s", task_id)
    return pipeline.run_task_sync(task_id)


@celery_app.task(
    name="agent_runner.tasks.resume_after_approval",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def resume_after_approval(self, task_id: str) -> dict[str, str]:  # noqa: ARG001
    """Drive a task from AWAITING_APPROVAL through to PR_OPENED / DONE."""
    logger.info("resume_after_approval: starting for task_id=%s", task_id)
    return pipeline.resume_after_approval_sync(task_id)
