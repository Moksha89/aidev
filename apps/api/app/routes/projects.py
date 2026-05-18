"""Project routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> list[ProjectRead]:
    projects = (
        db.query(Project)
        .filter(Project.owner_id == current.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [ProjectRead.model_validate(p) for p in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ProjectRead:
    project = Project(
        name=body.name,
        slug=body.slug,
        description=body.description,
        owner_id=current.id,
        default_model_server_id=body.default_model_server_id,
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{body.slug}' is already taken",
        ) from exc
    db.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ProjectRead:
    project = db.get(Project, project_id)
    if not project or project.owner_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return ProjectRead.model_validate(project)
