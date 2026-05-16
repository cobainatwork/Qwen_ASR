"""將 correction segments 匯出為 dataset samples。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import CorrectionSessionNotFoundError, DatasetNotFoundError
from app.models import AudioFile, Transcription
from app.repositories.correction import (
    CorrectionSegmentRepository,
    CorrectionSessionRepository,
)
from app.repositories.dataset import DatasetRepository, DatasetSampleRepository


def export_session_to_dataset(
    *,
    db: Session,
    api_key_id: int,
    session_id: int,
    dataset_id: int,
) -> int:
    """將指定 session 的所有 corrected segments 加入 dataset，回傳新增數。

    僅匯出 corrected_text 非空的段落（已校正）。
    匯出完成後自動呼叫 refresh_stats 更新 dataset 統計。
    """
    session_repo = CorrectionSessionRepository(db, api_key_id)
    session = session_repo.get(session_id)
    if session is None:
        raise CorrectionSessionNotFoundError(details={"session_id": session_id})

    dataset_repo = DatasetRepository(db, api_key_id)
    dataset = dataset_repo.get(dataset_id)
    if dataset is None:
        raise DatasetNotFoundError(details={"dataset_id": dataset_id})

    transcription = db.get(Transcription, session.transcription_id)
    if transcription is None or transcription.api_key_id != api_key_id:
        raise CorrectionSessionNotFoundError(
            details={"session_id": session_id, "reason": "transcription gone"},
        )

    audio = db.execute(
        select(AudioFile).where(AudioFile.transcription_id == transcription.id)
    ).scalar_one_or_none()
    if audio is None:
        raise CorrectionSessionNotFoundError(
            details={"reason": "transcription has no linked audio_file"}
        )

    seg_repo = CorrectionSegmentRepository(db, api_key_id)
    segments = seg_repo.list_by_session(session_id)

    audio_storage = Path(audio.storage_path)
    audio_file_size = audio_storage.stat().st_size if audio_storage.exists() else 0

    sample_repo = DatasetSampleRepository(db, api_key_id)
    inserted = 0
    for seg in segments:
        if not seg.corrected_text:
            continue
        sample_repo.create(
            dataset_id=dataset_id,
            audio_file_id=audio.id,
            transcript=seg.corrected_text,
            duration_sec=seg.end_sec - seg.start_sec,
            file_size=audio_file_size,
        )
        inserted += 1

    dataset_repo.refresh_stats(dataset_id)
    db.flush()
    return inserted
