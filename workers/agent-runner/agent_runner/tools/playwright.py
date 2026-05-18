"""Playwright tool — captures screenshots at standard viewports.

v0.1 stub: writes a 1×1 PNG keyed on viewport. v0.2 actually drives
Playwright inside the sandbox and uploads the resulting PNGs to the
backend.
"""

from __future__ import annotations

import hashlib
import os
import struct
import zlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int


VIEWPORTS: tuple[Viewport, ...] = (
    Viewport("mobile-375", 375, 812),
    Viewport("mobile-430", 430, 932),
    Viewport("tablet-768", 768, 1024),
    Viewport("desktop-1280", 1280, 800),
    Viewport("desktop-1920", 1920, 1080),
)


def capture_screenshot(
    *,
    workspace: str,
    task_id: str,
    viewport: Viewport,
    route: str = "/",
) -> str:
    """Write a placeholder PNG to `<workspace>/.aidev/screenshots/<viewport>.png`.

    Returns the absolute path. v0.2 will replace the contents with the
    real Playwright capture.
    """
    out_dir = os.path.join(workspace, ".aidev", "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{viewport.name}.png")
    seed = hashlib.sha256(f"{task_id}:{viewport.name}:{route}".encode()).digest()[:3]
    with open(out_path, "wb") as f:
        f.write(_one_by_one_png(seed[0], seed[1], seed[2]))
    return out_path


def _one_by_one_png(r: int, g: int, b: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = bytes([0, r, g, b])
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


__all__ = ["VIEWPORTS", "Viewport", "capture_screenshot"]
