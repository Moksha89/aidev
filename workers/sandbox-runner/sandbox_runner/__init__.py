"""Sandbox executor abstraction + implementations."""

from sandbox_runner.base import (
    CommandResult,
    SandboxExecutor,
    SandboxSession,
    build_executor,
)
from sandbox_runner.config import SandboxConfig
from sandbox_runner.docker_executor import (
    DockerSandboxExecutor,
    SandboxCommandError,
    SandboxLaunchError,
)
from sandbox_runner.egress import (
    DEFAULT_ALLOWLIST,
    build_allowlist,
    proxy_env,
    render_tinyproxy_filter,
)
from sandbox_runner.event_stream import EventStream, SandboxEvent
from sandbox_runner.fs_protection import (
    DEFAULT_PROTECTED_PATHS,
    FilesystemProtectionPlan,
    plan_for_phase,
    render_protection_script,
)
from sandbox_runner.mock_executor import MockSandboxExecutor
from sandbox_runner.preview import (
    PreviewRegistrar,
    PreviewRoute,
    render_dynamic_config,
)

__all__ = [
    "CommandResult",
    "DEFAULT_ALLOWLIST",
    "DEFAULT_PROTECTED_PATHS",
    "DockerSandboxExecutor",
    "EventStream",
    "FilesystemProtectionPlan",
    "MockSandboxExecutor",
    "PreviewRegistrar",
    "PreviewRoute",
    "SandboxCommandError",
    "SandboxConfig",
    "SandboxEvent",
    "SandboxExecutor",
    "SandboxLaunchError",
    "SandboxSession",
    "build_allowlist",
    "build_executor",
    "plan_for_phase",
    "proxy_env",
    "render_dynamic_config",
    "render_protection_script",
    "render_tinyproxy_filter",
]
__version__ = "0.2.0"
