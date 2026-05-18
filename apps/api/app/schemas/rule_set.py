"""Rule set schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RuleSetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    extra_forbidden_globs: str = ""
    extra_allowed_globs: str = ""
    is_enabled: bool = True


class RuleSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    extra_forbidden_globs: str
    extra_allowed_globs: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
