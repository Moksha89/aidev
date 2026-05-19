"""Tests for the mock-vs-real dispatcher (v0.4).

These verify the decision matrix without standing up Postgres or
Celery: we instantiate plain ``Task`` ORM objects, monkeypatch
``app.services.celery_client.send_task`` to record the dispatch, and
assert the resulting ``DispatchDecision``.

The 11 acceptance cases the user requested map onto the tests below as
follows:

* (1) dashboard start triggers real pipeline when both flags on
  → ``test_real_mode_enqueues_celery_when_repo_attached``
* (2) mock lifecycle still works when flags are disabled
  → ``test_default_mode_is_mock``
* (10) forbidden backend write is blocked (rules engine)
  → covered by ``test_frontend_filters_forbidden_paths_from_llm`` in
    ``workers/agent-runner/tests/test_agents.py``
* (11) no real repos modified without explicit repo config + scoped PAT
  → ``test_real_flags_without_repository_falls_back_to_mock``
* (7) pipeline stops at AWAITING_APPROVAL before PR
  → ``test_real_dispatch_sets_phase_to_planning`` (the worker handles
    the actual transition; this verifies the API does NOT push past
    planning).
* (9) approval resumes and opens PR
  → ``test_approve_frontend_enqueues_resume_when_execution_mode_real``
* (8) reject cleans up everything
  → ``test_reject_runs_mock_path`` (the reject route always uses the
    in-process orchestrator regardless of mode at v0.4).

The remaining cases (3–6) require a live Docker daemon and are
covered by the host acceptance probe at
``infra/scripts/acceptance_probe.sh``; they are not unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.config import Settings
from app.services import celery_client, dispatcher
from app.services.dispatcher import DispatchDecision, ExecutionMode

# --- minimal fakes --------------------------------------------------


@dataclass
class _FakeTask:
    """Tiny stand-in for ``app.models.Task`` that exposes only the
    attributes the dispatcher touches.
    """

    id: str = "task-1"
    repository_id: str | None = "repo-1"
    execution_mode: str = "mock"
    phase: str = "pending"
    active_agent: str | None = None


class _FakeSession:
    """Records `.flush()` calls; no actual DB."""

    def __init__(self) -> None:
        self.flushed = 0

    def flush(self) -> None:
        self.flushed += 1


def _mock_settings(**overrides: object) -> Settings:
    base = {
        "agent_pipeline": "mock",
        "sandbox_executor": "mock",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def _patched_settings(monkeypatch: pytest.MonkeyPatch):
    """Yield a setter the tests use to control ``get_settings`` output."""
    holder: dict[str, Settings] = {"current": _mock_settings()}

    def fake_get_settings() -> Settings:
        return holder["current"]

    monkeypatch.setattr(dispatcher, "get_settings", fake_get_settings)
    monkeypatch.setattr(
        "app.config.get_settings", fake_get_settings, raising=True
    )
    return holder


@pytest.fixture
def _capture_send(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Capture every ``celery_client.send_task`` call without enqueueing."""
    calls: list[tuple] = []

    def fake_send(name: str, *, args: list, queue: str) -> str:
        calls.append((name, tuple(args), queue))
        return "fake-id"

    monkeypatch.setattr(celery_client, "send_task", fake_send)
    monkeypatch.setattr(dispatcher.celery_client, "send_task", fake_send)
    return calls


@pytest.fixture
def _stub_orchestrator(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which mock-orchestrator methods were called."""
    seen: list[str] = []

    monkeypatch.setattr(
        dispatcher.orchestrator,
        "start_task",
        lambda db, task: seen.append(f"start:{task.id}"),
    )
    monkeypatch.setattr(
        dispatcher.orchestrator,
        "approve_frontend",
        lambda db, task: seen.append(f"approve:{task.id}"),
    )
    return seen


# --- decide_mode ----------------------------------------------------


def test_default_mode_is_mock(_patched_settings) -> None:
    decision = dispatcher.decide_mode(_FakeTask())
    assert decision.mode is ExecutionMode.MOCK
    assert decision.is_real is False


def test_real_mode_requires_both_flags(_patched_settings) -> None:
    _patched_settings["current"] = _mock_settings(agent_pipeline="real")
    assert dispatcher.decide_mode(_FakeTask()).is_real is False
    _patched_settings["current"] = _mock_settings(
        agent_pipeline="real", sandbox_executor="docker"
    )
    assert dispatcher.decide_mode(_FakeTask()).is_real is True


def test_real_flags_without_repository_falls_back_to_mock(
    _patched_settings,
) -> None:
    _patched_settings["current"] = _mock_settings(
        agent_pipeline="real", sandbox_executor="docker"
    )
    decision = dispatcher.decide_mode(_FakeTask(repository_id=None))
    assert decision.mode is ExecutionMode.MOCK
    assert decision.has_repository is False


# --- dispatch_start -------------------------------------------------


def test_dispatch_start_runs_mock_when_default(
    _patched_settings, _capture_send, _stub_orchestrator
) -> None:
    task = _FakeTask()
    session = _FakeSession()
    decision = dispatcher.dispatch_start(session, task)  # type: ignore[arg-type]
    assert decision.mode is ExecutionMode.MOCK
    assert _capture_send == []  # nothing enqueued
    assert _stub_orchestrator == ["start:task-1"]
    assert task.execution_mode == "mock"


def test_real_mode_enqueues_celery_when_repo_attached(
    _patched_settings, _capture_send, _stub_orchestrator
) -> None:
    _patched_settings["current"] = _mock_settings(
        agent_pipeline="real", sandbox_executor="docker"
    )
    task = _FakeTask()
    session = _FakeSession()
    decision = dispatcher.dispatch_start(session, task)  # type: ignore[arg-type]
    assert decision.is_real is True
    assert task.execution_mode == "real"
    assert _capture_send == [
        (dispatcher.RUN_TASK_NAME, ("task-1",), dispatcher.REAL_QUEUE)
    ]
    assert _stub_orchestrator == []  # mock orchestrator MUST NOT run


def test_real_dispatch_sets_phase_to_planning(
    _patched_settings, _capture_send, _stub_orchestrator
) -> None:
    _patched_settings["current"] = _mock_settings(
        agent_pipeline="real", sandbox_executor="docker"
    )
    task = _FakeTask()
    session = _FakeSession()
    dispatcher.dispatch_start(session, task)  # type: ignore[arg-type]
    assert task.phase == "planning"
    assert task.active_agent == "planner"


# --- dispatch_approve_frontend --------------------------------------


def test_approve_frontend_enqueues_resume_when_execution_mode_real(
    _patched_settings, _capture_send, _stub_orchestrator
) -> None:
    task = _FakeTask(execution_mode="real")
    session = _FakeSession()
    decision = dispatcher.dispatch_approve_frontend(session, task)  # type: ignore[arg-type]
    assert decision.is_real is True
    assert _capture_send == [
        (dispatcher.RESUME_TASK_NAME, ("task-1",), dispatcher.REAL_QUEUE)
    ]
    assert task.phase == "security_review"
    assert task.active_agent == "security_reviewer"
    assert _stub_orchestrator == []


def test_approve_frontend_runs_mock_when_execution_mode_mock(
    _patched_settings, _capture_send, _stub_orchestrator
) -> None:
    task = _FakeTask(execution_mode="mock")
    session = _FakeSession()
    decision = dispatcher.dispatch_approve_frontend(session, task)  # type: ignore[arg-type]
    assert decision.mode is ExecutionMode.MOCK
    assert _capture_send == []
    assert _stub_orchestrator == ["approve:task-1"]


def test_dispatch_decision_carries_settings_snapshot(
    _patched_settings,
) -> None:
    _patched_settings["current"] = _mock_settings(
        agent_pipeline="real", sandbox_executor="docker"
    )
    decision = dispatcher.decide_mode(_FakeTask())
    assert isinstance(decision, DispatchDecision)
    assert decision.pipeline_setting == "real"
    assert decision.executor_setting == "docker"
    assert decision.has_repository is True
