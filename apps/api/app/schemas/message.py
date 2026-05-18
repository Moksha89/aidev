"""Task message (chat) schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    role: Literal["user", "assistant", "system"] = "user"


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    role: str
    agent_role: str | None
    content: str
    created_at: datetime
