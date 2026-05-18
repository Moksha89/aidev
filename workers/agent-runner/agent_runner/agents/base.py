"""Base class for the five agent roles.

Every agent has the same shape:

1. Build a prompt from the system prompt for its role + the task history.
2. Call the model server via `aidev_model_client.ModelClient`.
3. Parse tool calls out of the response and execute them through the
   gated tool layer.
4. Return when the model signals "done" or after `max_iterations`.

In v0.1, `run()` is a stub that logs the role and returns. This file
defines the contract so v0.2 can drop real implementations in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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


class Agent:
    """Base agent: defines the lifecycle, leaves the loop to subclasses."""

    role: AgentRole

    def __init__(self, *, role: AgentRole, ctx: AgentContext) -> None:
        self.role = role
        self.ctx = ctx

    @property
    def system_prompt(self) -> str:  # pragma: no cover — overridden
        return f"You are the {self.role.value} agent. Follow the platform rules."

    def run(self) -> None:
        """Stub for v0.1: log and return.

        v0.2 will iterate until the model returns a `done` tool call.
        """
        logger.info(
            "agent role=%s phase=%s task=%s — stubbed run",
            self.role.value,
            self.ctx.phase.value,
            self.ctx.task_id,
        )
