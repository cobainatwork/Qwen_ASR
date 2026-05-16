from __future__ import annotations

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


def _build_asr_prompt(audio_path: str, options: dict[str, Any]) -> dict[str, Any]:
    """組裝 vLLM 推理 prompt（依 Qwen3-ASR 介面）。"""
    return {
        "audio_path": audio_path,
        "language": options.get("language"),
        "return_timestamps": options.get("return_timestamps", True),
    }


def _parse_vllm_output(raw: Any) -> tuple[str, list[dict[str, Any]] | None]:
    """解析 vLLM generate 回應。容錯 dict 與 vLLM RequestOutput 兩種型態。"""
    if isinstance(raw, dict):
        return str(raw.get("text", "")), raw.get("timestamps")
    if hasattr(raw, "outputs") and raw.outputs:
        first = raw.outputs[0]
        return getattr(first, "text", ""), getattr(first, "timestamps", None)
    return str(raw), None


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

        engine = AsrEngineManager.get_engine()
        t0 = time.monotonic()
        try:
            raw = await engine.generate(
                prompt=_build_asr_prompt(audio.storage_path, job.options)
            )
        except Exception as e:
            err_name = type(e).__name__
            self.tx_repo.mark_failed(record.id, error_message=f"{err_name}: {e}")
            self.db.commit()
            err_str = str(e)
            if "Cuda" in err_name or "CUDA" in err_name or "Cuda" in err_str or "CUDA" in err_str:
                raise AsrCudaError(details={"error": err_str}) from e
            raise AsrInferenceFailedError(details={"error": str(e)}) from e

        duration = time.monotonic() - t0
        text, ts = _parse_vllm_output(raw)

        # M7 後處理流程
        post_processing_metadata: dict[str, Any] = {}
        speakers: list[dict[str, Any]] | None = None

        from app.core.config import get_settings
        settings = get_settings()

        # 動態 import 4 個服務（避免在無 audio extras 環境啟動 crash）
        from app.services.aligner import AlignerService
        from app.services.correction import CorrectionOptions, run_correction_pipeline
        from app.services.diarization import DiarizationService
        from app.services.finetune.lock import is_finetune_active
        from app.services.post_processing import run_post_processing

        finetune_active = is_finetune_active(settings)

        # 1. ForcedAligner
        if settings.ALIGNER_ENABLED and not finetune_active and not job.options.get("skip_aligner"):
            try:
                word_ts = await AlignerService.align(
                    text, Path(audio.storage_path), audio.duration_sec
                )
                ts = [
                    {"word": w.word, "start": w.start_sec, "end": w.end_sec}
                    for w in word_ts
                ]
                post_processing_metadata["aligner"] = {"status": "ok", "count": len(ts)}
            except Exception as e:
                post_processing_metadata["aligner"] = {"status": "failed", "error": str(e)}

        # 2. Diarization
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
            except Exception as e:
                post_processing_metadata["diarization"] = {"status": "failed", "error": str(e)}

        # 3. 後處理（標點 + 數字正規化）
        if settings.POST_PROCESSING_ENABLED:
            pp = run_post_processing(text)
            text = pp.final_text
            post_processing_metadata["post_processing"] = {"stages": pp.stages}

        # 4. 糾錯四層（NEC → KenLM → 同音 → LLM）
        correction_options = CorrectionOptions(
            nec_enabled=settings.CORRECTION_NEC_ENABLED,
            kenlm_enabled=settings.CORRECTION_KENLM_ENABLED,
            homophone_enabled=settings.CORRECTION_HOMOPHONE_ENABLED,
            llm_enabled=settings.CORRECTION_LLM_BACKEND != "none",
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
            language=job.options.get("language"),
        )
