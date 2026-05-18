"""Planner agent."""

from __future__ import annotations

from agent_runner.agents.base import Agent


class PlannerAgent(Agent):
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
