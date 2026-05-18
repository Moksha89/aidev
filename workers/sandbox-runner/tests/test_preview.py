"""Preview registrar tests — Traefik (domain) and port-based (IP-only)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sandbox_runner.preview import (
    PortPoolExhaustedError,
    PortPreviewRegistrar,
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


# ---- PortPreviewRegistrar (IP-only acceptance) -----------------------------


def test_port_registrar_allocates_first_free_port() -> None:
    registrar = PortPreviewRegistrar(
        public_host="203.0.113.10",
        port_range_start=31000,
        port_range_end=31002,
    )
    alloc = registrar.allocate(task_id="t1", internal_port=3000)
    assert alloc.host_port == 31000
    assert alloc.internal_port == 3000
    assert alloc.public_host == "203.0.113.10"
    assert alloc.public_url == "http://203.0.113.10:31000"
    assert alloc.port_bindings == {"3000/tcp": 31000}


def test_port_registrar_walks_the_range_and_skips_held_ports() -> None:
    registrar = PortPreviewRegistrar(
        public_host="ip",
        port_range_start=31000,
        port_range_end=31010,
    )
    a = registrar.allocate(task_id="t1", internal_port=3000)
    b = registrar.allocate(task_id="t2", internal_port=3000)
    c = registrar.allocate(task_id="t3", internal_port=3000)
    assert (a.host_port, b.host_port, c.host_port) == (31000, 31001, 31002)

    registrar.release("t2")
    d = registrar.allocate(task_id="t4", internal_port=3000)
    # 31001 is now the lowest-free slot, so it should be reused.
    assert d.host_port == 31001


def test_port_registrar_is_idempotent_for_same_task() -> None:
    registrar = PortPreviewRegistrar(
        public_host="ip", port_range_start=31000, port_range_end=31010
    )
    a = registrar.allocate(task_id="t1", internal_port=3000)
    b = registrar.allocate(task_id="t1", internal_port=3000)
    assert a.host_port == b.host_port


def test_port_registrar_raises_when_pool_exhausted() -> None:
    registrar = PortPreviewRegistrar(
        public_host="ip", port_range_start=31000, port_range_end=31001
    )
    registrar.allocate(task_id="t1", internal_port=3000)
    registrar.allocate(task_id="t2", internal_port=3000)
    with pytest.raises(PortPoolExhaustedError):
        registrar.allocate(task_id="t3", internal_port=3000)


def test_port_registrar_release_returns_false_when_missing() -> None:
    registrar = PortPreviewRegistrar(
        public_host="ip", port_range_start=31000, port_range_end=31010
    )
    assert registrar.release("never-allocated") is False


def test_port_registrar_validates_task_id() -> None:
    registrar = PortPreviewRegistrar(
        public_host="ip", port_range_start=31000, port_range_end=31010
    )
    with pytest.raises(ValueError):
        registrar.allocate(task_id="../escape", internal_port=3000)


def test_port_registrar_validates_range() -> None:
    with pytest.raises(ValueError):
        PortPreviewRegistrar(
            public_host="ip", port_range_start=31100, port_range_end=31000
        )
    with pytest.raises(ValueError):
        PortPreviewRegistrar(
            public_host="ip", port_range_start=0, port_range_end=31000
        )
