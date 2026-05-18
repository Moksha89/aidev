"""Sandbox executor abstraction + implementations."""

from sandbox_runner.base import (
    CommandResult,
    SandboxExecutor,
    SandboxSession,
    build_executor,
)
from sandbox_runner.mock_executor import MockSandboxExecutor

__all__ = [
    "CommandResult",
    "MockSandboxExecutor",
    "SandboxExecutor",
    "SandboxSession",
    "build_executor",
]
__version__ = "0.1.0"
