"""Task routes — the most important surface of the API."""

from __future__ import annotations

import hashlib
import io

from aidev_shared import TaskPhase
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core import orchestrator
from app.core.deps import get_current_user, get_db
from app.models import (
    Project,
    Task,
    TaskApproval,
    TaskFile,
    TaskLog,
    TaskMessage,
    TaskPreview,
    User,
)
from app.schemas import (
    ApprovalCreate,
    ApprovalRead,
    MessageCreate,
    MessageRead,
    PreviewRead,
    TaskCreate,
    TaskFileRead,
    TaskLogRead,
    TaskRead,
)
from app.services import dispatcher

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _load_task(db: Session, task_id: str, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    project = db.get(Project, task.project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[TaskRead]:
    query = (
        db.query(Task)
        .join(Project, Project.id == Task.project_id)
        .filter(Project.owner_id == current.id)
    )
    if project_id:
        query = query.filter(Task.project_id == project_id)
    return [
        TaskRead.model_validate(t)
        for t in query.order_by(Task.created_at.desc()).all()
    ]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TaskRead:
    project = db.get(Project, body.project_id)
    if not project or project.owner_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    task = Task(
        project_id=body.project_id,
        repository_id=body.repository_id,
        creator_id=current.id,
        title=body.title,
        instruction=body.instruction,
        phase=TaskPhase.PENDING.value,
    )
    db.add(task)
    db.flush()
    # Persist the user's instruction as the first chat message.
    db.add(
        TaskMessage(
            task_id=task.id,
            role="user",
            content=body.instruction,
        )
    )
    db.commit()
    db.refresh(task)
    return TaskRead.model_validate(task)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TaskRead:
    return TaskRead.model_validate(_load_task(db, task_id, current))


@router.post("/{task_id}/start", response_model=TaskRead)
def start_task(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TaskRead:
    task = _load_task(db, task_id, current)
    if task.phase != TaskPhase.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is in phase '{task.phase}', not 'pending'",
        )
    dispatcher.dispatch_start(db, task)
    db.commit()
    db.refresh(task)
    return TaskRead.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: str,
    reason: str = "",
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TaskRead:
    task = _load_task(db, task_id, current)
    orchestrator.cancel_task(db, task, reason=reason)
    db.commit()
    db.refresh(task)
    return TaskRead.model_validate(task)


@router.post("/{task_id}/approve-frontend", response_model=ApprovalRead)
def approve_frontend(
    task_id: str,
    body: ApprovalCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ApprovalRead:
    if body.decision != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /tasks/:id/reject for rejection",
        )
    task = _load_task(db, task_id, current)
    if task.phase != TaskPhase.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is in phase '{task.phase}', not 'awaiting_approval'",
        )
    approval = TaskApproval(
        task_id=task.id,
        actor_user_id=current.id,
        decision="approved",
        reason=body.reason,
        actor_ip=request.client.host if request.client else None,
        actor_user_agent=request.headers.get("user-agent"),
    )
    db.add(approval)
    dispatcher.dispatch_approve_frontend(db, task)
    db.commit()
    db.refresh(approval)
    return ApprovalRead.model_validate(approval)


@router.post("/{task_id}/reject", response_model=ApprovalRead)
def reject_frontend(
    task_id: str,
    body: ApprovalCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ApprovalRead:
    task = _load_task(db, task_id, current)
    if task.phase != TaskPhase.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is in phase '{task.phase}', not 'awaiting_approval'",
        )
    approval = TaskApproval(
        task_id=task.id,
        actor_user_id=current.id,
        decision="rejected",
        reason=body.reason,
        actor_ip=request.client.host if request.client else None,
        actor_user_agent=request.headers.get("user-agent"),
    )
    db.add(approval)
    orchestrator.reject_frontend(db, task, reason=body.reason)
    db.commit()
    db.refresh(approval)
    return ApprovalRead.model_validate(approval)


# ----- chat -----


@router.post(
    "/{task_id}/message",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    task_id: str,
    body: MessageCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> MessageRead:
    task = _load_task(db, task_id, current)
    message = TaskMessage(task_id=task.id, role=body.role, content=body.content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return MessageRead.model_validate(message)


@router.get("/{task_id}/messages", response_model=list[MessageRead])
def list_messages(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[MessageRead]:
    task = _load_task(db, task_id, current)
    messages = (
        db.query(TaskMessage)
        .filter(TaskMessage.task_id == task.id)
        .order_by(TaskMessage.created_at.asc())
        .all()
    )
    return [MessageRead.model_validate(m) for m in messages]


# ----- logs / files / diff / preview / screenshots -----


@router.get("/{task_id}/logs", response_model=list[TaskLogRead])
def list_logs(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[TaskLogRead]:
    task = _load_task(db, task_id, current)
    logs = (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task.id)
        .order_by(TaskLog.sequence.asc())
        .all()
    )
    return [TaskLogRead.model_validate(log) for log in logs]


@router.get("/{task_id}/files", response_model=list[TaskFileRead])
def list_files(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[TaskFileRead]:
    task = _load_task(db, task_id, current)
    files = (
        db.query(TaskFile)
        .filter(TaskFile.task_id == task.id)
        .order_by(TaskFile.path.asc())
        .all()
    )
    return [TaskFileRead.model_validate(f) for f in files]


@router.get("/{task_id}/diff")
def get_diff(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict[str, object]:
    """Return a synthetic unified diff stitched from `task_files`.

    In production the worker stores the real `git diff` output as a blob;
    here we render the snippets we collected.
    """
    task = _load_task(db, task_id, current)
    files = (
        db.query(TaskFile)
        .filter(TaskFile.task_id == task.id)
        .order_by(TaskFile.path.asc())
        .all()
    )
    if not files:
        return {"task_id": task.id, "diff": ""}
    chunks: list[str] = []
    for f in files:
        chunks.append(
            f"diff --git a/{f.path} b/{f.path}\n"
            f"--- a/{f.path}\n"
            f"+++ b/{f.path}\n"
            f"{f.diff_snippet}"
        )
    return {"task_id": task.id, "diff": "\n".join(chunks)}


@router.get("/{task_id}/preview")
def get_preview(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict[str, str | None]:
    task = _load_task(db, task_id, current)
    return {
        "task_id": task.id,
        "preview_url": task.preview_url,
        "phase": task.phase,
    }


@router.get("/{task_id}/screenshots", response_model=list[PreviewRead])
def list_screenshots(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[PreviewRead]:
    task = _load_task(db, task_id, current)
    previews = (
        db.query(TaskPreview)
        .filter(TaskPreview.task_id == task.id)
        .order_by(TaskPreview.width.asc())
        .all()
    )
    return [PreviewRead.model_validate(p) for p in previews]


@router.get("/{task_id}/screenshots/{viewport}.png")
def get_screenshot_image(
    task_id: str,
    viewport: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> StreamingResponse:
    """Return a deterministic 1x1 PNG placeholder.

    The real Playwright screenshots are stored under `/var/lib/aidev/screenshots/`
    by the QA agent. The dashboard hits this endpoint and the worker
    eventually overwrites the placeholder with the real PNG. Until then,
    we return a small image keyed on the viewport so the dashboard can
    distinguish them without 404ing.
    """
    task = _load_task(db, task_id, current)
    seed = hashlib.sha256(f"{task.id}:{viewport}".encode()).digest()[:3]
    # 1x1 PNG with the seeded RGB triple as the pixel.
    png = _one_by_one_png(seed[0], seed[1], seed[2])
    return StreamingResponse(io.BytesIO(png), media_type="image/png")


@router.post("/{task_id}/create-pr", response_model=TaskRead)
def create_pr(
    task_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TaskRead:
    """Manually trigger PR creation if it didn't happen automatically.

    In the MVP this is a no-op when the task already has a `pr_url`.
    """
    task = _load_task(db, task_id, current)
    if task.pr_url:
        return TaskRead.model_validate(task)
    if task.phase not in {TaskPhase.PR_OPENED.value, TaskPhase.DONE.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot open PR while task is in phase '{task.phase}'",
        )
    return TaskRead.model_validate(task)


# ----- helpers -----


def _one_by_one_png(r: int, g: int, b: int) -> bytes:
    """Return a deterministic 1x1 PNG with the given RGB pixel."""
    import struct
    import zlib

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
