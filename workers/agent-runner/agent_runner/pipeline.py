"""The multi-agent task pipeline.

Stub for v0.1: defines the structure so v0.2 can swap real agents in
without changing the call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aidev_shared import AgentRole, TaskPhase

from agent_runner.agents.backend import BackendAgent
from agent_runner.agents.base import Agent, AgentContext
from agent_runner.agents.frontend import FrontendAgent
from agent_runner.agents.planner import PlannerAgent
from agent_runner.agents.qa import QaAgent
from agent_runner.agents.security import SecurityReviewerAgent


@dataclass
class PipelineResult:
    final_phase: TaskPhase
    transcript: list[str] = field(default_factory=list)


_PRE_APPROVAL: tuple[tuple[TaskPhase, AgentRole | None, type[Agent] | None], ...] = (
    (TaskPhase.PLANNING, AgentRole.PLANNER, PlannerAgent),
    (TaskPhase.FRONTEND_CODING, AgentRole.FRONTEND_DEVELOPER, FrontendAgent),
    (TaskPhase.FRONTEND_QA, AgentRole.QA, QaAgent),
    (TaskPhase.AWAITING_APPROVAL, None, None),
)

_POST_APPROVAL: tuple[tuple[TaskPhase, AgentRole | None, type[Agent] | None], ...] = (
    (TaskPhase.BACKEND_CODING, AgentRole.BACKEND_DEVELOPER, BackendAgent),
    (TaskPhase.SECURITY_REVIEW, AgentRole.SECURITY_REVIEWER, SecurityReviewerAgent),
    (TaskPhase.PR_OPENED, None, None),
    (TaskPhase.DONE, None, None),
)


def run_until_approval(ctx: AgentContext) -> PipelineResult:
    """Stub: walks the pre-approval phases."""
    transcript: list[str] = []
    for phase, role, agent_cls in _PRE_APPROVAL:
        transcript.append(f"phase={phase.value} agent={role.value if role else '-'}")
        if agent_cls is not None and role is not None:
            agent_cls(role=role, ctx=ctx).run()
    return PipelineResult(final_phase=TaskPhase.AWAITING_APPROVAL, transcript=transcript)


def resume_after_approval(ctx: AgentContext) -> PipelineResult:
    """Stub: walks the post-approval phases."""
    transcript: list[str] = []
    for phase, role, agent_cls in _POST_APPROVAL:
        transcript.append(f"phase={phase.value} agent={role.value if role else '-'}")
        if agent_cls is not None and role is not None:
            agent_cls(role=role, ctx=ctx).run()
    return PipelineResult(final_phase=TaskPhase.DONE, transcript=transcript)
