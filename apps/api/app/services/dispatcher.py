"""Mock-vs-real pipeline dispatcher.

The single decision point: when a dashboard task is started or
approved, does the work happen synchronously in the API process
(``mock`` orchestrator with demo data) or does it get enqueued to the
Celery agent-runner (``real`` pipeline with a Docker sandbox and a
real GitHub PR)?

Selection rule (v0.4):

    real_mode_active = (
        settings.agent_pipeline == "real"
        and settings.sandbox_executor == "docker"
        and task.repository_id is not None
    )

If *any* of those conditions is false we fall back to the mock
orchestrator. The default deployed configuration has
``agent_pipeline=mock`` and ``sandbox_executor=mock`` so dashboard
tasks are always safely mocked unless the operator explicitly opts
in (and the task has a connected repository).

Both flags must be flipped together: enabling only ``agent_pipeline``
without ``sandbox_executor=docker`` would attempt to spawn a sandbox
that does not exist; enabling only ``sandbox_executor`` keeps the
in-process orchestrator that never calls the sandbox.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core import orchestrator
from app.models import Task
from app.services import celery_client

logger = logging.getLogger(__name__)


REAL_QUEUE = "agent-runner"
RUN_TASK_NAME = "agent_runner.tasks.run_task"
RESUME_TASK_NAME = "agent_runner.tasks.resume_after_approval"


class ExecutionMode(StrEnum):
    MOCK = "mock"
    REAL = "real"


@dataclass(frozen=True)
class DispatchDecision:
    """Why a particular dispatch went mock or real.

    Exposed so the dashboard / logs / tests can see exactly which gate
    failed and why a task was not run through the real pipeline.
    """

    mode: ExecutionMode
    pipeline_setting: str
    executor_setting: str
    has_repository: bool

    @property
    def is_real(self) -> bool:
        return self.mode is ExecutionMode.REAL


def decide_mode(task: Task, settings: Settings | None = None) -> DispatchDecision:
    """Decide whether `task` should be run via the real pipeline."""
    s = settings or get_settings()
    pipeline = s.agent_pipeline
    executor = s.sandbox_executor
    has_repo = task.repository_id is not None
    if pipeline == "real" and executor == "docker" and has_repo:
        return DispatchDecision(
            mode=ExecutionMode.REAL,
            pipeline_setting=pipeline,
            executor_setting=executor,
            has_repository=has_repo,
        )
    return DispatchDecision(
        mode=ExecutionMode.MOCK,
        pipeline_setting=pipeline,
        executor_setting=executor,
        has_repository=has_repo,
    )


def dispatch_start(db: Session, task: Task) -> DispatchDecision:
    """Drive a task from PENDING toward AWAITING_APPROVAL.

    Real-mode: mark the task as ``execution_mode='real'``, transition
    its phase to ``PLANNING`` so the dashboard shows progress
    immediately, and enqueue the agent-runner Celery job. The Celery
    worker is responsible for every subsequent phase update.

    Mock-mode: delegate to the in-process orchestrator, which walks
    the full pre-approval sequence synchronously and seeds demo data.
    """
    decision = decide_mode(task)
    if decision.is_real:
        task.execution_mode = ExecutionMode.REAL.value
        task.phase = "planning"
        task.active_agent = "planner"
        db.flush()
        celery_client.send_task(
            RUN_TASK_NAME, args=[task.id], queue=REAL_QUEUE
        )
        logger.info(
            "dispatch_start: real pipeline task_id=%s repository_id=%s",
            task.id,
            task.repository_id,
        )
        return decision
    task.execution_mode = ExecutionMode.MOCK.value
    orchestrator.start_task(db, task)
    logger.info(
        "dispatch_start: mock pipeline task_id=%s pipeline=%s executor=%s repo=%s",
        task.id,
        decision.pipeline_setting,
        decision.executor_setting,
        decision.has_repository,
    )
    return decision


def dispatch_approve_frontend(db: Session, task: Task) -> DispatchDecision:
    """Transition an AWAITING_APPROVAL task forward.

    Real-mode is determined by the task's stored ``execution_mode``,
    not by the current settings — if the operator flipped the flag
    after the task was started we still need to follow the same
    pipeline so we don't, e.g., mock-out a real branch that the
    sandbox actually wrote to GitHub.
    """
    if task.execution_mode == ExecutionMode.REAL.value:
        task.phase = "security_review"
        task.active_agent = "security_reviewer"
        db.flush()
        celery_client.send_task(
            RESUME_TASK_NAME, args=[task.id], queue=REAL_QUEUE
        )
        logger.info(
            "dispatch_approve_frontend: real pipeline task_id=%s", task.id
        )
        return DispatchDecision(
            mode=ExecutionMode.REAL,
            pipeline_setting=get_settings().agent_pipeline,
            executor_setting=get_settings().sandbox_executor,
            has_repository=task.repository_id is not None,
        )
    orchestrator.approve_frontend(db, task)
    return DispatchDecision(
        mode=ExecutionMode.MOCK,
        pipeline_setting=get_settings().agent_pipeline,
        executor_setting=get_settings().sandbox_executor,
        has_repository=task.repository_id is not None,
    )


__all__ = [
    "DispatchDecision",
    "ExecutionMode",
    "REAL_QUEUE",
    "RESUME_TASK_NAME",
    "RUN_TASK_NAME",
    "decide_mode",
    "dispatch_approve_frontend",
    "dispatch_start",
]
