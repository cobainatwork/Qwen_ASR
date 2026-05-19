from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AudioFileTooLargeError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.idempotency import get_idempotency_cache, idempotent
from app.core.response import success
from app.deps.auth import require_scope
from app.deps.db import get_db
from app.models import ApiKey, AudioFile
from app.repositories.audio_file import AudioFileRepository
from app.schemas.asr import (
    DiarizationInfo,
    SpeakerTurn,
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
    ensure_safe_audio_path,
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
    _idem: None = Depends(idempotent),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[TranscribeData]:
    queue = get_queue(request)

    # Idempotency-Key cache hit: return cached response without re-running pipeline.
    cached = getattr(request.state, "idempotency_cached", None)
    if cached is not None:
        return success(TranscribeData(**cached))

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

    result = await _run_asr_pipeline(
        audio=audio,
        options=options,
        warnings=warnings,
        db=db,
        queue=queue,
        settings=settings,
        api_key=api_key,
    )
    idem_key = getattr(request.state, "idempotency_key", None)
    if idem_key is not None:
        get_idempotency_cache().record(idem_key, result.model_dump(mode="json"))
    return success(result)


async def _run_asr_pipeline(
    *,
    audio: AudioFile,
    options: TranscribeOptions,
    warnings: list[str],
    db: Session,
    queue: QueueBackend,
    settings: Settings,
    api_key: ApiKey,
) -> TranscribeData:
    """共用 ASR pipeline：resample → VAD → enqueue → wait_for_job → 投影 TranscribeData。

    被 /transcribe（剛 store 的 audio）與 /transcribe-stored/{id}（既存 audio）共用。
    """
    log = logger.bind(
        api_key_id=api_key.id,
        audio_file_id=audio.id,
    )
    log.info("asr pipeline start")

    # 防同一 audio_file_id 並發 transcribe（雙 tab / retry storm）
    repo = AudioFileRepository(db, api_key.id)
    locked = repo.lock_for_processing(audio.id)
    if locked is None:
        raise NotFoundError(message="音檔不存在或無權限存取")
    audio = locked

    safe_path = ensure_safe_audio_path(
        audio.storage_path, base_dir=settings.AUDIO_STORAGE_DIR
    )
    resample = await resample_to_16k_mono(
        safe_path,
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
        future=asyncio.get_running_loop().create_future(),
    )
    await queue.enqueue(job, QueuePriority.BATCH)
    transcription_id = await wait_for_job(job, timeout=settings.ASR_REQUEST_TIMEOUT_SEC)

    # 讀取結果（deferred import：避開 transcription → service → repository 循環）
    from app.repositories.transcription import TranscriptionRepository

    rec = TranscriptionRepository(db, api_key.id).get(transcription_id)
    if rec is None:
        raise ValidationFailedError(message="transcription_id 不存在")

    timestamps = (
        [Timestamp(**t) for t in rec.timestamps] if rec.timestamps else None
    )
    speakers = (
        [SpeakerTurn(**s) for s in rec.speakers] if rec.speakers else None
    )
    diarization_meta = (rec.post_processing or {}).get("diarization")
    diarization_info = (
        DiarizationInfo(
            status=diarization_meta.get("status", "unknown"),
            backend=diarization_meta.get("backend"),
            # JSONB key 為 "speakers"（int），對應 schema 的 speakers_count
            speakers_count=diarization_meta.get("speakers"),
        )
        if isinstance(diarization_meta, dict)
        else None
    )
    log.info(
        "asr pipeline complete",
        transcription_id=rec.id,
        duration_sec=rec.duration_sec or 0.0,
        processing_duration_sec=rec.processing_duration_sec or 0.0,
        model_version=rec.model_version,
    )
    return TranscribeData(
        transcription_id=rec.id,
        audio_file_id=audio.id,
        text=rec.transcript_text or "",
        timestamps=timestamps,
        speakers=speakers,
        diarization=diarization_info,
        language=rec.language,
        duration_sec=rec.duration_sec or 0.0,
        processing_duration_sec=rec.processing_duration_sec or 0.0,
        model_version=rec.model_version,
        resampling_warning=resample.resampling_warning,
        vad_segments_count=len(vad_segments),
        warnings=warnings,
    )


@router.post(
    "/transcribe-stored/{audio_file_id}",
    response_model=ResponseEnvelope[TranscribeData],
)
async def transcribe_stored(
    audio_file_id: int,
    request: Request,
    options_json: str = Form("{}"),
    api_key: ApiKey = Depends(require_scope("asr:write")),
    _idem: None = Depends(idempotent),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResponseEnvelope[TranscribeData]:
    """對已存在的 audio_file 重跑 ASR pipeline（不需 re-upload）。

    使用情境：YouTube 下載完成、或歷史音檔重新辨識。Tenant 隔離由
    AudioFileRepository.get 自動處理（不屬於當前 api_key 的 audio_file_id
    會回 None → 404）。
    """
    queue = get_queue(request)

    # Idempotency-Key cache hit: return cached response without re-running pipeline.
    cached = getattr(request.state, "idempotency_cached", None)
    if cached is not None:
        return success(TranscribeData(**cached))

    try:
        options = TranscribeOptions.model_validate_json(options_json)
    except Exception as e:
        raise ValidationFailedError(details={"options_json": str(e)}) from e

    warnings = collect_unsupported_warnings(options)

    audio = AudioFileRepository(db, api_key.id).get(audio_file_id)
    if audio is None:
        raise NotFoundError(message="音檔不存在或無權限存取")

    result = await _run_asr_pipeline(
        audio=audio,
        options=options,
        warnings=warnings,
        db=db,
        queue=queue,
        settings=settings,
        api_key=api_key,
    )
    idem_key = getattr(request.state, "idempotency_key", None)
    if idem_key is not None:
        get_idempotency_cache().record(idem_key, result.model_dump(mode="json"))
    return success(result)
