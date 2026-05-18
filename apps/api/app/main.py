"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import api_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    del app  # not used; placeholder for future startup hooks
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Developer API",
        description="Backend for the self-hosted AI Developer platform.",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "env": settings.aidev_env}

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {
            "service": "aidev-api",
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


app = create_app()
