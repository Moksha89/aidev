"""Base class for the five agent roles.

Every agent has the same shape:

1. Build a prompt from the system prompt for its role + the task instruction.
2. Optionally call the model server via :class:`~agent_runner.llm.LLMClient`.
3. Produce an :class:`AgentResult` describing the file changes the
   pipeline should apply and the messages it should append.

v0.4 deliberately keeps the loop one-shot — no tool calling, no
multi-turn iteration. The pipeline orchestrator (``pipeline.py``)
applies changes through the sandbox, captures the diff, and hands off
to the next agent. Earlier v0.1 stubs are kept working: the
``ctx``-based constructor still exists for existing tests, and the
zero-arg :meth:`run` still returns ``None``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from aidev_rules_engine import Evaluator
from aidev_shared import AgentRole, TaskPhase

logger = logging.getLogger(__name__)


class ModelCallable(Protocol):
    """Protocol matching `aidev_model_client.ModelClient.chat`."""

    def chat(self, *, messages: list, temperature: float = 0.2) -> object: ...


@dataclass
class AgentContext:
    """Everything an agent needs to run.

    Built once per task and passed to each agent.
    """

    task_id: str
    workspace_path: str
    phase: TaskPhase
    evaluator: Evaluator
    model: ModelCallable | None = None
    max_iterations: int = 16


@dataclass(frozen=True)
class FileChange:
    """A file the agent wants the pipeline to write into the sandbox.

    The pipeline routes every write through the rules engine; the agent
    only proposes paths and content.
    """

    path: str
    content: str
    status: str = "added"  # added | modified | deleted


@dataclass
class AgentResult:
    """Structured output from one :meth:`Agent.run` invocation.

    Attributes:
        agent: which role produced this result.
        log_message: short, human-readable summary written to ``task_logs``.
        chat_message: full assistant message written to ``task_messages``;
            ``None`` to skip the user-facing chat append.
        changes: ordered file changes the pipeline should apply.
        used_model: ``True`` if the agent successfully called the local
            model server; ``False`` if it fell back to a deterministic
            template (model unavailable / invalid output).
        output: free-form structured payload for chained agents.
    """

    agent: AgentRole
    log_message: str
    chat_message: str | None = None
    changes: list[FileChange] = field(default_factory=list)
    used_model: bool = False
    output: dict = field(default_factory=dict)


class Agent:
    """Base agent: defines the lifecycle, leaves the loop to subclasses."""

    role: AgentRole

    def __init__(
        self,
        *,
        role: AgentRole | None = None,
        ctx: AgentContext | None = None,
    ) -> None:
        if role is not None:
            self.role = role
        self.ctx = ctx

    @property
    def system_prompt(self) -> str:  # pragma: no cover — overridden
        return f"You are the {self.role.value} agent. Follow the platform rules."

    def run(self) -> None:  # noqa: D401
        """v0.1 stub.

        Concrete v0.4 agents implement their own ``run(...)`` with the
        signature their pipeline step expects (see ``planner.py``,
        ``frontend.py``, ``security.py``). This base ``run()`` exists
        only so unit tests that instantiate the stub agents keep
        working.
        """
        logger.info(
            "agent role=%s — base stub run (override in subclass)",
            self.role.value,
        )
