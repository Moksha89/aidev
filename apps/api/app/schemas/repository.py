"""Repository schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryConnect(BaseModel):
    project_id: str
    github_owner: str = Field(min_length=1, max_length=128)
    github_name: str = Field(min_length=1, max_length=128)
    default_branch: str = "main"


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    github_owner: str
    github_name: str
    default_branch: str
    html_url: str
    created_at: datetime
    updated_at: datetime
