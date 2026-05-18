from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AsrAudioTooLongError,
    AsrCudaError,
    AsrInferenceFailedError,
    NotFoundError,
)
from app.repositories.audio_file import AudioFileRepository
from app.repositories.transcription import TranscriptionRepository
from app.services.asr.engine import AsrEngineManager
from app.services.asr.queue import AsrJob

logger = structlog.get_logger(__name__)


@dataclass
class TranscribeOutcome:
    transcription_id: int
    text: str
    timestamps: list[dict[str, Any]] | None
    duration_sec: float
    processing_duration_sec: float
    model_version: str
    language: str | None


def _parse_timestamps(
    time_stamps: list[Any] | None,
) -> list[dict[str, Any]] | None:
    """將 qwen-asr TimeStamp 物件列表轉換為統一 dict 格式。

    TimeStamp 欄位：text（str）、start_time（float）、end_time（float）。
    回傳 None 表示本次推理無時間戳（return_time_stamps=False 或 ForcedAligner
    未載入；qwen-asr streaming 模式也回 None）。
    """
    if time_stamps is None:
        return None
    return [
        {"text": ts.text, "start": ts.start_time, "end": ts.end_time}
        for ts in time_stamps
    ]


def _load_wav_as_numpy(storage_path: str) -> tuple[Any, int]:
    """讀取 WAV 檔案，回傳 (numpy ndarray, sample_rate)。

    音檔經 M3 預處理管線後保證為 16kHz mono WAV。使用 torchaudio 讀取後轉
    numpy（shape: [samples]）以符合 qwen-asr transcribe(audio=[(np, sr)]) 介面。
    """
    import numpy as np  # noqa: PLC0415
    import torchaudio  # noqa: PLC0415

    waveform, sample_rate = torchaudio.load(storage_path)
    # waveform shape: [channels, samples]；取第一聲道
    wav_np: np.ndarray = waveform[0].numpy()
    return wav_np, sample_rate


class Transcriber:
    def __init__(
        self,
        db: Session,
        api_key_id: int,
        max_duration_sec: int,
    ) -> None:
        self.db = db
        self.api_key_id = api_key_id
        self.max_duration_sec = max_duration_sec
        self.audio_repo = AudioFileRepository(db, api_key_id)
        self.tx_repo = TranscriptionRepository(db, api_key_id)

    async def run(self, job: AsrJob) -> TranscribeOutcome:
        audio = self.audio_repo.get(job.audio_file_id)
        if audio is None:
            raise NotFoundError(message="audio_file 不存在")

        if audio.duration_sec is None:
            raise AsrInferenceFailedError(message="audio_files.duration_sec 未填寫")

        if audio.duration_sec > self.max_duration_sec:
            raise AsrAudioTooLongError(
                details={
                    "limit_sec": self.max_duration_sec,
                    "actual_sec": audio.duration_sec,
                }
            )

        model_version = AsrEngineManager.model_version()
        record = self.tx_repo.create(
            file_name=audio.original_name,
            source="upload",
            duration_sec=audio.duration_sec,
            language=job.options.get("language"),
            model_name="Qwen3-ASR-1.7B",
            model_version=model_version,
            status="processing",
        )
        self.audio_repo.set_transcription_id(audio.id, record.id)
        self.db.commit()

        # ── 推理核心：asyncio.to_thread 包裝 qwen-asr 同步 transcribe ─────
        asr = AsrEngineManager.get_asr()
        language: str | None = job.options.get("language")  # None = 自動偵測
        context_hint: str = job.options.get("hotword_context", "")  # M5 整合點

        t0 = time.monotonic()
        try:
            wav_np, sample_rate = _load_wav_as_numpy(audio.storage_path)
            results: list[Any] = await asyncio.to_thread(
                asr.transcribe,
                audio=[(wav_np, sample_rate)],
                context=[context_hint],
                language=[language],
                return_time_stamps=True,
            )
        except Exception as e:
            err_name = type(e).__name__
            err_str = str(e)
            self.tx_repo.mark_failed(record.id, error_message=f"{err_name}: {e}")
            self.db.commit()
            if "Cuda" in err_name or "CUDA" in err_name or "Cuda" in err_str or "CUDA" in err_str:
                raise AsrCudaError(details={"error": err_str}) from e
            raise AsrInferenceFailedError(details={"error": err_str}) from e

        duration = time.monotonic() - t0
        result = results[0]
        text: str = result.text
        detected_language: str | None = getattr(result, "language", language)
        ts = _parse_timestamps(result.time_stamps)
        # ────────────────────────────────────────────────────────────────────

        # M7 後處理流程（v1.10 §3.3.2：ForcedAligner 已內建於 ASR 引擎，
        # 此處不再呼叫獨立 AlignerService；timestamps 已由 qwen-asr 內建提供）
        post_processing_metadata: dict[str, Any] = {}
        speakers: list[dict[str, Any]] | None = None

        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()

        from app.services.correction import (  # noqa: PLC0415
            CorrectionOptions,
            run_correction_pipeline,
        )
        from app.services.diarization import DiarizationService  # noqa: PLC0415
        from app.services.finetune.lock import is_finetune_active  # noqa: PLC0415
        from app.services.post_processing import run_post_processing  # noqa: PLC0415

        finetune_active = is_finetune_active(settings)

        # 1. Diarization（pyannote / CAM++ fallback；finetune_active 時強制 CAM++）
        if settings.DIARIZATION_ENABLED and not job.options.get("skip_diarization"):
            try:
                segments, backend = await DiarizationService.diarize(Path(audio.storage_path))
                speakers = [
                    {"speaker": s.speaker, "start": s.start_sec, "end": s.end_sec}
                    for s in segments
                ]
                post_processing_metadata["diarization"] = {
                    "status": "ok",
                    "backend": backend,
                    "speakers": len({s.speaker for s in segments}),
                }
            except Exception as e:  # noqa: BLE001
                post_processing_metadata["diarization"] = {
                    "status": "failed",
                    "error": str(e),
                }

        # 2. 後處理（標點 + 數字正規化）
        if settings.POST_PROCESSING_ENABLED:
            pp = run_post_processing(text)
            text = pp.final_text
            post_processing_metadata["post_processing"] = {"stages": pp.stages}

        # 3. 糾錯四層（NEC → KenLM → 同音 → LLM；finetune_active 時 NEC/LLM 自動降級）
        correction_options = CorrectionOptions(
            nec_enabled=settings.CORRECTION_NEC_ENABLED and not finetune_active,
            kenlm_enabled=settings.CORRECTION_KENLM_ENABLED,
            homophone_enabled=settings.CORRECTION_HOMOPHONE_ENABLED,
            llm_enabled=(
                settings.CORRECTION_LLM_BACKEND != "none" and not finetune_active
            ),
        )
        if any([
            correction_options.nec_enabled,
            correction_options.kenlm_enabled,
            correction_options.homophone_enabled,
            correction_options.llm_enabled,
        ]):
            corr = await run_correction_pipeline(text, correction_options)
            text = corr.final_text
            post_processing_metadata["correction"] = {"stages": corr.stages}

        return_timestamps = job.options.get("return_timestamps", True)
        self.tx_repo.mark_completed(
            record.id,
            transcript_text=text,
            timestamps=ts if return_timestamps else None,
            processing_duration_sec=duration,
        )
        # 寫回 speakers / post_processing 兩個 JSONB 欄位
        record.speakers = speakers
        record.post_processing = post_processing_metadata
        self.db.flush()
        self.db.commit()
        logger.info(
            "transcription completed",
            transcription_id=record.id,
            duration_ms=duration * 1000,
        )
        return TranscribeOutcome(
            transcription_id=record.id,
            text=text,
            timestamps=ts if return_timestamps else None,
            duration_sec=audio.duration_sec,
            processing_duration_sec=duration,
            model_version=model_version,
            language=detected_language,
        )
