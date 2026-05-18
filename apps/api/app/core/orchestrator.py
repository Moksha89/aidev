"""In-process mock task orchestrator.

This is the MVP demonstration of the multi-agent lifecycle:

    PENDING → PLANNING → FRONTEND_CODING → FRONTEND_QA
            → AWAITING_APPROVAL → BACKEND_CODING → SECURITY_REVIEW
            → PR_OPENED → DONE

It does **not** run a real LLM and does **not** spawn a real sandbox.
It exists so the dashboard has data to render and so we can
demonstrate the approval gate end-to-end without depending on the
worker, model server, or Docker.

In production, the equivalent flow lives in `workers/agent-runner/`
and is driven by Celery — see `docs/ARCHITECTURE.md`.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from aidev_shared import AgentRole, TaskPhase
from sqlalchemy.orm import Session

from app.models import Task, TaskFile, TaskLog, TaskMessage, TaskPreview


@dataclass(frozen=True)
class StepResult:
    phase: TaskPhase
    agent: AgentRole | None
    log: str


# The mock pipeline up to (but not including) human approval.
# After approval, the orchestrator runs the post-approval steps.
_PRE_APPROVAL_STEPS: tuple[StepResult, ...] = (
    StepResult(
        TaskPhase.PLANNING,
        AgentRole.PLANNER,
        "Planner agent: analysing instruction and proposing a 3-step plan.",
    ),
    StepResult(
        TaskPhase.FRONTEND_CODING,
        AgentRole.FRONTEND_DEVELOPER,
        "Frontend agent: scaffolding components, restricted to frontend allowlist.",
    ),
    StepResult(
        TaskPhase.FRONTEND_QA,
        AgentRole.QA,
        "QA agent: running build + Playwright screenshots at five viewports.",
    ),
    StepResult(
        TaskPhase.AWAITING_APPROVAL,
        None,
        "Waiting for human approval before any backend work.",
    ),
)

_POST_APPROVAL_STEPS: tuple[StepResult, ...] = (
    StepResult(
        TaskPhase.BACKEND_UNLOCKED,
        None,
        "Approval recorded — backend paths now writable.",
    ),
    StepResult(
        TaskPhase.BACKEND_CODING,
        AgentRole.BACKEND_DEVELOPER,
        "Backend agent: implementing API endpoints and DB migrations.",
    ),
    StepResult(
        TaskPhase.SECURITY_REVIEW,
        AgentRole.SECURITY_REVIEWER,
        "Security Reviewer: running semgrep / bandit against the diff.",
    ),
    StepResult(
        TaskPhase.PR_OPENED,
        None,
        "Branch pushed and pull request opened on GitHub.",
    ),
    StepResult(
        TaskPhase.DONE,
        None,
        "Task complete.",
    ),
)


_DEMO_FRONTEND_FILES: tuple[tuple[str, str, int, int], ...] = (
    (
        "apps/web/src/app/dashboard/page.tsx",
        "modified",
        24,
        4,
    ),
    (
        "apps/web/src/components/TaskTimeline.tsx",
        "added",
        86,
        0,
    ),
    (
        "apps/web/src/components/ChatPanel.tsx",
        "added",
        72,
        0,
    ),
    (
        "apps/web/src/mocks/tasks.ts",
        "added",
        58,
        0,
    ),
)


_DEMO_VIEWPORTS: tuple[tuple[str, int, int], ...] = (
    ("mobile-375", 375, 812),
    ("mobile-430", 430, 932),
    ("tablet-768", 768, 1024),
    ("desktop-1280", 1280, 800),
    ("desktop-1920", 1920, 1080),
)


def _append_log(
    db: Session,
    task: Task,
    *,
    message: str,
    phase: TaskPhase | None = None,
    agent: AgentRole | None = None,
    level: str = "info",
) -> None:
    sequence = (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task.id)
        .count()
    )
    db.add(
        TaskLog(
            task_id=task.id,
            level=level,
            phase=phase.value if phase else None,
            agent_role=agent.value if agent else None,
            message=message,
            sequence=sequence,
        )
    )


def _append_assistant_message(
    db: Session, task: Task, *, agent: AgentRole | None, content: str
) -> None:
    db.add(
        TaskMessage(
            task_id=task.id,
            role="assistant",
            agent_role=agent.value if agent else None,
            content=content,
        )
    )


def start_task(db: Session, task: Task) -> Task:
    """Drive the mock task to the AWAITING_APPROVAL phase.

    Real implementation: enqueue a Celery job that runs the Planner →
    Frontend → QA agents inside the sandbox.
    """
    if task.phase != TaskPhase.PENDING.value:
        return task

    for step in _PRE_APPROVAL_STEPS:
        task.phase = step.phase.value
        task.active_agent = step.agent.value if step.agent else None
        _append_log(
            db,
            task,
            message=step.log,
            phase=step.phase,
            agent=step.agent,
        )
        if step.agent:
            _append_assistant_message(
                db,
                task,
                agent=step.agent,
                content=_demo_assistant_content(step.agent, task),
            )

    # Seed the demo files + preview screenshots so the dashboard has
    # something concrete to show.
    _seed_demo_files(db, task)
    _seed_demo_previews(db, task)
    task.branch_name = f"aidev/task-{task.id[:8]}"
    task.preview_url = f"https://task-{task.id[:8]}.preview.aidev.local"
    db.flush()
    return task


def approve_frontend(db: Session, task: Task) -> Task:
    """Transition through the post-approval phases.

    Real implementation: re-enqueue the Celery job with phase=BACKEND_UNLOCKED;
    the worker flips the rules engine and resumes the agents.
    """
    if task.phase != TaskPhase.AWAITING_APPROVAL.value:
        return task

    for step in _POST_APPROVAL_STEPS:
        task.phase = step.phase.value
        task.active_agent = step.agent.value if step.agent else None
        _append_log(
            db,
            task,
            message=step.log,
            phase=step.phase,
            agent=step.agent,
        )
        if step.agent:
            _append_assistant_message(
                db,
                task,
                agent=step.agent,
                content=_demo_assistant_content(step.agent, task),
            )

    task.pr_url = (
        f"https://github.com/Moksha89/aidev/pull/{(int(task.id[:6], 16) % 90) + 10}"
    )
    task.pr_number = (int(task.id[:6], 16) % 90) + 10
    db.flush()
    return task


def reject_frontend(db: Session, task: Task, *, reason: str) -> Task:
    if task.phase != TaskPhase.AWAITING_APPROVAL.value:
        return task
    task.phase = TaskPhase.REJECTED.value
    task.active_agent = None
    _append_log(
        db,
        task,
        message=f"Frontend rejected by user. Reason: {reason or 'no reason given'}",
        phase=TaskPhase.REJECTED,
        level="warn",
    )
    db.flush()
    return task


def cancel_task(db: Session, task: Task, *, reason: str = "") -> Task:
    task.phase = TaskPhase.CANCELLED.value
    task.active_agent = None
    _append_log(
        db,
        task,
        message=f"Task cancelled. Reason: {reason or 'no reason given'}",
        phase=TaskPhase.CANCELLED,
        level="warn",
    )
    db.flush()
    return task


# ---------------------------------------------------------------- helpers


def _seed_demo_files(db: Session, task: Task) -> None:
    for path, status, added, removed in _DEMO_FRONTEND_FILES:
        db.add(
            TaskFile(
                task_id=task.id,
                path=path,
                status=status,
                lines_added=added,
                lines_removed=removed,
                diff_snippet=f"@@ {path} @@\n+ // demo diff for {path}\n",
            )
        )


def _seed_demo_previews(db: Session, task: Task) -> None:
    for viewport, width, height in _DEMO_VIEWPORTS:
        db.add(
            TaskPreview(
                task_id=task.id,
                viewport=viewport,
                width=width,
                height=height,
                # served by the API as a deterministic placeholder image
                image_url=(
                    f"/tasks/{task.id}/screenshots/{viewport}.png"
                ),
                route="/dashboard",
                notes="Generated by mock orchestrator.",
            )
        )


def _demo_assistant_content(agent: AgentRole, task: Task) -> str:
    """Short, deterministic message per agent — keeps the chat realistic."""
    title = task.title
    if agent == AgentRole.PLANNER:
        return textwrap.dedent(
            f"""
            I'll break "{title}" into three steps:

            1. Scaffold the page route and layout.
            2. Build the components with typed mock data.
            3. Run Playwright to capture screenshots at all five viewports.

            Starting frontend work now under the frontend-first allowlist.
            """
        ).strip()
    if agent == AgentRole.FRONTEND_DEVELOPER:
        return textwrap.dedent(
            """
            Added the page, two components, and a typed mock module. Lint
            and type-check are clean. Handing off to QA for screenshots
            and waiting for your approval before any backend work.
            """
        ).strip()
    if agent == AgentRole.QA:
        return (
            "Build succeeded. Captured screenshots at "
            "mobile-375, mobile-430, tablet-768, desktop-1280, "
            "and desktop-1920. Preview URL is live."
        )
    if agent == AgentRole.BACKEND_DEVELOPER:
        return (
            "Backend now unlocked. I'll add the endpoints required by "
            "the frontend mocks, plus the Pydantic schemas and an "
            "Alembic migration. Tests included."
        )
    if agent == AgentRole.SECURITY_REVIEWER:
        return (
            "Ran semgrep (OWASP top-ten pack) and bandit against the "
            "diff. No findings. Opening the pull request."
        )
    return ""
