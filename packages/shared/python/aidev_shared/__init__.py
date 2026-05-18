"""Shared enums and types for the AI Developer platform."""

from aidev_shared.enums import (
    BACKEND_PHASES,
    FRONTEND_PHASES,
    TERMINAL_PHASES,
    AgentRole,
    ApprovalDecision,
    LogLevel,
    TaskPhase,
    is_backend_phase,
    is_frontend_phase,
    is_terminal,
)

__all__ = [
    "BACKEND_PHASES",
    "FRONTEND_PHASES",
    "TERMINAL_PHASES",
    "AgentRole",
    "ApprovalDecision",
    "LogLevel",
    "TaskPhase",
    "is_backend_phase",
    "is_frontend_phase",
    "is_terminal",
]
__version__ = "0.1.0"
