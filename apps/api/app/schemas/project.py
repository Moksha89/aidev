"""Project schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    slug: str = Field(min_length=1, max_length=256, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str = ""
    default_model_server_id: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str
    owner_id: str
    default_model_server_id: str | None
    created_at: datetime
    updated_at: datetime
