"""Preview schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PreviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    viewport: str
    width: int
    height: int
    image_url: str
    route: str
    notes: str
    created_at: datetime
