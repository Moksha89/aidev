"""Shell tool — runs commands in the task sandbox.

v0.1 stub: runs locally with no sandbox. v0.2 replaces this with a call
into `workers/sandbox-runner` which executes inside the Docker sandbox.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    truncated_stdout: bool = False


_MAX_OUTPUT = 64 * 1024


def run_command(
    *,
    workspace: str,
    command: str,
    timeout_seconds: int = 600,
) -> CommandResult:
    """Run `command` in `workspace` and return captured output.

    The MVP runs commands directly on the worker host. The sandbox
    runner will provide a Docker-based replacement with network egress
    restricted and resource caps enforced.
    """
    logger.info("run_command (host stub): %s", command)
    proc = subprocess.run(  # noqa: S602 — host stub only, replaced in v0.2
        command,
        cwd=workspace,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    truncated = len(stdout) > _MAX_OUTPUT
    if truncated:
        stdout = stdout[:_MAX_OUTPUT] + "\n…[output truncated]…\n"
    return CommandResult(
        command=command,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr[:_MAX_OUTPUT],
        truncated_stdout=truncated,
    )


__all__ = ["CommandResult", "run_command"]
