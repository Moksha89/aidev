"""Security Reviewer agent."""

from __future__ import annotations

from agent_runner.agents.base import Agent


class SecurityReviewerAgent(Agent):
    @property
    def system_prompt(self) -> str:
        return (
            "You are the Security Reviewer agent.\n"
            "Run semgrep with the OWASP top-ten pack, bandit on touched\n"
            "Python files, and npm/pip audit on lockfiles.\n"
            "Block the PR if any HIGH/CRITICAL finding is real.\n"
            "False positives must be marked with `# nosec: <reason>` or\n"
            "`// semgrep-ignore: <reason>` and the reason justified in\n"
            "the PR description.\n"
            "When complete, signal `done` with a structured report."
        )
