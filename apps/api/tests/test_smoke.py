"""Smoke tests covering the FastAPI bootstrap.

These don't depend on Postgres / Redis — they exercise the app
factory and the meta routes only, so CI can run them without
provisioning services.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "env" in body


def test_root_returns_service_metadata() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "aidev-api"
    assert body["version"] == "0.1.0"


def test_openapi_schema_is_served() -> None:
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "AI Developer API"
