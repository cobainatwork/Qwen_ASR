from datetime import datetime

from pydantic import BaseModel, Field


class HotwordGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class HotwordGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class HotwordGroupData(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    word_count: int
    created_at: datetime
    updated_at: datetime


class HotwordItem(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    weight: float = 1.0
    pinyin: str | None = None


class HotwordBulkUploadRequest(BaseModel):
    words: list[HotwordItem] = Field(..., min_length=1, max_length=2000)


class HotwordBulkUploadData(BaseModel):
    group_id: int
    inserted_count: int
    new_word_count: int
    strategy: str
