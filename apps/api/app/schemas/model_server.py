"""Model server schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    model_identifier: str = Field(min_length=1, max_length=256)
    api_key: str | None = None
    server_type: Literal["ollama", "vllm", "openai", "llamacpp", "lmstudio"] = "openai"
    is_default: bool = False


class ModelServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    model_identifier: str
    server_type: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
