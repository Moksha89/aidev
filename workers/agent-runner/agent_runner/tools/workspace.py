"""Workspace tool — validates every write against the rules engine."""

from __future__ import annotations

import os
from dataclasses import dataclass

from aidev_rules_engine import Evaluator, RuleViolation
from aidev_shared import TaskPhase


@dataclass(frozen=True)
class WriteResult:
    path: str
    bytes_written: int


def write_file(
    *,
    workspace: str,
    relative_path: str,
    content: str,
    phase: TaskPhase,
    evaluator: Evaluator,
) -> WriteResult:
    """Write a file under `workspace/relative_path` only if the rules
    engine approves it for the given phase.

    Raises:
        RuleViolation: when the path is forbidden in the current phase.
        ValueError: when the path tries to escape the workspace (e.g. `..`).
    """
    normalised = os.path.normpath(relative_path).replace(os.sep, "/")
    if normalised.startswith("../") or normalised == ".." or normalised.startswith("/"):
        raise ValueError(
            f"Refusing to write outside workspace: {relative_path!r}"
        )

    evaluator.assert_write_allowed(normalised, phase)

    full = os.path.join(workspace, normalised)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        n = f.write(content)
    return WriteResult(path=normalised, bytes_written=n)


__all__ = ["RuleViolation", "WriteResult", "write_file"]
