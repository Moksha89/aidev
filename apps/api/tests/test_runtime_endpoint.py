"""Tests for ``GET /settings/runtime``.

The dashboard polls this endpoint to render the runtime banner. The
endpoint requires authentication; we override the dependency directly
because the smoke-test fixtures already trust the database-less
testclient pattern.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.deps import get_current_user
from app.main import app
from app.models import User


@pytest.fixture
def _client() -> Iterator[TestClient]:
    """Bypass auth: every request runs as a stub admin user."""

    def _fake_user() -> User:
        u = User()
        u.id = "user-test"
        u.email = "ops@aidev.local"
        u.is_admin = True
        u.is_active = True
        u.full_name = "Test"
        return u

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        get_settings.cache_clear()


def test_runtime_default_is_mock(
    _client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "AIDEV_AGENT_PIPELINE",
        "AGENT_PIPELINE",
        "AIDEV_SANDBOX_EXECUTOR",
        "SANDBOX_EXECUTOR",
        "AIDEV_GITHUB_TOKEN",
        "AIDEV_GITHUB_APP_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    resp = _client.get("/settings/runtime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sandbox_executor"] == "mock"
    assert body["agent_pipeline"] == "mock"
    assert body["github_configured"] is False
    assert body["github_mode"] is None
    assert body["real_pipeline_active"] is False
    # Non-secret runtime info MUST be present so the dashboard can show it.
    assert "model_base_url" in body
    assert "model_name" in body
    assert body["env"] in {"development", "staging", "production"}


def test_runtime_reflects_real_pipeline_flags(
    _client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIDEV_AGENT_PIPELINE", "real")
    monkeypatch.setenv("SANDBOX_EXECUTOR", "docker")
    monkeypatch.setenv("AIDEV_GITHUB_TOKEN", "ghp_dummy_token_for_unit_test")
    get_settings.cache_clear()
    resp = _client.get("/settings/runtime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sandbox_executor"] == "docker"
    assert body["agent_pipeline"] == "real"
    assert body["github_configured"] is True
    assert body["github_mode"] == "token"
    assert body["real_pipeline_active"] is True


def test_runtime_does_not_leak_secrets(
    _client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "ghp_super_secret_token_must_not_appear_in_response"
    monkeypatch.setenv("AIDEV_GITHUB_TOKEN", secret)
    get_settings.cache_clear()
    resp = _client.get("/settings/runtime")
    assert resp.status_code == 200
    assert secret not in resp.text


def test_runtime_app_pipeline_without_executor_is_not_active(
    _client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIDEV_AGENT_PIPELINE", "real")
    monkeypatch.delenv("SANDBOX_EXECUTOR", raising=False)
    get_settings.cache_clear()
    resp = _client.get("/settings/runtime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["real_pipeline_active"] is False
