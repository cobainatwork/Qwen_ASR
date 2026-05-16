from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    metadata: dict[str, Any] | None = None


class DatasetData(BaseModel):
    id: int
    name: str
    description: str | None
    sample_count: int
    total_duration_sec: float
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DatasetSampleData(BaseModel):
    id: int
    dataset_id: int
    audio_file_id: int
    transcript: str
    duration_sec: float
    file_size: int
    created_at: datetime
