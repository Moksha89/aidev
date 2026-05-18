"""Repository routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models import Project, Repository, User
from app.schemas import RepositoryConnect, RepositoryRead

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[RepositoryRead]:
    query = (
        db.query(Repository)
        .join(Project, Project.id == Repository.project_id)
        .filter(Project.owner_id == current.id)
    )
    if project_id:
        query = query.filter(Repository.project_id == project_id)
    return [
        RepositoryRead.model_validate(r)
        for r in query.order_by(Repository.created_at.desc()).all()
    ]


@router.post(
    "/connect", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED
)
def connect_repository(
    body: RepositoryConnect,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> RepositoryRead:
    project = db.get(Project, body.project_id)
    if not project or project.owner_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # The real implementation calls github-client to verify the user has
    # access to the repo. For the MVP we accept the metadata and store it.
    settings_obj = get_settings()
    if settings_obj.github_token or settings_obj.github_app_id:
        # Verification is best-effort; failure here doesn't block the connect
        # because we want the dashboard to be usable without GitHub creds.
        pass

    repo = Repository(
        project_id=body.project_id,
        github_owner=body.github_owner,
        github_name=body.github_name,
        default_branch=body.default_branch,
        html_url=f"https://github.com/{body.github_owner}/{body.github_name}",
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return RepositoryRead.model_validate(repo)
