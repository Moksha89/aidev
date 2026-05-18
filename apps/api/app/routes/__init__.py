"""HTTP route registration."""

from fastapi import APIRouter

from app.routes import auth, projects, repositories, settings, tasks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(repositories.router)
api_router.include_router(tasks.router)
api_router.include_router(settings.router)

__all__ = ["api_router"]
