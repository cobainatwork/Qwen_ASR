from __future__ import annotations

import time
from dataclasses import dataclass
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
        return_timestamps = job.options.get("return_timestamps", True)
        self.tx_repo.mark_completed(
            record.id,
            transcript_text=text,
            timestamps=ts if return_timestamps else None,
            processing_duration_sec=duration,
        )
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
