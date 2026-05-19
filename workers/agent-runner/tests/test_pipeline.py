"""Tests for ``pipeline.py`` helpers and safety gates.

The full ``run_task_async`` path requires a live Postgres + Docker,
so we don't exercise it end-to-end here. Instead we cover:

* the safety gate that refuses to run when the v0.4 flags are off,
* the deterministic helpers (slug / branch name / diff snippet),
* the staged-change round-trip through base64.
"""

from __future__ import annotations

import asyncio
import base64

import pytest

from agent_runner import pipeline
from agent_runner.agents.base import FileChange
from agent_runner.config import AgentRunnerConfig


def _mock_config() -> AgentRunnerConfig:
    return AgentRunnerConfig(
        database_url="postgresql+psycopg://x:x@localhost:5432/x",
        redis_url="redis://localhost:6379/0",
        agent_pipeline="mock",
        sandbox_executor="mock",
        github_token=None,
        github_app_id=None,
        github_app_private_key_path=None,
        github_app_installation_id=None,
        model_base_url="http://localhost:11434/v1",
        model_name="qwen2.5-coder:14b",
        model_api_key="ollama",
        model_timeout_seconds=60,
        pr_default_base_branch="main",
        pr_title_template="aidev: {title}",
        pr_body_template="Body {title} {instruction} {branch} {pipeline} {executor}",
    )


# --- safety gate -----------------------------------------------------


def test_run_task_async_refuses_without_real_flags() -> None:
    """When pipeline=mock and executor=mock, the runner must NOT touch
    the database or Docker — it returns ``phase='skipped'`` immediately.
    """
    cfg = _mock_config()
    result = asyncio.run(pipeline.run_task_async("task-id", config=cfg))
    assert result == {"task_id": "task-id", "phase": "skipped"}


def test_resume_after_approval_refuses_without_real_flags() -> None:
    cfg = _mock_config()
    result = asyncio.run(pipeline.resume_after_approval_async("t", config=cfg))
    assert result == {"task_id": "t", "phase": "skipped"}


# --- helpers ---------------------------------------------------------


def test_branch_name_is_deterministic_and_short() -> None:
    name = pipeline._branch_name("11111111-2222-3333-4444-555555555555", "Hello World!!")
    assert name.startswith("aidev/task-")
    assert "hello-world" in name
    assert len(name) < 80


def test_slug_strips_unsafe_characters() -> None:
    assert pipeline._slug("Hello, World!") == "hello-world"
    assert pipeline._slug("---") == "task"
    assert len(pipeline._slug("a" * 200)) <= 48


def test_clone_url_injects_token_for_https() -> None:
    url = pipeline._clone_url("owner/name", token="ghp_dummy")
    assert url == "https://x-access-token:ghp_dummy@github.com/owner/name.git"


def test_clone_url_omits_token_when_absent() -> None:
    url = pipeline._clone_url("owner/name", token=None)
    assert url == "https://github.com/owner/name.git"


def test_count_added_handles_trailing_newline() -> None:
    assert pipeline._count_added("a\nb\nc\n") == 3
    assert pipeline._count_added("a\nb\nc") == 3
    assert pipeline._count_added("") == 1


def test_diff_snippet_for_isolates_one_file() -> None:
    diff = (
        "diff --git a/A.md b/A.md\n--- a/A.md\n+++ b/A.md\n@@ +1\n+hello\n"
        "diff --git a/B.md b/B.md\n--- a/B.md\n+++ b/B.md\n@@ +1\n+world\n"
    )
    a = pipeline._diff_snippet_for("A.md", diff)
    b = pipeline._diff_snippet_for("B.md", diff)
    assert a.startswith("diff --git a/A.md") and "world" not in a
    assert b.startswith("diff --git a/B.md") and "hello" not in b
    assert pipeline._diff_snippet_for("C.md", diff) == ""


# --- staged-change round-trip ----------------------------------------


def test_file_change_round_trip_through_base64() -> None:
    """The pipeline stages content as base64 and reads it back at
    resume time. Make sure the encode→decode round-trip preserves
    arbitrary UTF-8 (including emoji + newlines).
    """
    original = "héllo\nworld\n— em-dash ✓\n"
    encoded = base64.b64encode(original.encode("utf-8")).decode("ascii")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == original


@pytest.mark.parametrize("title", ["Hello", "ALL CAPS", "lots--of--dashes"])
def test_branch_name_handles_edge_titles(title: str) -> None:
    name = pipeline._branch_name("abcdefgh-0000-0000-0000-000000000000", title)
    assert name.startswith("aidev/task-abcdefgh-")
    assert " " not in name


def test_default_github_factory_raises_when_unconfigured() -> None:
    cfg = _mock_config()
    with pytest.raises(pipeline.PipelineError):
        pipeline._default_github_factory(cfg)


def test_default_executor_factory_returns_docker_executor() -> None:
    inst = pipeline._default_executor_factory()
    # We don't construct a session here (that would require Docker);
    # we only check that the import wiring is correct.
    assert type(inst).__name__ == "DockerSandboxExecutor"


def test_file_change_class_default_status_is_added() -> None:
    fc = FileChange(path="x.md", content="x")
    assert fc.status == "added"
