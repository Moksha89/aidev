"""Security Reviewer agent.

v0.4 implementation: a deterministic, regex-based pass that the post-
approval pipeline runs against the staged file content *before* the
branch is pushed to GitHub. It is not a replacement for semgrep /
bandit — those still live in CI — but it is the last gate that runs
inside the agent-runner with the operator's PAT in scope.

The gate has two outputs:

* :class:`SecurityFinding` per issue, with severity ``critical`` /
  ``high`` / ``medium`` / ``low``.
* A boolean ``blocked`` flag — ``True`` if any ``critical`` / ``high``
  finding is present. When blocked, the pipeline transitions the task
  to ``FAILED`` and surfaces the findings via the task log instead of
  opening a PR.

The detector list is intentionally small and high-signal — the goal is
to catch obviously committed secrets / credentials, not to be a full
SAST suite. False positives can be suppressed with the standard
``# noqa: aidev-security`` / ``// noqa: aidev-security`` markers on
the same line.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from aidev_shared import AgentRole

from agent_runner.agents.base import Agent, AgentResult, FileChange

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityFinding:
    """One issue spotted in a staged file."""

    path: str
    line: int
    severity: str  # critical | high | medium | low
    rule: str
    message: str


@dataclass
class SecurityReport:
    blocked: bool = False
    findings: list[SecurityFinding] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.findings:
            return "Security review: 0 findings."
        by_sev: dict[str, int] = {}
        for f in self.findings:
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        parts = [f"{count} {sev}" for sev, count in sorted(by_sev.items())]
        verdict = "BLOCKED" if self.blocked else "advisory"
        return f"Security review ({verdict}): {', '.join(parts)}."


# Each rule is ``(name, severity, compiled_regex, message)``. We
# deliberately match a small, high-signal set: AWS / GitHub / generic
# bearer credentials. The pipeline still relies on the rules engine
# for path-based blocking; this is the *content* gate.
_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "aws_access_key",
        "critical",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key ID committed",
    ),
    (
        "aws_secret_key",
        "critical",
        re.compile(
            r"(?i)aws(.{0,20})?(secret|sk)[^\n]{0,4}=\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"
        ),
        "Possible AWS secret access key",
    ),
    (
        "github_token",
        "critical",
        re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
        "GitHub personal access token",
    ),
    (
        "github_fine_grained",
        "critical",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "GitHub fine-grained PAT",
    ),
    (
        "private_key_block",
        "critical",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "Private key material committed",
    ),
    (
        "generic_bearer",
        "high",
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
        "Bearer token in source",
    ),
    (
        "hardcoded_password",
        "medium",
        re.compile(
            r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"\n]{6,}['\"]"
        ),
        "Hard-coded password literal",
    ),
)

_SUPPRESS_RE = re.compile(r"(?:#|//)\s*noqa:\s*aidev-security", re.IGNORECASE)


class SecurityReviewerAgent(Agent):
    role = AgentRole.SECURITY_REVIEWER

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Security Reviewer agent.\n"
            "Scan staged changes for committed credentials / private keys\n"
            "before the branch is pushed. Block on any HIGH or CRITICAL\n"
            "finding. Allow inline suppression via `# noqa: aidev-security`\n"
            "with a justification in the PR description."
        )

    def review(self, *, changes: list[FileChange]) -> AgentResult:
        """Scan ``changes`` for committed credentials.

        Returns an :class:`AgentResult` whose ``output['report']`` is a
        :class:`SecurityReport`. The pipeline blocks the PR if
        ``report.blocked`` is ``True``.
        """
        report = SecurityReport()
        for change in changes:
            if change.status == "deleted":
                continue
            for finding in _scan_file(change.path, change.content):
                report.findings.append(finding)
                if finding.severity in {"critical", "high"}:
                    report.blocked = True

        log = report.summary
        if report.blocked:
            log += " Blocking PR."
        return AgentResult(
            agent=self.role,
            log_message=log,
            chat_message=(
                "Security review complete. " + report.summary
                if not report.blocked
                else (
                    "Security review BLOCKED the PR. "
                    + report.summary
                    + " Resolve the findings (or suppress with "
                    "`# noqa: aidev-security` and a justification) and "
                    "restart the task."
                )
            ),
            used_model=False,
            output={
                "report": report,
                "findings": [_finding_dict(f) for f in report.findings],
                "blocked": report.blocked,
            },
        )


def _scan_file(path: str, content: str) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for lineno, raw in enumerate(content.splitlines(), start=1):
        if _SUPPRESS_RE.search(raw):
            continue
        for rule_name, severity, pattern, message in _RULES:
            if pattern.search(raw):
                findings.append(
                    SecurityFinding(
                        path=path,
                        line=lineno,
                        severity=severity,
                        rule=rule_name,
                        message=message,
                    )
                )
    return findings


def _finding_dict(finding: SecurityFinding) -> dict:
    return {
        "path": finding.path,
        "line": finding.line,
        "severity": finding.severity,
        "rule": finding.rule,
        "message": finding.message,
    }


__all__ = [
    "SecurityFinding",
    "SecurityReport",
    "SecurityReviewerAgent",
]
