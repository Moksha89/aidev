"""Core enums shared across all services.

These mirror `packages/shared/typescript/src/index.ts`. If you change one
side, change the other.
"""

from __future__ import annotations

from enum import StrEnum


class TaskPhase(StrEnum):
    """Lifecycle states for a task.

    The transition graph is enforced by the API; the rules engine keys
    off the phase to decide which paths an agent may write to.
    """

    PENDING = "pending"
    PLANNING = "planning"
    FRONTEND_CODING = "frontend_coding"
    FRONTEND_QA = "frontend_qa"
    AWAITING_APPROVAL = "awaiting_approval"
    BACKEND_UNLOCKED = "backend_unlocked"
    BACKEND_CODING = "backend_coding"
    SECURITY_REVIEW = "security_review"
    PR_OPENED = "pr_opened"
    DONE = "done"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    FAILED = "failed"


class AgentRole(StrEnum):
    """The agent that's currently driving the task."""

    PLANNER = "planner"
    FRONTEND_DEVELOPER = "frontend_developer"
    BACKEND_DEVELOPER = "backend_developer"
    QA = "qa"
    SECURITY_REVIEWER = "security_reviewer"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


FRONTEND_PHASES: frozenset[TaskPhase] = frozenset(
    {
        TaskPhase.PLANNING,
        TaskPhase.FRONTEND_CODING,
        TaskPhase.FRONTEND_QA,
        TaskPhase.AWAITING_APPROVAL,
    }
)

BACKEND_PHASES: frozenset[TaskPhase] = frozenset(
    {
        TaskPhase.BACKEND_UNLOCKED,
        TaskPhase.BACKEND_CODING,
        TaskPhase.SECURITY_REVIEW,
        TaskPhase.PR_OPENED,
    }
)

TERMINAL_PHASES: frozenset[TaskPhase] = frozenset(
    {
        TaskPhase.DONE,
        TaskPhase.REJECTED,
        TaskPhase.CANCELLED,
        TaskPhase.FAILED,
    }
)


def is_frontend_phase(phase: TaskPhase) -> bool:
    """True for phases where the rules engine restricts writes to frontend paths."""
    return phase in FRONTEND_PHASES


def is_backend_phase(phase: TaskPhase) -> bool:
    """True for phases where backend paths become writable."""
    return phase in BACKEND_PHASES


def is_terminal(phase: TaskPhase) -> bool:
    return phase in TERMINAL_PHASES
