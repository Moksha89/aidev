"""Approval schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalCreate(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=2000)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    actor_user_id: str | None
    decision: str
    reason: str
    actor_ip: str | None
    created_at: datetime
