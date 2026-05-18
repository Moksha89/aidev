"""Traefik dynamic preview registration / deregistration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sandbox_runner.preview import (
    PreviewRegistrar,
    PreviewRoute,
    render_dynamic_config,
)


def test_render_dynamic_config_includes_router_and_service() -> None:
    route = PreviewRoute(
        task_id="t1",
        domain="task-t1.preview.aidev.local",
        backend_url="http://aidev-sandbox-t1:3000",
    )
    yaml = render_dynamic_config(route)
    assert "aidev-preview-t1:" in yaml
    assert "Host(`task-t1.preview.aidev.local`)" in yaml
    assert "url: http://aidev-sandbox-t1:3000" in yaml
    # Security middlewares wired in by default.
    assert "aidev-security-headers@file" in yaml
    assert "aidev-rate-limit@file" in yaml


def test_registrar_writes_and_removes_dynamic_file(tmp_path: Path) -> None:
    registrar = PreviewRegistrar(dynamic_dir=str(tmp_path))
    route = PreviewRoute(
        task_id="abc",
        domain="task-abc.preview.aidev.local",
        backend_url="http://aidev-sandbox-abc:3000",
    )
    path = registrar.register(route)

    assert os.path.basename(path) == "task-abc.yml"
    assert os.path.exists(path)
    content = Path(path).read_text(encoding="utf-8")
    assert "aidev-preview-abc" in content

    removed = registrar.deregister("abc")
    assert removed is True
    assert not os.path.exists(path)


def test_deregister_returns_false_when_missing(tmp_path: Path) -> None:
    registrar = PreviewRegistrar(dynamic_dir=str(tmp_path))
    assert registrar.deregister("nonexistent") is False


def test_register_creates_dynamic_dir_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested"
    registrar = PreviewRegistrar(dynamic_dir=str(nested))
    registrar.register(
        PreviewRoute(
            task_id="x",
            domain="task-x.preview.aidev.local",
            backend_url="http://aidev-sandbox-x:3000",
        )
    )
    assert nested.exists()


def test_register_rejects_bad_task_id(tmp_path: Path) -> None:
    registrar = PreviewRegistrar(dynamic_dir=str(tmp_path))
    with pytest.raises(ValueError):
        registrar.register(
            PreviewRoute(
                task_id="../escape",
                domain="x",
                backend_url="http://x:3000",
            )
        )
