from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AudioFileTooLargeError, ValidationFailedError
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey
from app.repositories.audio_file import AudioFileRepository
from app.schemas.asr import (
    Timestamp,
    TranscribeData,
    TranscribeOptions,
    collect_unsupported_warnings,
)
from app.schemas.common import ResponseEnvelope
from app.services.asr.consumer import wait_for_job
from app.services.asr.queue import AsrJob, QueueBackend, QueuePriority
from app.services.audio import (
    FireRedVADService,
    Segment,
    resample_to_16k_mono,
    store_upload,
    verify_mime,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])


def get_queue(request: Request) -> QueueBackend:
    """從 app.state 取得當前 QueueBackend 實例。"""
    queue: QueueBackend | None = getattr(request.app.state, "asr_queue", None)
    if queue is None:
        raise RuntimeError("asr_queue 未在 app.state 設定（lifespan 未啟動？）")
    return queue


@router.post("/transcribe", response_model=ResponseEnvelope[TranscribeData])
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    options_json: str = Form("{}"),
    api_key: ApiKey = Depends(require_scope("asr:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[TranscribeData]:
    queue = get_queue(request)

    # 解析 options
    try:
        options = TranscribeOptions.model_validate_json(options_json)
    except Exception as e:
        raise ValidationFailedError(details={"options_json": str(e)}) from e

    warnings = collect_unsupported_warnings(options)

    # 讀取 bytes
    raw_bytes = await file.read()
    if len(raw_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise AudioFileTooLargeError(
            details={"limit_mb": settings.MAX_UPLOAD_SIZE_MB, "actual_bytes": len(raw_bytes)}
        )

    # 預處理
    mime, ext = verify_mime(raw_bytes, settings.supported_formats_list)
    audio = store_upload(
        db=db,
        api_key_id=api_key.id,
        raw_bytes=raw_bytes,
        original_name=file.filename or f"upload.{ext}",
        canonical_ext=ext,
        verified_mime=mime,
        storage_dir=settings.AUDIO_STORAGE_DIR,
    )
    db.commit()

    resample = await resample_to_16k_mono(
        Path(audio.storage_path),
        settings.AUDIO_STORAGE_DIR / "processed",
    )
    AudioFileRepository(db, api_key.id).update_after_resample(
        audio.id,
        original_sample_rate=resample.original_sample_rate,
        duration_sec=resample.duration_sec,
    )
    db.commit()

    # VAD_ENABLED=false 時跳過 VAD（套件未安裝或環境關閉），整段直送 ASR
    vad_segments: list[Segment] = []
    if settings.VAD_ENABLED:
        vad_segments = await FireRedVADService.detect_speech(resample.output_path)

    # 入佇列等待
    job = AsrJob(
        audio_file_id=audio.id,
        api_key_id=api_key.id,
        options=options.model_dump(),
        future=asyncio.get_event_loop().create_future(),
    )
    await queue.enqueue(job, QueuePriority.BATCH)
    transcription_id = await wait_for_job(job, timeout=settings.ASR_REQUEST_TIMEOUT_SEC)

    # 讀取結果
    from app.repositories.transcription import TranscriptionRepository

    rec = TranscriptionRepository(db, api_key.id).get(transcription_id)
    if rec is None:
        raise ValidationFailedError(message="transcription_id 不存在")

    timestamps = (
        [Timestamp(**t) for t in rec.timestamps] if rec.timestamps else None
    )
    return success(
        TranscribeData(
            transcription_id=rec.id,
            audio_file_id=audio.id,
            text=rec.transcript_text or "",
            timestamps=timestamps,
            language=rec.language,
            duration_sec=rec.duration_sec or 0.0,
            processing_duration_sec=rec.processing_duration_sec or 0.0,
            model_version=rec.model_version,
            resampling_warning=resample.resampling_warning,
            vad_segments_count=len(vad_segments),
            warnings=warnings,
        )
    )
