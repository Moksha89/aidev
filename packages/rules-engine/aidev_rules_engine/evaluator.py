"""Decide whether an agent may write to a given path in a given phase."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from aidev_shared import TaskPhase

from aidev_rules_engine.parser import Rule, parse_rules_directory


@dataclass(frozen=True)
class Decision:
    """Outcome of evaluating a write attempt against the active rules."""

    allowed: bool
    reason: str
    matched_rule_id: str | None = None
    matched_pattern: str | None = None

    def __bool__(self) -> bool:  # pragma: no cover — convenience
        return self.allowed


class RuleViolationError(RuntimeError):
    """Raised when a write attempt violates the active rules.

    The `decision` attribute carries the structured reason so callers
    can surface it to the dashboard without re-parsing the message.
    """

    def __init__(self, decision: Decision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


# Backwards-compat alias so call sites that imported the old name keep working.
RuleViolation = RuleViolationError


def _matches(path: str, pattern: str) -> bool:
    """Glob match with `**` semantics that match pathspec/gitignore.

    `fnmatch` treats `**` like a single `*`. We expand a few common cases:
    - `**/foo` matches `foo` at any depth.
    - `foo/**` matches everything under `foo/`.
    - `**` in the middle matches any number of segments.
    """
    norm_path = path.lstrip("./").replace("\\", "/")
    norm_pattern = pattern.replace("\\", "/")

    if "**" not in norm_pattern:
        return fnmatch.fnmatchcase(norm_path, norm_pattern)

    parts = norm_pattern.split("/")
    return _segment_match(norm_path.split("/"), parts)


def _segment_match(path_parts: list[str], pattern_parts: list[str]) -> bool:
    if not pattern_parts:
        return not path_parts
    head, *tail = pattern_parts
    if head == "**":
        if not tail:
            return True
        return any(
            _segment_match(path_parts[i:], tail) for i in range(len(path_parts) + 1)
        )
    if not path_parts:
        return False
    if fnmatch.fnmatchcase(path_parts[0], head):
        return _segment_match(path_parts[1:], tail)
    return False


class Evaluator:
    """Combines a set of rules into an allow/deny oracle."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        self._rules: tuple[Rule, ...] = tuple(rules)

    @classmethod
    def from_directory(cls, directory: str | Path) -> Evaluator:
        return cls(parse_rules_directory(directory))

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def active_rules(self, phase: TaskPhase) -> tuple[Rule, ...]:
        """Return rules whose `applies_to` matches the given phase."""
        out: list[Rule] = []
        phase_name = phase.value.upper()
        for rule in self._rules:
            if rule.applies_to_all_phases:
                out.append(rule)
                continue
            target = rule.target_phase
            if target and target.upper() == phase_name:
                out.append(rule)
        return tuple(out)

    def evaluate_write(self, path: str, phase: TaskPhase) -> Decision:
        """Decide whether `path` may be written in the given `phase`.

        Decision order (highest precedence first):
        1. Any global forbidden match → DENY.
        2. Any phase-specific forbidden match → DENY.
        3. At least one allowed match in the active rule set → ALLOW.
        4. Otherwise → DENY with "no rule explicitly permits this path".
        """
        active = self.active_rules(phase)

        # 1 & 2 — forbidden wins, sorted by priority (already done).
        for rule in active:
            for pattern in rule.forbidden_paths:
                if _matches(path, pattern):
                    return Decision(
                        allowed=False,
                        reason=(
                            f"'{path}' matches forbidden pattern '{pattern}' "
                            f"in rule '{rule.id}' ({rule.title})."
                        ),
                        matched_rule_id=rule.id,
                        matched_pattern=pattern,
                    )

        # 3 — explicit allow in any active rule.
        for rule in active:
            for pattern in rule.allowed_paths:
                if _matches(path, pattern):
                    return Decision(
                        allowed=True,
                        reason=(
                            f"'{path}' matches allowed pattern '{pattern}' "
                            f"in rule '{rule.id}' ({rule.title})."
                        ),
                        matched_rule_id=rule.id,
                        matched_pattern=pattern,
                    )

        # 4 — implicit deny.
        has_any_allowed = any(rule.allowed_paths for rule in active)
        reason = (
            f"'{path}' does not match any allowed pattern for phase "
            f"'{phase.value}'."
            if has_any_allowed
            else f"No allowed paths are configured for phase '{phase.value}'."
        )
        return Decision(allowed=False, reason=reason)

    def assert_write_allowed(self, path: str, phase: TaskPhase) -> None:
        """Raise `RuleViolation` if the write is not allowed."""
        decision = self.evaluate_write(path, phase)
        if not decision.allowed:
            raise RuleViolationError(decision)
