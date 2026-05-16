from datetime import datetime

from pydantic import BaseModel, Field


class YoutubeDownloadRequest(BaseModel):
    url: str = Field(..., min_length=10)


class YoutubeDownloadData(BaseModel):
    id: int
    url: str
    video_title: str | None
    audio_file_id: int | None
    status: str
    error_message: str | None
    file_size: int | None
    duration_sec: float | None
    created_at: datetime
    updated_at: datetime
