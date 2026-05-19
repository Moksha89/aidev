"""Planner agent.

v0.4 implementation: ask the local model for a 3-5 step plan, then fall
back to a deterministic 3-step template if the model is unavailable or
produces invalid output. The Planner does not write code — it only
populates ``AgentResult.output['plan']`` for the Frontend agent to read.
"""

from __future__ import annotations

import logging

from aidev_shared import AgentRole

from agent_runner.agents.base import Agent, AgentResult
from agent_runner.llm import LLMClient

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    role = AgentRole.PLANNER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Planner agent.\n"
            "Read the user's instruction and produce a 3-5 step plan.\n"
            "Each step must specify the agent role responsible (frontend,\n"
            "backend, qa, security). Never include backend steps before\n"
            "human approval — the platform will reject them.\n"
            "Output strictly as JSON: {\"plan\": [{\"step\": ..., \"role\": ...}]}."
        )

    def plan(
        self,
        *,
        instruction: str,
        title: str,
        llm: LLMClient | None,
    ) -> AgentResult:
        """Return a plan + a short user-facing chat message.

        Never raises — falls back to a deterministic template on any
        LLM error so the pipeline can always make forward progress.
        """
        plan, used_model = _try_llm_plan(
            instruction=instruction,
            title=title,
            llm=llm,
            system=self.system_prompt,
        )
        if not plan:
            plan = _default_plan(title)

        bullets = "\n".join(
            f"  {i + 1}. {step['step']}" for i, step in enumerate(plan)
        )
        chat = (
            f"Plan for \"{title}\":\n\n{bullets}\n\n"
            "Starting frontend work under the frontend-first allowlist; "
            "backend changes are blocked until you approve."
        )
        return AgentResult(
            agent=self.role,
            log_message=(
                f"Planner produced a {len(plan)}-step plan "
                f"({'model' if used_model else 'fallback'})."
            ),
            chat_message=chat,
            used_model=used_model,
            output={"plan": plan},
        )


def _try_llm_plan(
    *,
    instruction: str,
    title: str,
    llm: LLMClient | None,
    system: str,
) -> tuple[list[dict], bool]:
    if llm is None:
        return [], False
    user = (
        f"Title: {title}\n\n"
        f"Instruction:\n{instruction}\n\n"
        "Return only a JSON object with a `plan` field as described."
    )
    parsed = llm.generate_json(system=system, user=user, max_tokens=1024)
    if not isinstance(parsed, dict):
        return [], False
    plan = parsed.get("plan")
    if not isinstance(plan, list) or not plan:
        return [], False
    cleaned: list[dict] = []
    for raw in plan:
        if not isinstance(raw, dict):
            continue
        step = str(raw.get("step") or "").strip()
        role = str(raw.get("role") or "frontend").strip().lower()
        if not step:
            continue
        # Drop backend steps pre-approval — the rules engine would
        # reject the writes anyway and we don't want to mislead the user.
        if role == "backend":
            continue
        cleaned.append({"step": step, "role": role})
    if not cleaned:
        return [], False
    return cleaned[:5], True


def _default_plan(title: str) -> list[dict]:
    return [
        {
            "step": f"Scaffold the page route and layout for \"{title}\".",
            "role": "frontend",
        },
        {
            "step": "Build the React component with typed mock data.",
            "role": "frontend",
        },
        {
            "step": "Run the test command, then wait for human approval.",
            "role": "qa",
        },
    ]


__all__ = ["PlannerAgent"]
