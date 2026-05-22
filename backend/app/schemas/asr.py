from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginationMeta


class TranscribeOptions(BaseModel):
    model: str | None = None
    language: str | None = None
    return_timestamps: bool = True

    # Phase 1 接收但忽略（會出現在回應 warnings 內）
    diarization: bool | None = None
    post_processing: bool | None = None
    denoise_enabled: bool | None = None
    nec_enabled: bool | None = None
    punctuation_enabled: bool | None = None
    hotword_group_ids: list[int] | None = None
    vad_enabled: bool = True


class Timestamp(BaseModel):
    text: str
    start: float
    end: float


class SpeakerTurn(BaseModel):
    speaker: str
    start: float
    end: float


class DiarizationInfo(BaseModel):
    status: str
    backend: str | None = None
    speakers_count: int | None = None


class TranscribeData(BaseModel):
    transcription_id: int
    audio_file_id: int
    text: str
    timestamps: list[Timestamp] | None = None
    speakers: list[SpeakerTurn] | None = None
    diarization: DiarizationInfo | None = None
    language: str | None = None
    duration_sec: float
    processing_duration_sec: float
    model_version: str
    resampling_warning: bool
    vad_segments_count: int
    warnings: list[str] = Field(default_factory=list)


class TranscriptionListItem(BaseModel):
    """列表 API 回應項目 — 排除 JSONB/TEXT 大欄位（CLAUDE.md 強制規範 #4）。"""

    id: int
    file_name: str | None
    source: str
    status: str
    duration_sec: float | None
    language: str | None
    model_version: str
    created_at: datetime
    updated_at: datetime


class TranscriptionListData(BaseModel):
    items: list[TranscriptionListItem]
    pagination: PaginationMeta


# diarization 由 settings.DIARIZATION_ENABLED 控制（M7 起支援），不再列入「Phase 1 不支援」。
_UNSUPPORTED_FIELDS = (
    "post_processing",
    "denoise_enabled",
    "nec_enabled",
    "punctuation_enabled",
    "hotword_group_ids",
)


def collect_unsupported_warnings(options: TranscribeOptions) -> list[str]:
    warnings: list[str] = []
    for field in _UNSUPPORTED_FIELDS:
        value = getattr(options, field, None)
        if value not in (None, False, []):
            warnings.append(f"Phase 1 不支援 {field}，已忽略（將在後續 Phase 啟用）")
    if options.model and options.model != "":
        warnings.append("Phase 1 model 參數已忽略，使用啟動載入的 ASR_MODEL")
    return warnings
