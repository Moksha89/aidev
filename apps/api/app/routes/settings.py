"""Settings routes — model servers, GitHub config, rule overrides."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models import ModelServer, Project, RuleSet, User
from app.schemas import (
    ModelServerCreate,
    ModelServerRead,
    RuleSetRead,
    RuleSetUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# --------------------------------------------------------------- models


@router.get("/models", response_model=list[ModelServerRead])
def list_models(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[ModelServerRead]:
    del current  # auth only; model servers are platform-wide
    return [
        ModelServerRead.model_validate(m)
        for m in db.query(ModelServer).order_by(ModelServer.created_at.desc()).all()
    ]


@router.post("/models", response_model=ModelServerRead, status_code=status.HTTP_201_CREATED)
def create_model(
    body: ModelServerCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ModelServerRead:
    if not current.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    if body.is_default:
        # Demote any existing default.
        for m in db.query(ModelServer).filter(ModelServer.is_default.is_(True)).all():
            m.is_default = False
    server = ModelServer(
        name=body.name,
        base_url=body.base_url,
        model_identifier=body.model_identifier,
        server_type=body.server_type,
        is_default=body.is_default,
        # API key encryption happens on disk in production; for the MVP we
        # store nothing rather than store plaintext.
        api_key_encrypted=None,
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return ModelServerRead.model_validate(server)


# ---------------------------------------------------------------- rules


@router.get("/rules", response_model=list[RuleSetRead])
def list_rule_overrides(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[RuleSetRead]:
    query = (
        db.query(RuleSet)
        .join(Project, Project.id == RuleSet.project_id)
        .filter(Project.owner_id == current.id)
    )
    if project_id:
        query = query.filter(RuleSet.project_id == project_id)
    return [
        RuleSetRead.model_validate(r)
        for r in query.order_by(RuleSet.created_at.desc()).all()
    ]


@router.post(
    "/rules", response_model=RuleSetRead, status_code=status.HTTP_201_CREATED
)
def create_rule_override(
    project_id: str,
    body: RuleSetUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> RuleSetRead:
    project = db.get(Project, project_id)
    if not project or project.owner_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    rule_set = RuleSet(
        project_id=project_id,
        name=body.name,
        extra_forbidden_globs=body.extra_forbidden_globs,
        extra_allowed_globs=body.extra_allowed_globs,
        is_enabled=body.is_enabled,
    )
    db.add(rule_set)
    db.commit()
    db.refresh(rule_set)
    return RuleSetRead.model_validate(rule_set)


# --------------------------------------------------------------- github


@router.get("/github")
def get_github_status(
    current: User = Depends(get_current_user),
) -> dict[str, object]:
    """Tell the dashboard whether GitHub auth is configured.

    Never returns the token; only a boolean and the mode in use.
    """
    del current
    s = get_settings()
    if s.github_token:
        return {"configured": True, "mode": "token"}
    if s.github_app_id and s.github_app_private_key_path:
        return {
            "configured": True,
            "mode": "app",
            "app_id": s.github_app_id,
            "installation_id": s.github_app_installation_id,
        }
    return {"configured": False, "mode": None}


# --------------------------------------------------------------- servers


@router.get("/servers")
def list_servers(current: User = Depends(get_current_user)) -> dict[str, object]:
    """Summary of the configured runtime (model + queue + sandbox)."""
    del current
    s = get_settings()
    return {
        "model_base_url": s.model_base_url,
        "model_name": s.model_name,
        "redis_url": _redact(s.redis_url),
        "sandbox_executor": s.sandbox_executor,
        "env": s.aidev_env,
    }


def _redact(url: str) -> str:
    """Hide creds in a URL like `redis://:password@host:port/0`."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    creds, _, host = rest.partition("@")
    if ":" in creds:
        user, _, _ = creds.partition(":")
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://***@{host}"
