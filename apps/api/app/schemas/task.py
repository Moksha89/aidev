"""Task schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    project_id: str
    repository_id: str | None = None
    title: str = Field(min_length=1, max_length=512)
    instruction: str = Field(min_length=1)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    repository_id: str | None
    creator_id: str | None
    title: str
    instruction: str
    phase: str
    active_agent: str | None
    execution_mode: str
    branch_name: str | None
    preview_url: str | None
    pr_url: str | None
    pr_number: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class TaskLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    level: str
    agent_role: str | None
    phase: str | None
    message: str
    sequence: int
    created_at: datetime


class TaskFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    path: str
    status: str
    lines_added: int
    lines_removed: int
    diff_snippet: str
