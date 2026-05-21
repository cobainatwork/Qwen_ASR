from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class QualityEvalIssue(BaseModel):
    code: str
    message: str | None = None


class QualityEvalData(BaseModel):
    score: float
    issues: list[QualityEvalIssue]


class CorrectionSessionData(BaseModel):
    id: int
    transcription_id: int
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class CorrectionSegmentData(BaseModel):
    id: int
    session_id: int
    segment_index: int
    start_sec: float
    end_sec: float
    original_text: str
    corrected_text: str | None
    speaker_label: str | None
    is_skipped: bool
    version: int
    updated_at: datetime


class CorrectionSegmentUpdate(BaseModel):
    corrected_text: str | None = Field(None, min_length=0, max_length=5000)
    is_skipped: bool | None = None  # None 表示不變更
    expected_version: int

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "CorrectionSegmentUpdate":
        if self.corrected_text is None and self.is_skipped is None:
            raise ValueError(
                "至少需提供 corrected_text 或 is_skipped 其一"
            )
        return self


class ExportToDatasetRequest(BaseModel):
    dataset_id: int


class ExportToDatasetData(BaseModel):
    inserted_count: int
    dataset_id: int
