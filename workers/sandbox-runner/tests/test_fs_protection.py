"""Layer-3 filesystem protection plans + shell script rendering."""

from __future__ import annotations

from aidev_shared import TaskPhase

from sandbox_runner.fs_protection import (
    DEFAULT_PROTECTED_PATHS,
    plan_for_phase,
    render_protection_script,
)


def test_frontend_phase_locks_all_backend_paths() -> None:
    plan = plan_for_phase(TaskPhase.FRONTEND_CODING)
    assert plan.unlock_paths == ()
    assert set(plan.lock_paths) == set(DEFAULT_PROTECTED_PATHS)


def test_awaiting_approval_still_locks_backend_paths() -> None:
    plan = plan_for_phase(TaskPhase.AWAITING_APPROVAL)
    assert "apps/api" in plan.lock_paths
    assert "infra" in plan.lock_paths


def test_backend_unlocked_releases_non_env_paths() -> None:
    plan = plan_for_phase(TaskPhase.BACKEND_UNLOCKED)
    assert "apps/api" in plan.unlock_paths
    assert "infra" in plan.unlock_paths
    # .env files MUST stay locked — they're secrets territory in every phase.
    assert all(p.startswith(".env") for p in plan.lock_paths)
    assert ".env" in plan.lock_paths


def test_backend_coding_keeps_env_locked() -> None:
    plan = plan_for_phase(TaskPhase.BACKEND_CODING)
    assert all(p.startswith(".env") for p in plan.lock_paths)


def test_render_script_uses_chmod_and_idempotent_test() -> None:
    plan = plan_for_phase(TaskPhase.FRONTEND_CODING)
    script = render_protection_script(plan, workspace="/workspace")
    assert script.startswith("#!/bin/sh")
    assert "set -eu" in script
    assert "WORKSPACE=\"/workspace\"" in script
    assert "chmod -R a-w,a+rX" in script
    # `[ -e ... ]` guard means the script does not fail if a path
    # doesn't exist in the cloned repo.
    assert "if [ -e" in script
    # Final echo so callers can correlate logs with the applied phase.
    assert "fs-protection applied phase=frontend_coding" in script


def test_render_script_unlock_section_for_backend_phase() -> None:
    plan = plan_for_phase(TaskPhase.BACKEND_UNLOCKED)
    script = render_protection_script(plan)
    assert "chmod -R u+rwX,go+rX" in script


def test_render_script_quotes_path_segments() -> None:
    plan = plan_for_phase(TaskPhase.FRONTEND_CODING)
    script = render_protection_script(plan)
    # apps/api should appear inside single quotes.
    assert "'apps/api'" in script
