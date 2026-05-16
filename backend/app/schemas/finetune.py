from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FinetuneTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    dataset_id: int
    base_model: str = "Qwen/Qwen3-ASR-1.7B"
    config: dict[str, Any] | None = None


class FinetuneTaskData(BaseModel):
    id: int
    name: str
    dataset_id: int
    base_model: str
    status: str
    config: dict[str, Any] | None
    loss_history: list[dict[str, Any]] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FinetuneCheckpointData(BaseModel):
    id: int
    task_id: int
    epoch: int
    step: int
    loss: float
    wer: float | None
    checkpoint_path: str
    file_size: int
    is_active: bool
    created_at: datetime


class FinetuneUploadData(BaseModel):
    file_id: str
    size_bytes: int
