"""Gated tool layer used by the agents.

Every tool call here is the only way an agent affects the workspace,
runs a command, or generates a screenshot. The wrappers enforce the
rules engine and (in v0.2) the sandbox boundary.
"""

from agent_runner.tools.playwright import capture_screenshot
from agent_runner.tools.shell import run_command
from agent_runner.tools.workspace import write_file

__all__ = ["capture_screenshot", "run_command", "write_file"]
